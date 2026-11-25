"""Unified English/Vietnamese neural TTS for ChessCV.

Transient Edge TTS failures are retried before the API gives up.
Short completed announcements are cached in memory to avoid
repeated remote requests. No audio is saved to disk.
"""

from __future__ import annotations

import asyncio
import logging
from collections import OrderedDict
from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field


router = APIRouter(
    prefix="/voice",
    tags=["Move Voice"],
)

logger = logging.getLogger(__name__)


# ============================================================
# NEURAL VOICES
# ============================================================

VOICE_BY_LANGUAGE = {
    "en": "en-US-AriaNeural",
    "vi": "vi-VN-HoaiMyNeural",
}


# ============================================================
# RETRY CONFIGURATION
# ============================================================

MAX_ATTEMPTS = 3

ATTEMPT_TIMEOUT_SECONDS = 12.0

RETRY_DELAYS_SECONDS = (
    0.5,
    1.2,
)


# ============================================================
# MEMORY CACHE
# ============================================================

MAX_CACHE_ITEMS = 128

MAX_CACHE_BYTES = 12 * 1024 * 1024

MAX_SINGLE_AUDIO_BYTES = 1024 * 1024

_audio_cache: OrderedDict[
    tuple[str, str],
    bytes,
] = OrderedDict()

_cache_size_bytes = 0

_synthesis_lock = asyncio.Lock()


# ============================================================
# REQUEST MODEL
# ============================================================

class SpeakRequest(BaseModel):

    text: str = Field(
        min_length=1,
        max_length=220,
    )

    language: Literal[
        "en",
        "vi",
    ] = "en"


# ============================================================
# CACHE MANAGEMENT
# ============================================================

def _cache_audio(
    key: tuple[str, str],
    audio: bytes,
) -> None:

    global _cache_size_bytes

    if len(audio) > MAX_SINGLE_AUDIO_BYTES:
        return

    previous = _audio_cache.pop(
        key,
        None,
    )

    if previous is not None:
        _cache_size_bytes -= len(previous)

    _audio_cache[key] = audio

    _cache_size_bytes += len(audio)

    while (
        len(_audio_cache) > MAX_CACHE_ITEMS
        or _cache_size_bytes > MAX_CACHE_BYTES
    ):

        _, removed = _audio_cache.popitem(
            last=False,
        )

        _cache_size_bytes -= len(removed)


# ============================================================
# GENERATE NEURAL AUDIO
# ============================================================

async def _synthesize(
    text: str,
    voice: str,
) -> bytes:

    import edge_tts

    communicate = edge_tts.Communicate(
        text=text,
        voice=voice,
    )

    chunks: list[bytes] = []

    async for chunk in communicate.stream():

        if chunk.get("type") == "audio":

            chunks.append(
                chunk["data"]
            )

    if not chunks:

        raise RuntimeError(
            "Edge TTS returned no audio data"
        )

    return b"".join(chunks)


# ============================================================
# COMMON AUDIO RESPONSE
# ============================================================

def _audio_response(
    data: bytes,
    language: str,
    cache_status: str,
    attempts: int,
) -> Response:

    return Response(
        content=data,
        media_type="audio/mpeg",
        headers={
            "Cache-Control": "no-store",
            "X-TTS-Language": language,
            "X-TTS-Cache": cache_status,
            "X-TTS-Attempts": str(attempts),
        },
    )


# ============================================================
# NEURAL TTS ENDPOINT
# ============================================================

@router.post(
    "/speak",
    response_class=Response,
)
async def speak_move(
    payload: SpeakRequest,
) -> Response:

    text = payload.text.strip()

    if not text:

        raise HTTPException(
            status_code=422,
            detail="Spoken text cannot be empty.",
        )

    # ========================================================
    # DEPENDENCY CHECK
    # ========================================================

    try:

        import edge_tts

    except ImportError as error:

        raise HTTPException(
            status_code=503,
            detail=(
                "edge-tts is not installed. "
                "Run: python -m pip install -U edge-tts"
            ),
        ) from error

    key = (
        payload.language,
        text,
    )

    voice = VOICE_BY_LANGUAGE[
        payload.language
    ]

    # ========================================================
    # SERIALIZE SYNTHESIS REQUESTS
    #
    # Prevent concurrent upstream requests.
    # Also avoid generating the same audio repeatedly.
    # ========================================================

    async with _synthesis_lock:

        # ====================================================
        # CACHE LOOKUP
        # ====================================================

        cached = _audio_cache.get(key)

        if cached is not None:

            _audio_cache.move_to_end(key)

            return _audio_response(
                data=cached,
                language=payload.language,
                cache_status="HIT",
                attempts=0,
            )

        # ====================================================
        # EDGE TTS RETRIES
        # ====================================================

        last_error: Exception | None = None

        for attempt in range(
            1,
            MAX_ATTEMPTS + 1,
        ):

            try:

                audio = await asyncio.wait_for(
                    _synthesize(
                        text,
                        voice,
                    ),
                    timeout=ATTEMPT_TIMEOUT_SECONDS,
                )

                # ============================================
                # SAVE SUCCESSFUL AUDIO TO CACHE
                # ============================================

                _cache_audio(
                    key,
                    audio,
                )

                if attempt > 1:

                    logger.info(
                        "Edge TTS recovered on attempt %d/%d "
                        "(language=%s)",
                        attempt,
                        MAX_ATTEMPTS,
                        payload.language,
                    )

                return _audio_response(
                    data=audio,
                    language=payload.language,
                    cache_status="MISS",
                    attempts=attempt,
                )

            except Exception as error:

                last_error = error

                upstream_status = getattr(
                    error,
                    "status",
                    "unknown",
                )

                logger.warning(
                    "Edge TTS failed: "
                    "attempt=%d/%d "
                    "language=%s "
                    "error=%s "
                    "upstream_status=%s",
                    attempt,
                    MAX_ATTEMPTS,
                    payload.language,
                    type(error).__name__,
                    upstream_status,
                )

                # ============================================
                # WAIT BEFORE NEXT ATTEMPT
                # ============================================

                if attempt < MAX_ATTEMPTS:

                    await asyncio.sleep(
                        RETRY_DELAYS_SECONDS[
                            attempt - 1
                        ]
                    )

    # ========================================================
    # ALL ATTEMPTS FAILED
    # ========================================================

    error_name = (
        type(last_error).__name__
        if last_error is not None
        else "UnknownError"
    )

    raise HTTPException(
        status_code=503,
        detail=(
            f"Neural voice unavailable after "
            f"{MAX_ATTEMPTS} attempts "
            f"({error_name}). "
            "Check Edge TTS connectivity "
            "and backend logs."
        ),
    ) from last_error

"""Unified neural TTS service for ChessCV.

English and Vietnamese use the same Edge TTS provider,
the same API endpoint and the same MP3 audio format.

The frontend handles audio output independently through
an Audio Output Adapter.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field


router = APIRouter(
    prefix="/voice",
    tags=["Move Voice"],
)


# ============================================================
# NEURAL VOICE CONFIGURATION
# ============================================================

VOICE_BY_LANGUAGE = {
    "en": "en-US-AriaNeural",
    "vi": "vi-VN-HoaiMyNeural",
}


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

    voice = VOICE_BY_LANGUAGE[
        payload.language
    ]

    # ========================================================
    # EDGE TTS DEPENDENCY
    # ========================================================

    try:

        import edge_tts

    except ImportError as error:

        raise HTTPException(
            status_code=503,
            detail=(
                "edge-tts is not installed. "
                "Run: python -m pip install edge-tts"
            ),
        ) from error

    # ========================================================
    # GENERATE AUDIO
    # ========================================================

    try:

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
                "No audio received from Edge TTS."
            )

        audio_data = b"".join(chunks)

        # ====================================================
        # COMMON AUDIO RESPONSE
        # ====================================================

        return Response(
            content=audio_data,
            media_type="audio/mpeg",
            headers={
                "Cache-Control": "no-store",
                "X-TTS-Language": payload.language,
            },
        )

    except Exception as error:

        raise HTTPException(
            status_code=503,
            detail=(
                "Neural voice generation failed. "
                "Check the internet connection and Edge TTS service."
            ),
        ) from error

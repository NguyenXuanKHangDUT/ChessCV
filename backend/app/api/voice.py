"""ChessCV voice API: legacy Edge TTS plus reliable offline ESP32 queue.

Live Game uses local MP3 clips. When ESP32 is selected, the browser enqueues
clip keys here. ESP32 polls, downloads MP3 files, plays them, then acknowledges.
Queue state persists in an independent SQLite file across backend restarts.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import sqlite3
import time
from collections import OrderedDict
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse, Response
from pydantic import BaseModel, Field

router = APIRouter(prefix="/voice", tags=["Move Voice"])
logger = logging.getLogger(__name__)

VOICE_BY_LANGUAGE = {
    "en": "en-US-AriaNeural",
    "vi": "vi-VN-HoaiMyNeural",
}

MAX_ATTEMPTS = 3
ATTEMPT_TIMEOUT_SECONDS = 12.0
RETRY_DELAYS_SECONDS = (0.5, 1.2)
MAX_CACHE_ITEMS = 128
MAX_CACHE_BYTES = 12 * 1024 * 1024
MAX_SINGLE_AUDIO_BYTES = 1024 * 1024

_audio_cache: OrderedDict[tuple[str, str], bytes] = OrderedDict()
_cache_size_bytes = 0
_synthesis_lock = asyncio.Lock()


class SpeakRequest(BaseModel):
    text: str = Field(min_length=1, max_length=220)
    language: Literal["en", "vi"] = "en"


def _cache_audio(key: tuple[str, str], audio: bytes) -> None:
    global _cache_size_bytes

    if len(audio) > MAX_SINGLE_AUDIO_BYTES:
        return

    previous = _audio_cache.pop(key, None)
    if previous is not None:
        _cache_size_bytes -= len(previous)

    _audio_cache[key] = audio
    _cache_size_bytes += len(audio)

    while len(_audio_cache) > MAX_CACHE_ITEMS or _cache_size_bytes > MAX_CACHE_BYTES:
        _, removed = _audio_cache.popitem(last=False)
        _cache_size_bytes -= len(removed)


async def _synthesize(text: str, voice: str) -> bytes:
    import edge_tts

    communicate = edge_tts.Communicate(text=text, voice=voice)
    chunks: list[bytes] = []
    async for chunk in communicate.stream():
        if chunk.get("type") == "audio":
            chunks.append(chunk["data"])

    if not chunks:
        raise RuntimeError("Edge TTS returned no audio data")

    return b"".join(chunks)


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


@router.post("/speak", response_class=Response)
async def speak_move(payload: SpeakRequest) -> Response:
    text = payload.text.strip()
    if not text:
        raise HTTPException(status_code=422, detail="Spoken text cannot be empty.")

    try:
        import edge_tts
    except ImportError as error:
        raise HTTPException(
            status_code=503,
            detail="edge-tts is not installed. Run: python -m pip install -U edge-tts",
        ) from error

    key = (payload.language, text)
    voice = VOICE_BY_LANGUAGE[payload.language]

    async with _synthesis_lock:
        cached = _audio_cache.get(key)
        if cached is not None:
            _audio_cache.move_to_end(key)
            return _audio_response(cached, payload.language, "HIT", 0)

        last_error: Exception | None = None

        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                audio = await asyncio.wait_for(
                    _synthesize(text, voice), timeout=ATTEMPT_TIMEOUT_SECONDS
                )
                _cache_audio(key, audio)
                if attempt > 1:
                    logger.info(
                        "Edge TTS recovered on attempt %d/%d (language=%s)",
                        attempt,
                        MAX_ATTEMPTS,
                        payload.language,
                    )
                return _audio_response(audio, payload.language, "MISS", attempt)
            except Exception as error:
                last_error = error
                logger.warning(
                    "Edge TTS failed: attempt=%d/%d language=%s error=%s upstream_status=%s",
                    attempt,
                    MAX_ATTEMPTS,
                    payload.language,
                    type(error).__name__,
                    getattr(error, "status", "unknown"),
                )
                if attempt < MAX_ATTEMPTS:
                    await asyncio.sleep(RETRY_DELAYS_SECONDS[attempt - 1])

    error_name = type(last_error).__name__ if last_error else "UnknownError"
    raise HTTPException(
        status_code=503,
        detail=(
            f"Neural voice unavailable after {MAX_ATTEMPTS} attempts "
            f"({error_name}). Check Edge TTS connectivity and backend logs."
        ),
    ) from last_error


# ============================================================
# OFFLINE ESP32 AUDIO BRIDGE
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[3]
AUDIO_ROOT = PROJECT_ROOT / "frontend" / "public" / "audio"
DB_PATH = PROJECT_ROOT / "data" / "esp32_audio_queue.sqlite3"
CLIP_KEY = re.compile(r"^[a-z0-9_]{1,64}$")
MAX_PENDING_JOBS = 128
MAX_CLIPS_PER_JOB = 24
_device_last_poll: float = 0.0


@contextmanager
def _db() -> Iterator[sqlite3.Connection]:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH, timeout=10.0)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def _init_db() -> None:
    with _db() as database:
        database.execute(
            """
            CREATE TABLE IF NOT EXISTS esp32_audio_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id TEXT NOT NULL UNIQUE,
                language TEXT NOT NULL,
                clips_json TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                failures INTEGER NOT NULL DEFAULT 0,
                last_error TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                completed_at TEXT
            )
            """
        )
        database.execute(
            "CREATE INDEX IF NOT EXISTS idx_esp32_audio_pending "
            "ON esp32_audio_jobs(status, id)"
        )


_init_db()


class EnqueueRequest(BaseModel):
    request_id: str = Field(min_length=8, max_length=96)
    language: Literal["en", "vi"]
    clips: list[str] = Field(min_length=1, max_length=MAX_CLIPS_PER_JOB)


def _validate_clips(language: str, clips: list[str]) -> None:
    for clip in clips:
        if not CLIP_KEY.fullmatch(clip):
            raise HTTPException(status_code=422, detail=f"Invalid clip key: {clip!r}")
        path = AUDIO_ROOT / language / f"{clip}.mp3"
        if not path.is_file() or path.stat().st_size < 600:
            raise HTTPException(
                status_code=503,
                detail=f"Missing offline audio clip: {language}/{clip}.mp3",
            )


@router.post("/esp32/enqueue")
def enqueue_esp32_audio(payload: EnqueueRequest) -> dict:
    if not re.fullmatch(r"[A-Za-z0-9_-]{8,96}", payload.request_id):
        raise HTTPException(status_code=422, detail="Invalid request_id")

    _validate_clips(payload.language, payload.clips)

    with _db() as database:
        existing = database.execute(
            "SELECT id, status FROM esp32_audio_jobs WHERE request_id = ?",
            (payload.request_id,),
        ).fetchone()
        if existing:
            return {
                "ok": True,
                "job_id": existing["id"],
                "status": existing["status"],
                "duplicate": True,
            }

        pending = database.execute(
            "SELECT COUNT(*) FROM esp32_audio_jobs WHERE status = 'pending'"
        ).fetchone()[0]
        if pending >= MAX_PENDING_JOBS:
            raise HTTPException(status_code=429, detail="ESP32 audio queue is full")

        cursor = database.execute(
            "INSERT INTO esp32_audio_jobs(request_id, language, clips_json) "
            "VALUES (?, ?, ?)",
            (payload.request_id, payload.language, json.dumps(payload.clips)),
        )
        job_id = cursor.lastrowid

    logger.info("ESP32 queued job=%s language=%s clips=%d", job_id, payload.language, len(payload.clips))
    return {"ok": True, "job_id": job_id, "status": "pending", "duplicate": False}


@router.get("/esp32/next", response_class=PlainTextResponse)
def next_esp32_audio() -> PlainTextResponse:
    global _device_last_poll
    _device_last_poll = time.monotonic()

    with _db() as database:
        job = database.execute(
            "SELECT id, language, clips_json FROM esp32_audio_jobs "
            "WHERE status = 'pending' ORDER BY id LIMIT 1"
        ).fetchone()

    if job is None:
        return PlainTextResponse("NONE\n", headers={"Cache-Control": "no-store"})

    clips = json.loads(job["clips_json"])
    response = f"{job['id']}|{job['language']}|{','.join(clips)}\n"
    return PlainTextResponse(response, headers={"Cache-Control": "no-store"})


@router.post("/esp32/ack")
def acknowledge_esp32_audio(job_id: int, ok: bool = True) -> dict:
    global _device_last_poll
    _device_last_poll = time.monotonic()
    if job_id < 1:
        raise HTTPException(status_code=422, detail="Invalid job_id")

    with _db() as database:
        job = database.execute(
            "SELECT id, status FROM esp32_audio_jobs WHERE id = ?", (job_id,)
        ).fetchone()
        if job is None:
            raise HTTPException(status_code=404, detail="ESP32 job not found")

        if job["status"] == "done":
            return {"ok": True, "job_id": job_id, "already_done": True}

        if ok:
            database.execute(
                "UPDATE esp32_audio_jobs SET status = 'done', "
                "completed_at = CURRENT_TIMESTAMP WHERE id = ?", (job_id,)
            )
        else:
            database.execute(
                "UPDATE esp32_audio_jobs SET failures = failures + 1, "
                "last_error = 'ESP32 playback/download failed' WHERE id = ?",
                (job_id,),
            )

    if ok:
        logger.info("ESP32 completed audio job=%d", job_id)
    else:
        logger.warning("ESP32 will retry audio job=%d", job_id)
    return {"ok": True, "job_id": job_id, "completed": ok}


@router.get("/esp32/status")
def esp32_audio_status() -> dict:
    online = (_device_last_poll > 0 and time.monotonic() - _device_last_poll < 8.0)
    with _db() as database:
        pending = database.execute(
            "SELECT COUNT(*) FROM esp32_audio_jobs WHERE status = 'pending'"
        ).fetchone()[0]
        failures = database.execute(
            "SELECT COALESCE(SUM(failures),0) FROM esp32_audio_jobs WHERE status = 'pending'"
        ).fetchone()[0]
    return {
        "online": online,
        "pending": pending,
        "retry_count": failures,
        "source": "offline_mp3",
    }


@router.get("/esp32/clip/{language}/{clip_key}.mp3")
def get_esp32_audio_clip(language: Literal["en", "vi"], clip_key: str) -> FileResponse:
    global _device_last_poll
    _device_last_poll = time.monotonic()
    if not CLIP_KEY.fullmatch(clip_key):
        raise HTTPException(status_code=404, detail="Invalid clip key")

    path = AUDIO_ROOT / language / f"{clip_key}.mp3"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Audio clip not found")

    return FileResponse(
        path=path,
        media_type="audio/mpeg",
        headers={"Cache-Control": "public, max-age=3600"},
    )
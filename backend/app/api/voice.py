"""Vietnamese neural voice for ChessCV move announcements.

The browser sends a short spoken move in Vietnamese and receives MP3 bytes.
This endpoint does not change the chess engine, game state, or UI language.

Requires `python -m pip install edge-tts` in the backend environment.
The voice service needs an internet connection.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

router = APIRouter(prefix="/voice", tags=["Move Voice"])


class SpeakRequest(BaseModel):
    text: str = Field(min_length=1, max_length=220)
    voice: Literal[
        "vi-VN-HoaiMyNeural",
        "vi-VN-NamMinhNeural",
    ] = "vi-VN-HoaiMyNeural"


@router.post("/speak", response_class=Response)
async def speak_vi_move(payload: SpeakRequest) -> Response:
    """Generate a short Vietnamese move announcement as audio/mpeg."""

    text = payload.text.strip()
    if not text:
        raise HTTPException(status_code=422, detail="Spoken text cannot be empty.")

    try:
        import edge_tts
    except ImportError as error:
        raise HTTPException(
            status_code=503,
            detail="edge-tts is not installed. Run: python -m pip install edge-tts",
        ) from error

    try:
        communicate = edge_tts.Communicate(text=text, voice=payload.voice)
        chunks: list[bytes] = []

        async for chunk in communicate.stream():
            if chunk.get("type") == "audio":
                chunks.append(chunk["data"])

        if not chunks:
            raise RuntimeError("No audio received from the neural voice service.")

        return Response(
            content=b"".join(chunks),
            media_type="audio/mpeg",
            headers={"Cache-Control": "no-store"},
        )

    except Exception as error:
        # Do not affect game state when the remote TTS service is unavailable.
        raise HTTPException(
            status_code=503,
            detail=(
                "Vietnamese neural voice is unavailable. "
                "Check the internet connection and edge-tts installation."
            ),
        ) from error
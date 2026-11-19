"""LAN audio bridge for an ESP32 DevKit (stage 1: MP3 -> PCM only).

The existing /api/voice/speak and browser EN/VI TTS remain unchanged.
ESP32 pulls a read-only move event, then GETs a synthesized MP3.
No speaker, DAC or amplifier is needed to validate the PCM decoder.
"""

from __future__ import annotations

import re
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from backend.app.services.live_game_service import live_game_service


router = APIRouter(
    prefix="/esp32",
    tags=["ESP32 Audio"],
)


VOICE_MODELS = {
    "vi": "vi-VN-HoaiMyNeural",
    "en": "en-US-JennyNeural",
}


PIECE_NAMES = {
    "vi": {
        "K": "Vua",
        "Q": "Hậu",
        "R": "Xe",
        "B": "Tượng",
        "N": "Mã",
        "P": "Tốt",
    },
    "en": {
        "K": "King",
        "Q": "Queen",
        "R": "Rook",
        "B": "Bishop",
        "N": "Knight",
        "P": "pawn",
    },
}


RANKS = {
    "vi": {
        "1": "một",
        "2": "hai",
        "3": "ba",
        "4": "bốn",
        "5": "năm",
        "6": "sáu",
        "7": "bảy",
        "8": "tám",
    },
    "en": {
        str(n): str(n)
        for n in range(1, 9)
    },
}


FILES_VI = {
    "a": "a",
    "b": "bê",
    "c": "xê",
    "d": "đê",
    "e": "e",
    "f": "ép",
    "g": "giê",
    "h": "hát",
}


SAN_PATTERN = re.compile(
    r"^(?P<piece>[KQRBN])?"
    r"(?P<hint>[a-h1-8]{0,2})"
    r"(?P<capture>x)?"
    r"(?P<target>[a-h][1-8])"
    r"(?:=(?P<promo>[QRBN]))?"
    r"(?P<suffix>[+#])?$"
)


def _square_speech(
    value: str,
    language: str,
) -> str:
    return " ".join(
        RANKS[language].get(char)
        or (
            FILES_VI.get(char, char)
            if language == "vi"
            else char
        )
        for char in value
    )


def san_to_speech(
    san: str,
    color: str,
    language: str,
) -> str:
    """Strictly convert legal SAN from GameTracker into a spoken move."""

    player = (
        ("Trắng" if color == "white" else "Đen")
        if language == "vi"
        else ("White" if color == "white" else "Black")
    )

    cleaned = re.sub(
        r"[!?]+$",
        "",
        san.strip().replace("0", "O"),
    )

    is_mate = cleaned.endswith("#")
    is_check = cleaned.endswith("+")
    stripped = cleaned.rstrip("+#")

    if stripped in ("O-O", "O-O-O"):
        if language == "vi":
            sentence = (
                f"{player} nhập thành cánh "
                f"{'vua' if stripped == 'O-O' else 'hậu'}"
            )
        else:
            sentence = (
                f"{player} castles "
                f"{'kingside' if stripped == 'O-O' else 'queenside'}"
            )
    else:
        match = SAN_PATTERN.fullmatch(cleaned)

        if not match:
            raise HTTPException(
                status_code=422,
                detail=f"Unsupported SAN: {san!r}.",
            )

        data = match.groupdict()

        piece_name = PIECE_NAMES[language][
            data["piece"] or "P"
        ]

        sentence = f"{player} {piece_name}"

        if data["hint"]:
            sentence += (
                f" {'từ' if language == 'vi' else 'from'} "
                f"{_square_speech(data['hint'], language)}"
            )

        if data["capture"]:
            sentence += (
                f" {'ăn' if language == 'vi' else 'takes'}"
            )

        sentence += (
            f" {_square_speech(data['target'], language)}"
        )

        if data["promo"]:
            sentence += (
                f" phong thành "
                f"{PIECE_NAMES[language][data['promo']]}"
                if language == "vi"
                else (
                    f" promotes to "
                    f"{PIECE_NAMES[language][data['promo']]}"
                )
            )

    if is_mate:
        sentence += (
            ", chiếu hết"
            if language == "vi"
            else ", checkmate"
        )
    elif is_check:
        sentence += (
            ", chiếu"
            if language == "vi"
            else ", check"
        )

    return sentence


def _brief_state() -> dict:
    raw = live_game_service.get_state()

    if not raw.get("running") or not raw.get("started_at"):
        return {
            "running": False,
            "session": "",
            "moves": [],
            "pending": None,
        }

    return {
        "running": True,
        "session": str(raw["started_at"]),
        "moves": raw.get("moves") or [],
        "pending": raw.get("pending_bot_move"),
    }


@router.get("/health")
def esp32_audio_health() -> dict:
    return {
        "ok": True,
        "mode": "mp3-over-http-to-pcm",
        "voice_languages": ["vi", "en"],
    }


@router.get("/next")
def next_move_for_esp32(
    session: str = Query(default="", max_length=100),
    after_ply: int = Query(default=0, ge=0),
    spoken_pending: str = Query(default="", max_length=100),
) -> dict:
    """Stateless polling with per-device cursors held by the ESP32.

    'skip' advances the cursor without speaking a bot move already announced
    when it was pending. This avoids reading a bot move twice.
    """

    state = _brief_state()

    if not state["running"]:
        return {
            "kind": "stopped",
            "session": "",
            "latest_ply": 0,
        }

    moves = state["moves"]

    latest_ply = max(
        (
            int(m.get("ply") or 0)
            for m in moves
        ),
        default=0,
    )

    current_session = state["session"]

    if session != current_session:
        return {
            "kind": "sync",
            "session": current_session,
            "latest_ply": latest_ply,
        }

    # Send one confirmed move each request.
    # If TTS/decoding is slower than polling, moves remain in order.

    for move in sorted(
        moves,
        key=lambda m: int(m.get("ply") or 0),
    ):
        ply = int(move.get("ply") or 0)

        if ply <= after_ply:
            continue

        uci = str(move.get("uci") or "")
        pending_key = f"{ply}|{uci}"

        return {
            "kind": (
                "skip"
                if pending_key == spoken_pending
                else "move"
            ),
            "session": current_session,
            "latest_ply": latest_ply,
            "ply": ply,
            "san": str(move.get("san") or ""),
            "color": str(move.get("color") or ""),
            "uci": uci,
            "pending_key": pending_key,
        }

    # If the bot has a pending move, announce it before
    # it is performed on the physical chessboard.

    pending = state["pending"]

    if pending:
        next_ply = latest_ply + 1
        uci = str(pending.get("uci") or "")
        key = f"{next_ply}|{uci}"

        if key != spoken_pending:
            return {
                "kind": "pending",
                "session": current_session,
                "latest_ply": latest_ply,
                "ply": next_ply,
                "san": str(pending.get("san") or ""),
                "color": str(pending.get("color") or ""),
                "uci": uci,
                "pending_key": key,
            }

    return {
        "kind": "idle",
        "session": current_session,
        "latest_ply": latest_ply,
    }


@router.get("/tts.mp3")
async def esp32_tts_mp3(
    san: str = Query(min_length=2, max_length=16),
    color: Literal["white", "black"] = "white",
    lang: Literal["en", "vi"] = "vi",
) -> Response:
    """Generate a complete MP3 for embedded HTTP GET clients."""

    text = san_to_speech(san, color, lang)

    try:
        import edge_tts

        chunks: list[bytes] = []

        async for chunk in edge_tts.Communicate(
            text=text,
            voice=VOICE_MODELS[lang],
        ).stream():
            if chunk.get("type") == "audio":
                data = chunk.get("data")

                if data:
                    chunks.append(data)

        mp3 = b"".join(chunks)

        if not mp3:
            raise RuntimeError(
                "Neural TTS returned no audio data."
            )

    except Exception as error:
        raise HTTPException(
            status_code=503,
            detail=(
                f"Unable to generate neural MP3: {error}"
            ),
        ) from error

    return Response(
        content=mp3,
        media_type="audio/mpeg",
        headers={
            "Cache-Control": "no-store",
        },
    )
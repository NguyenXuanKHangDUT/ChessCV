"""Build ChessCV's fixed EN/VI voice clips once (not during gameplay).

Run from the repository root:
    python -m pip install -U edge-tts
    python scripts/build_offline_chess_audio.py

All completed clips survive interrupted runs. Only write manifest.json
when every clip for BOTH languages is present and nonempty.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

try:
    import edge_tts
except ImportError:
    raise SystemExit("Missing edge-tts. Run: python -m pip install -U edge-tts")

ROOT = Path(__file__).resolve().parent.parent
AUDIO_DIR = ROOT / "frontend" / "public" / "audio"
VOICE = {"en": "en-US-AriaNeural", "vi": "vi-VN-HoaiMyNeural"}
FILES = "abcdefgh"
RANKS = "12345678"
PIECES = ("king", "queen", "rook", "bishop", "knight", "pawn")
PROMOTIONS = ("queen", "rook", "bishop", "knight")

EN_PIECES = {
    "king": "King", "queen": "Queen", "rook": "Rook",
    "bishop": "Bishop", "knight": "Knight", "pawn": "pawn",
}
VI_PIECES = {
    "king": "Vua", "queen": "Hậu", "rook": "Xe",
    "bishop": "Tượng", "knight": "Mã", "pawn": "Tốt",
}
EN_COLORS = {"white": "White", "black": "Black"}
VI_COLORS = {"white": "Trắng", "black": "Đen"}
EN_RANKS = {
    "1": "one", "2": "two", "3": "three", "4": "four",
    "5": "five", "6": "six", "7": "seven", "8": "eight",
}
VI_RANKS = {
    "1": "một", "2": "hai", "3": "ba", "4": "bốn",
    "5": "năm", "6": "sáu", "7": "bảy", "8": "tám",
}
VI_FILES = {
    "a": "a", "b": "bê", "c": "xê", "d": "đê",
    "e": "e", "f": "ép", "g": "giê", "h": "hát",
}
# Say chess FILE letters as letters, not as articles or words.
EN_SPOKEN_FILES = {
    "a": "ay", "b": "bee", "c": "see", "d": "dee",
    "e": "ee", "f": "eff", "g": "jee", "h": "aitch",
}


def make_manifest() -> dict:
    result: dict[str, list[dict[str, str]]] = {"en": [], "vi": []}
    for language in ("en", "vi"):
        items = result[language]
        used_keys: set[str] = set()

        def add(key: str, match: str, speech: str | None = None) -> None:
            if key in used_keys:
                raise ValueError(f"Duplicate audio key: {language}/{key}")
            used_keys.add(key)
            items.append({
                "key": key,
                "match": match,
                "speech": speech if speech is not None else match,
                "file": f"{language}/{key}.mp3",
            })

        piece_names = VI_PIECES if language == "vi" else EN_PIECES
        color_names = VI_COLORS if language == "vi" else EN_COLORS
        rank_names = VI_RANKS if language == "vi" else EN_RANKS
        file_names = VI_FILES if language == "vi" else {c: c for c in FILES}
        spoken_files = VI_FILES if language == "vi" else EN_SPOKEN_FILES

        for color in ("white", "black"):
            for piece in PIECES:
                add(
                    f"piece_{color}_{piece}",
                    f"{color_names[color]} {piece_names[piece]}",
                )
                if language == "vi":
                    # Illegal warning puts the piece BEFORE its color.
                    add(
                        f"illegal_piece_{color}_{piece}",
                        f"{piece_names[piece]} {color_names[color].lower()}",
                    )

            for side in ("kingside", "queenside"):
                if language == "vi":
                    side_name = "cánh vua" if side == "kingside" else "cánh hậu"
                    phrase = f"{color_names[color]} nhập thành {side_name}"
                else:
                    phrase = f"{color_names[color]} castles {side}"
                add(f"castle_{color}_{side}", phrase)

        for file_letter in FILES:
            for rank in RANKS:
                match = f"{file_names[file_letter]} {rank_names[rank]}"
                if language == "en":
                    speech = f"{spoken_files[file_letter]} {rank_names[rank]}"
                else:
                    speech = match
                add(f"square_{file_letter}{rank}", match, speech)

        for file_letter in FILES:
            add(f"file_{file_letter}", file_names[file_letter], spoken_files[file_letter])

        for rank in RANKS:
            add(f"rank_{rank}", rank_names[rank])

        if language == "vi":
            actions = {
                "from": "từ", "to": "đến", "takes": "ăn",
                "check": "chiếu", "checkmate": "chiếu hết",
                "illegal": "Nước đi không hợp lệ",
            }
            for name, phrase in actions.items():
                add(f"action_{name}", phrase)
            for piece in PROMOTIONS:
                add(f"promote_{piece}", f"phong thành {piece_names[piece]}")
        else:
            actions = {
                "from": "from", "to": "to", "takes": "takes",
                "check": "check", "checkmate": "checkmate",
                "illegal": "Illegal move",
            }
            for name, phrase in actions.items():
                add(f"action_{name}", phrase)
            for piece in PROMOTIONS:
                add(f"promote_{piece}", f"promotes to {piece_names[piece]}")

    return {"version": 1, "languages": result}


def valid_audio(path: Path) -> bool:
    if not path.is_file() or path.stat().st_size < 600:
        return False
    with path.open("rb") as stream:
        signature = stream.read(3)
    return signature == b"ID3" or signature[:2] in (
        b"\xff\xfb", b"\xff\xf3", b"\xff\xf2",
    )


async def synthesize(text: str, voice: str) -> bytes:
    stream = edge_tts.Communicate(text=text, voice=voice, rate="-5%")
    chunks: list[bytes] = []
    async for event in stream.stream():
        if event.get("type") == "audio":
            chunks.append(event["data"])
    data = b"".join(chunks)
    if not data:
        raise RuntimeError("NoAudioReceived")
    return data


async def run_build(force: bool) -> None:
    manifest = make_manifest()
    clips = [
        (language, item)
        for language, items in manifest["languages"].items()
        for item in items
    ]
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []
    generated = 0
    reused = 0

    for index, (language, item) in enumerate(clips, start=1):
        dest = AUDIO_DIR / item["file"]
        dest.parent.mkdir(parents=True, exist_ok=True)
        key = f"{language}/{item['key']}"

        if not force and valid_audio(dest):
            reused += 1
            print(f"[{index}/{len(clips)}] SKIP {key}")
            continue

        for attempt in range(1, 8):
            try:
                audio = await asyncio.wait_for(
                    synthesize(item["speech"], VOICE[language]),
                    timeout=20.0,
                )
                temp = dest.with_suffix(".mp3.tmp")
                temp.write_bytes(audio)
                if not valid_audio(temp):
                    raise RuntimeError("Audio data is missing or invalid")
                os.replace(temp, dest)
                generated += 1
                print(
                    f"[{index}/{len(clips)}] OK   {key} "
                    f"({len(audio)} bytes; attempt {attempt})"
                )
                break
            except Exception as error:
                print(
                    f"[{index}/{len(clips)}] RETRY {key} "
                    f"attempt {attempt}/7: {type(error).__name__}: {error}"
                )
                if attempt < 7:
                    await asyncio.sleep(min(2 * attempt, 12))
        else:
            failures.append(key)
            # Fail early: running the script again resumes previous files.
            break

    if failures:
        print("\nCHƯA HOÀN THÀNH. Chạy lại chính lệnh trên để tiếp tục.")
        print("File còn lỗi:", ", ".join(failures))
        raise SystemExit(1)

    for language, item in clips:
        if not valid_audio(AUDIO_DIR / item["file"]):
            raise RuntimeError(f"Missing audio: {language}/{item['key']}")

    manifest_file = AUDIO_DIR / "manifest.json"
    manifest_file.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print("\nDONE. Thư viện âm thanh đã hoàn tất.")
    print(f"Tổng file MP3: {len(clips)} (mới: {generated}, đã có: {reused})")
    print(f"Manifest: {manifest_file}")
    print("Khi chơi cờ, ChessCV chỉ tải MP3 local; không gọi Edge TTS.")
    print("Nghe thử những file trong frontend/public/audio/vi trước khi dùng.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate the fixed EN+VI ChessCV voice pack once."
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Regenerate every file, including manually replaced audio.",
    )
    options = parser.parse_args()
    try:
        asyncio.run(run_build(options.force))
    except KeyboardInterrupt:
        print("\nĐã dừng. Chạy lại để tiếp tục từ các file đã tạo.")
        sys.exit(130)
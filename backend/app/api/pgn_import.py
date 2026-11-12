"""Import exactly one standard-chess PGN into the existing ChessCV database.

Keep ChessCV's PGN headers (Event, Date, Round, White, Black, Result).
Keep SetUp/FEN only for nonstandard starting positions; save ECO/Opening
in the existing database columns, not in the stored PGN headers.

Both preview and import validate every move. The database import is atomic
and keeps all other saved games unchanged.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass
from datetime import datetime

import chess
import chess.pgn
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.database.db import get_db
from backend.app.database.models.game import Game
from backend.app.database.models.move import Move
from backend.app.database.models.player import Player
from backend.app.services.opening_service import opening_service

router = APIRouter(prefix="/pgn", tags=["PGN Import"])

MAX_PGN_CHARS = 250_000
MAX_PLIES = 1_000
KEEP_TAGS = ("Event", "Date", "Round", "White", "Black", "Result")
ECO_PATTERN = re.compile(r"^[A-E][0-9]{2}$")


class PgnInput(BaseModel):
    pgn: str = Field(min_length=1, max_length=MAX_PGN_CHARS)


@dataclass
class PreparedGame:
    white: str
    black: str
    result: str
    started_at: datetime | None
    initial_fen: str
    final_fen: str
    pgn: str
    eco_code: str | None
    opening_name: str | None
    moves: list[dict]
    headers_kept: dict[str, str]
    headers_database: dict[str, str]
    headers_removed: list[str]


def _clean_name(name: str, fallback: str) -> str:
    clean = " ".join(name.split())
    if not clean or clean == "?":
        return fallback
    if len(clean) > 100:
        raise HTTPException(status_code=422, detail="Player name exceeds 100 characters.")
    return clean


def _parse_date(value: str) -> datetime | None:
    # PGN can legitimately contain ???? or partial dates.
    if not re.fullmatch(r"\d{4}\.\d{2}\.\d{2}", value):
        return None
    try:
        return datetime.strptime(value, "%Y.%m.%d")
    except ValueError:
        return None


def _prepare(pgn_text: str) -> PreparedGame:
    text = pgn_text.lstrip("\ufeff").strip()
    if not text:
        raise HTTPException(status_code=422, detail="Paste a PGN or choose a .pgn file first.")
    if len(text) > MAX_PGN_CHARS:
        raise HTTPException(status_code=422, detail="PGN exceeds the 250,000-character limit.")

    source = io.StringIO(text)
    try:
        parsed = chess.pgn.read_game(source)
        if parsed is None:
            raise HTTPException(status_code=422, detail="No chess game was found in the PGN.")
        if parsed.errors:
            detail = "; ".join(str(error) for error in parsed.errors[:3])
            raise HTTPException(status_code=422, detail=f"Invalid PGN moves: {detail}")
        if chess.pgn.read_game(source) is not None:
            raise HTTPException(
                status_code=422,
                detail="Only one PGN game can be imported at a time. Remove the other games.",
            )
    except HTTPException:
        raise
    except (ValueError, TypeError, AssertionError) as error:
        raise HTTPException(status_code=422, detail=f"Could not parse PGN: {error}") from error

    original_headers = dict(parsed.headers)
    # python-chess supplies default headers even if the source had none.
    # Track the tags actually present in the input for an honest preview.
    supplied_tags = {
        match.group(1)
        for match in re.finditer(
            r'(?m)^\s*\[([A-Za-z0-9_]+)\s+"(?:\\.|[^"\\])*"\s*\]\s*$',
            text,
        )
    }
    variant = original_headers.get("Variant", "Standard")
    if variant.lower() not in ("standard", "chess", "normal"):
        raise HTTPException(
            status_code=422,
            detail="ChessCV currently imports standard chess only (not Chess960 or chess variants).",
        )

    try:
        board = parsed.board()
        if getattr(board, "chess960", False):
            raise ValueError("Chess960 is not supported by ChessCV.")
        if not board.is_valid():
            raise ValueError("Starting FEN is not a valid standard chess position.")
    except (ValueError, TypeError, AssertionError) as error:
        raise HTTPException(status_code=422, detail=f"Invalid starting position: {error}") from error

    initial_fen = board.fen()
    white = _clean_name(original_headers.get("White", "?"), "White")
    black = _clean_name(original_headers.get("Black", "?"), "Black")
    result = original_headers.get("Result", "*").strip()
    if result not in ("1-0", "0-1", "1/2-1/2", "*"):
        raise HTTPException(status_code=422, detail="PGN Result must be 1-0, 0-1, 1/2-1/2 or *.")

    date_text = original_headers.get("Date", "????.??.??")
    header_values = {
        "Event": original_headers.get("Event", "?") or "?",
        "Date": date_text,
        "Round": original_headers.get("Round", "?") or "?",
        "White": white,
        "Black": black,
        "Result": result,
    }

    # Regenerate the canonical movetext from legal chess moves, rather than
    # trusting SAN text. PGN comments and side variations are intentionally
    # omitted because ChessCV's Games/Analyze follows the mainline only.
    normalized = chess.pgn.Game()
    normalized.headers.clear()
    for tag in KEEP_TAGS:
        normalized.headers[tag] = header_values[tag]

    if initial_fen != chess.STARTING_FEN:
        # Preserve the exact initial position, castling rights and move number.
        normalized.headers["SetUp"] = "1"
        normalized.headers["FEN"] = initial_fen
        header_values["SetUp"] = "1"
        header_values["FEN"] = initial_fen

    node = normalized
    records: list[dict] = []
    for played in parsed.mainline_moves():
        if len(records) >= MAX_PLIES:
            raise HTTPException(status_code=422, detail=f"PGN exceeds {MAX_PLIES} half-moves.")
        if played not in board.legal_moves:
            raise HTTPException(
                status_code=422,
                detail=f"Move {len(records) + 1} ({played.uci()}) is illegal in its position.",
            )
        record = {
            "ply": len(records) + 1,
            "move_number": board.fullmove_number,
            "color": "white" if board.turn == chess.WHITE else "black",
            "uci": played.uci(),
            "san": board.san(played),
            "fen_before": board.fen(),
        }
        board.push(played)
        record["fen_after"] = board.fen()
        records.append(record)
        node = node.add_variation(played)

    if not records:
        raise HTTPException(status_code=422, detail="The PGN contains no moves.")

    normalized_text = normalized.accept(
        chess.pgn.StringExporter(headers=True, variations=False, comments=False)
    ).strip() + "\n"

    eco = (original_headers.get("ECO") or "").strip().upper()
    opening = (original_headers.get("Opening") or "").strip()
    source_eco = eco if ECO_PATTERN.fullmatch(eco) else None
    source_opening = opening[:255] if opening and opening != "?" else None

    # Preserve trusted supplied opening metadata, otherwise use the same
    # opening recognizer as ChessCV's /games/save endpoint.
    if source_eco is None or source_opening is None:
        detected = opening_service.recognize_from_san_moves([r["san"] for r in records])
        eco = source_eco or detected.eco_code
        opening = source_opening or detected.opening_name
    else:
        eco = source_eco
        opening = source_opening

    stored = {}
    if eco:
        stored["ECO"] = eco
    if opening:
        stored["Opening"] = opening

    removed = sorted(
        tag for tag in supplied_tags
        if tag not in KEEP_TAGS and tag not in ("FEN", "SetUp", "ECO", "Opening")
    )
    # Standard starting positions don't need FEN/SetUp in their PGN.
    if initial_fen == chess.STARTING_FEN:
        removed.extend(tag for tag in ("FEN", "SetUp") if tag in supplied_tags)
    if "ECO" in supplied_tags and not stored.get("ECO"):
        removed.append("ECO")
    if "Opening" in supplied_tags and not stored.get("Opening"):
        removed.append("Opening")

    return PreparedGame(
        white=white,
        black=black,
        result=result,
        started_at=_parse_date(date_text),
        initial_fen=initial_fen,
        final_fen=board.fen(),
        pgn=normalized_text,
        eco_code=eco,
        opening_name=opening,
        moves=records,
        headers_kept=header_values,
        headers_database=stored,
        headers_removed=sorted(set(removed)),
    )


def _details(prepared: PreparedGame) -> dict:
    return {
        "white": prepared.white,
        "black": prepared.black,
        "result": prepared.result,
        "total_plies": len(prepared.moves),
        "total_moves": max(move["move_number"] for move in prepared.moves),
        "opening": prepared.opening_name,
        "eco_code": prepared.eco_code,
        "initial_fen": prepared.initial_fen,
        "headers_kept": prepared.headers_kept,
        "headers_database": prepared.headers_database,
        "headers_removed": prepared.headers_removed,
        "normalized_pgn": prepared.pgn,
        "analysis_supported": len(prepared.moves) <= 400,
    }


def _get_player(db: Session, name: str) -> Player:
    found = db.scalar(
        select(Player).where(func.lower(Player.name) == name.lower()).limit(1)
    )
    if found is not None:
        return found
    created = Player(name=name)
    db.add(created)
    db.flush()
    return created


def _existing_id(db: Session, prepared: PreparedGame, white_id: int, black_id: int) -> int | None:
    candidates = db.scalars(
        select(Game).where(
            Game.white_player_id == white_id,
            Game.black_player_id == black_id,
            Game.result == prepared.result,
            Game.initial_fen == prepared.initial_fen,
            Game.final_fen == prepared.final_fen,
            Game.total_moves == max(record["move_number"] for record in prepared.moves),
        )
    ).all()
    wanted_uci = [record["uci"] for record in prepared.moves]
    for candidate in candidates:
        sequence = db.scalars(
            select(Move.uci)
            .where(Move.game_id == candidate.id)
            .order_by(Move.ply.asc())
        ).all()
        if list(sequence) == wanted_uci:
            return candidate.id
    return None


@router.post("/preview")
def preview_pgn(payload: PgnInput) -> dict:
    """Validate and show exactly what would be saved. No database writes."""
    return _details(_prepare(payload.pgn))


@router.post("/import")
def import_pgn(payload: PgnInput, db: Session = Depends(get_db)) -> dict:
    """Atomically import one game, or return its existing ID if duplicated."""
    prepared = _prepare(payload.pgn)
    try:
        white = _get_player(db, prepared.white)
        black = _get_player(db, prepared.black)
        existing_id = _existing_id(db, prepared, white.id, black.id)
        if existing_id is not None:
            db.rollback()  # Import did not make any persistent changes.
            return {"saved": False, "duplicate": True, "game_id": existing_id, **_details(prepared)}

        game = Game(
            white_player_id=white.id,
            black_player_id=black.id,
            initial_fen=prepared.initial_fen,
            final_fen=prepared.final_fen,
            pgn=prepared.pgn,
            result=prepared.result,
            termination=None,
            opening_name=prepared.opening_name,
            eco_code=prepared.eco_code,
            total_moves=max(record["move_number"] for record in prepared.moves),
            started_at=prepared.started_at,
            ended_at=None,
        )
        db.add(game)
        db.flush()
        db.add_all(Move(game_id=game.id, **record) for record in prepared.moves)
        db.commit()
        return {"saved": True, "duplicate": False, "game_id": game.id, **_details(prepared)}
    except HTTPException:
        db.rollback()
        raise
    except Exception as error:
        db.rollback()
        print(f"PGN import database error ({type(error).__name__}): {error}")
        raise HTTPException(status_code=500, detail="Database import failed. Check backend logs.") from error
"""Stockfish review of games already saved in MySQL.

Uses a separate, full-strength UCI process so the 1800-Elo live bot
keeps its own settings. Analysis results are not written to the database.
"""

from __future__ import annotations

import math
from pathlib import Path

import chess
import chess.engine
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.database.db import get_db
from backend.app.database.models.game import Game
from backend.app.database.models.move import Move


router = APIRouter(prefix="/games", tags=["Game Analysis"])
ANALYSIS_SECONDS_PER_POSITION = 0.15
MAX_ANALYSIS_PLIES = 400


def _win_chance(cp: int) -> float:
    """Smooth CP-to-win-chance approximation, not Chess.com accuracy."""
    return 1.0 / (1.0 + math.exp(-max(-2000, min(2000, cp)) / 220.0))


def _classification(
    best_uci: str | None,
    played_uci: str,
    loss: float,
) -> str:
    if best_uci == played_uci:
        return "best"
    if loss < 0.025:
        return "excellent"
    if loss < 0.075:
        return "good"
    if loss < 0.15:
        return "inaccuracy"
    if loss < 0.30:
        return "mistake"
    return "blunder"


def _evaluation(info: dict) -> tuple[int, int | None]:
    score = info["score"].white()
    return int(score.score(mate_score=100000) or 0), score.mate()


@router.post("/{game_id}/analyze")
def analyze_saved_game(
    game_id: int,
    db: Session = Depends(get_db),
) -> dict:
    game = db.get(Game, game_id)

    if game is None:
        raise HTTPException(
            status_code=404,
            detail="Game not found.",
        )

    saved_moves = db.scalars(
        select(Move)
        .where(Move.game_id == game_id)
        .order_by(Move.ply.asc())
    ).all()

    if not saved_moves:
        raise HTTPException(
            status_code=422,
            detail="This game has no saved moves to analyze.",
        )

    if len(saved_moves) > MAX_ANALYSIS_PLIES:
        raise HTTPException(
            status_code=422,
            detail=(
                "Analysis currently supports up to "
                f"{MAX_ANALYSIS_PLIES} half-moves."
            ),
        )

    # Validate ALL stored moves first.
    # Never analyze a corrupted move sequence.

    try:
        board = chess.Board(game.initial_fen)

        for index, item in enumerate(saved_moves, start=1):
            move = chess.Move.from_uci(item.uci)

            if move not in board.legal_moves:
                raise ValueError(
                    f"Saved move {index} ({item.uci}) is not legal."
                )

            board.push(move)

    except (ValueError, AssertionError) as error:
        raise HTTPException(
            status_code=422,
            detail=f"Saved game cannot be replayed: {error}",
        ) from error

    engine_path = (
        Path(settings.STOCKFISH_PATH)
        .expanduser()
        .resolve()
    )

    if not engine_path.is_file():
        raise HTTPException(
            status_code=503,
            detail=(
                f"Stockfish executable not found at {engine_path}. "
                "Install Stockfish first."
            ),
        )

    engine = None

    try:
        # Separate process: do not modify the live 1800-Elo bot.

        engine = chess.engine.SimpleEngine.popen_uci(
            str(engine_path),
            timeout=15.0,
        )

        options = {}

        if "Threads" in engine.options:
            options["Threads"] = 1

        if "Hash" in engine.options:
            options["Hash"] = 64

        if "UCI_LimitStrength" in engine.options:
            options["UCI_LimitStrength"] = False

        if options:
            engine.configure(options)

        board = chess.Board(game.initial_fen)

        limit = chess.engine.Limit(
            time=ANALYSIS_SECONDS_PER_POSITION
        )

        # Analyze every position, including the initial one.

        before_info = engine.analyse(board, limit)

        initial_cp, initial_mate = _evaluation(before_info)

        reviewed = []

        scores = {
            "white": [],
            "black": [],
        }

        counts = {
            "white": {
                name: 0
                for name in (
                    "best",
                    "excellent",
                    "good",
                    "inaccuracy",
                    "mistake",
                    "blunder",
                )
            },
            "black": {
                name: 0
                for name in (
                    "best",
                    "excellent",
                    "good",
                    "inaccuracy",
                    "mistake",
                    "blunder",
                )
            },
        }

        for item in saved_moves:
            mover = (
                "white"
                if board.turn == chess.WHITE
                else "black"
            )

            perspective = (
                chess.WHITE
                if mover == "white"
                else chess.BLACK
            )

            best_score = int(
                before_info["score"]
                .pov(perspective)
                .score(mate_score=100000)
                or 0
            )

            pv = before_info.get("pv", [])

            best_move = (
                pv[0]
                if pv and pv[0] in board.legal_moves
                else None
            )

            best_uci = (
                best_move.uci()
                if best_move
                else None
            )

            best_san = (
                board.san(best_move)
                if best_move
                else None
            )

            played = chess.Move.from_uci(item.uci)
            board.push(played)

            after_info = engine.analyse(board, limit)

            actual_score = int(
                after_info["score"]
                .pov(perspective)
                .score(mate_score=100000)
                or 0
            )

            cp, mate = _evaluation(after_info)

            # Classification uses change in estimated win chance,
            # instead of only raw centipawn loss.

            loss = max(
                0.0,
                _win_chance(best_score)
                - _win_chance(actual_score),
            )

            classification = _classification(
                best_uci,
                item.uci,
                loss,
            )

            accuracy = round(
                100.0 * math.exp(-3.0 * loss),
                1,
            )

            scores[mover].append(accuracy)
            counts[mover][classification] += 1

            reviewed.append({
                "ply": item.ply,
                "move_number": item.move_number,
                "color": mover,
                "uci": item.uci,
                "san": item.san,
                "fen_after": board.fen(),
                "best_uci": best_uci,
                "best_san": best_san,
                "evaluation_cp": cp,
                "evaluation_mate": mate,
                "win_chance_loss": round(loss, 4),
                "accuracy": accuracy,
                "classification": classification,
            })

            before_info = after_info

        return {
            "game_id": game_id,
            "engine": "Stockfish (full strength)",
            "seconds_per_position": ANALYSIS_SECONDS_PER_POSITION,
            "method": (
                "Approximate win-chance-loss labels; "
                "not Chess.com Game Review."
            ),
            "initial_evaluation_cp": initial_cp,
            "initial_evaluation_mate": initial_mate,
            "moves": reviewed,
            "summary": {
                color: {
                    "accuracy": (
                        round(
                            sum(scores[color]) / len(scores[color]),
                            1,
                        )
                        if scores[color]
                        else None
                    ),
                    "counts": counts[color],
                }
                for color in ("white", "black")
            },
        }

    except (
        chess.engine.EngineError,
        chess.engine.EngineTerminatedError,
        OSError,
        TimeoutError,
    ) as error:
        raise HTTPException(
            status_code=503,
            detail=f"Stockfish analysis failed: {error}",
        ) from error

    finally:
        if engine is not None:
            try:
                engine.quit()
            except Exception:
                pass
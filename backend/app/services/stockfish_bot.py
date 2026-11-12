"""Reusable UCI Stockfish opponent targeting roughly 1800 Elo.

Stockfish itself is distributed separately; set STOCKFISH_PATH in .env.
The engine is started lazily and shared across requests under a lock.
"""

from __future__ import annotations

import threading
from pathlib import Path

import chess
import chess.engine

from backend.app.core.config import settings


class BotUnavailableError(RuntimeError):
    """An external UCI engine could not be used."""


class StockfishBot:
    name = "Stockfish Bot"
    estimated_rating = 1800

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._engine: chess.engine.SimpleEngine | None = None

    def _configured_path(self) -> Path:
        return Path(settings.STOCKFISH_PATH).expanduser().resolve()

    def _close_engine_locked(self) -> None:
        engine, self._engine = self._engine, None

        if engine is not None:
            try:
                engine.quit()
            except Exception:
                pass

    def _ensure_engine_locked(self) -> chess.engine.SimpleEngine:
        if self._engine is not None:
            return self._engine

        path = self._configured_path()

        if not path.is_file():
            raise BotUnavailableError(
                "Stockfish executable not found: "
                f"{path}. Download Stockfish and set STOCKFISH_PATH in .env."
            )

        engine = None

        try:
            engine = chess.engine.SimpleEngine.popen_uci(
                str(path),
                timeout=10.0,
            )

            required = {
                "UCI_LimitStrength",
                "UCI_Elo",
            }

            if not required.issubset(engine.options):
                raise BotUnavailableError(
                    "This UCI engine does not support UCI_LimitStrength and "
                    "UCI_Elo. Please use a current Stockfish release."
                )

            engine.configure({
                "Threads": 1,
                "Hash": 32,
                "UCI_LimitStrength": True,
                "UCI_Elo": self.estimated_rating,
            })

        except (
            OSError,
            chess.engine.EngineError,
            TimeoutError,
            BotUnavailableError,
        ) as error:

            if engine is not None:
                try:
                    engine.quit()
                except Exception:
                    pass

            raise BotUnavailableError(
                f"Could not initialize Stockfish at {path}: {error}"
            ) from error

        self._engine = engine
        return engine

    def ensure_ready(self) -> None:
        with self._lock:
            self._ensure_engine_locked()

    def choose_move(self, board: chess.Board) -> dict:
        if board.is_game_over(claim_draw=True):
            raise ValueError(
                "Cannot choose a bot move: game is already over."
            )

        with self._lock:
            engine = self._ensure_engine_locked()

            try:
                result = engine.play(
                    board.copy(stack=True),
                    chess.engine.Limit(time=0.7),
                )

            except (
                OSError,
                chess.engine.EngineError,
                TimeoutError,
            ) as error:

                self._close_engine_locked()

                raise BotUnavailableError(
                    f"Stockfish could not calculate a move: {error}"
                ) from error

            move = result.move

            if move is None or move not in board.legal_moves:
                self._close_engine_locked()

                raise BotUnavailableError(
                    "Stockfish returned no legal move. Restart the engine."
                )

            return {
                "move": move,
                "uci": move.uci(),
                "san": board.san(move),
                "estimated_rating": self.estimated_rating,
                "name": self.name,
            }

    def shutdown(self) -> None:
        with self._lock:
            self._close_engine_locked()


stockfish_bot = StockfishBot()
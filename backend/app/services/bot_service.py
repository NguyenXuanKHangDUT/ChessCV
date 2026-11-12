"""Common dispatch layer for chess opponents."""

from __future__ import annotations

import chess

from backend.app.services.beginner_bot import beginner_bot
from backend.app.services.stockfish_bot import stockfish_bot


BOT_NAMES = {
    "beginner": "Beginner Bot",
    "stockfish_1800": "Stockfish Bot",
}


class BotService:
    def validate_bot_type(self, bot_type: str) -> None:
        if bot_type not in BOT_NAMES:
            raise ValueError(
                "bot_type must be beginner or stockfish_1800"
            )

    def get_name(self, bot_type: str) -> str:
        self.validate_bot_type(bot_type)
        return BOT_NAMES[bot_type]

    def ensure_ready(self, bot_type: str) -> None:
        self.validate_bot_type(bot_type)

        if bot_type == "stockfish_1800":
            stockfish_bot.ensure_ready()

    def choose_move(
        self,
        board: chess.Board,
        bot_type: str = "beginner",
    ) -> dict:

        self.validate_bot_type(bot_type)

        if bot_type == "stockfish_1800":
            return stockfish_bot.choose_move(board)

        return beginner_bot.choose_move(board)

    def shutdown(self) -> None:
        stockfish_bot.shutdown()


bot_service = BotService()
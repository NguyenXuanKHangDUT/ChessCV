from __future__ import annotations

import chess

from fastapi import (
    APIRouter,
    HTTPException,
)

from pydantic import (
    BaseModel,
)
from typing import Literal

from backend.app.services.bot_service import bot_service
from backend.app.services.stockfish_bot import BotUnavailableError


router = APIRouter(
    prefix="/bot",
    tags=[
        "Chess Bot",
    ],
)


# ============================================================
# REQUEST
# ============================================================

class BotMoveRequest(
    BaseModel
):

    fen: str
    bot_type: Literal["beginner", "stockfish_1800", "stockfish_2800"] = "beginner"


# ============================================================
# RESPONSE
# ============================================================

class BotMoveResponse(
    BaseModel
):

    bot_name: str

    estimated_rating: int

    uci: str

    san: str


# ============================================================
# BOT MOVE
# ============================================================

@router.post(
    "/move",
    response_model=
        BotMoveResponse,
)
def get_bot_move(
    payload: BotMoveRequest,
):

    # ========================================================
    # FEN
    # ========================================================

    try:

        board = (
            chess.Board(
                payload.fen
            )
        )


    except ValueError as error:

        raise HTTPException(
            status_code=
                422,

            detail=
                f"Invalid FEN: {error}",
        ) from error


    # ========================================================
    # GAME OVER
    # ========================================================

    if board.is_game_over(
        claim_draw=True
    ):

        raise HTTPException(
            status_code=
                409,

            detail=
                "Game is already over.",
        )


    # ========================================================
    # CHOOSE MOVE
    # ========================================================

    try:

        result = (
            bot_service
            .choose_move(
                board,
                bot_type=payload.bot_type,
            )
        )


    except ValueError as error:

        raise HTTPException(
            status_code=409,
            detail=str(error),
        ) from error

    except BotUnavailableError as error:

        raise HTTPException(
            status_code=503,
            detail=str(error),
        ) from error


    # ========================================================
    # RESULT
    # ========================================================

    return BotMoveResponse(

        bot_name=
            result[
                "name"
            ],

        estimated_rating=
            result[
                "estimated_rating"
            ],

        uci=
            result[
                "uci"
            ],

        san=
            result[
                "san"
            ],
    )
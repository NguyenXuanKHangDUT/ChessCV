from __future__ import annotations

from datetime import (
    datetime,
)

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
)

from pydantic import (
    BaseModel,
    Field,
)

from sqlalchemy import (
    func,
    select,
)

from sqlalchemy.orm import (
    Session,
    aliased,
)

from backend.app.database.db import (
    get_db,
)

from backend.app.database.models.game import (
    Game,
)

from backend.app.database.models.move import (
    Move,
)

from backend.app.database.models.player import (
    Player,
)

from backend.app.services.opening_service import (
    opening_service,
)


router = APIRouter(
    prefix="/games",
    tags=[
        "Games",
    ],
)


# ============================================================
# MOVE INPUT
# ============================================================

class SavedMoveInput(
    BaseModel
):

    ply: int

    move_number: int

    color: str

    uci: str

    san: str

    fen_before: str

    fen_after: str


# ============================================================
# SAVE GAME INPUT
# ============================================================

class SaveGameRequest(
    BaseModel
):

    white_name: str = Field(
        min_length=1,
        max_length=100,
    )


    black_name: str = Field(
        min_length=1,
        max_length=100,
    )


    initial_fen: str

    final_fen: str

    pgn: str


    result: str = "*"


    termination: (
        str
        |
        None
    ) = None


    started_at: (
        datetime
        |
        None
    ) = None


    ended_at: (
        datetime
        |
        None
    ) = None


    moves: list[
        SavedMoveInput
    ] = Field(
        default_factory=list
    )


# ============================================================
# PLAYER NAME
# ============================================================

def _clean_player_name(
    name: str,
) -> str:

    cleaned = (
        " ".join(
            name
            .strip()
            .split()
        )
    )


    if not cleaned:

        raise HTTPException(
            status_code=
                422,

            detail=
                "Player name cannot be empty.",
        )


    return cleaned


# ============================================================
# GET OR CREATE PLAYER
# ============================================================

def _get_or_create_player(
    db: Session,
    name: str,
) -> Player:

    cleaned = (
        _clean_player_name(
            name
        )
    )


    existing = (
        db.scalar(

            select(
                Player
            )

            .where(
                func.lower(
                    Player.name
                )
                ==
                cleaned.lower()
            )

            .limit(
                1
            )
        )
    )


    if existing is not None:

        return existing


    player = (
        Player(
            name=
                cleaned
        )
    )


    db.add(
        player
    )


    db.flush()


    return player


# ============================================================
# SERIALIZE HISTORY ROW
# ============================================================

def _serialize_game_row(
    game: Game,
    white_name: (
        str
        |
        None
    ),
    black_name: (
        str
        |
        None
    ),
) -> dict:

    game_date = (
        game.started_at
        or
        game.created_at
    )


    return {
        "id":
            game.id,

        "date":
            (
                game_date.isoformat()
                if game_date
                else None
            ),

        "white":
            (
                white_name
                or
                "White"
            ),

        "black":
            (
                black_name
                or
                "Black"
            ),

        "result":
            game.result,

        "opening":
            game.opening_name,

        "eco_code":
            game.eco_code,

        "moves":
            game.total_moves,
    }


# ============================================================
# SAVE COMPLETED GAME
# ============================================================

@router.post(
    "/save"
)
def save_game(
    payload: SaveGameRequest,

    db: Session = Depends(
        get_db
    ),
):

    try:

        # ====================================================
        # PLAYERS
        # ====================================================

        white_player = (
            _get_or_create_player(
                db,
                payload.white_name,
            )
        )


        black_player = (
            _get_or_create_player(
                db,
                payload.black_name,
            )
        )


        # ====================================================
        # OPENING
        # ====================================================
        #
        # IMPORTANT:
        #
        # Opening recognition happens ONLY here.
        #
        # Live Game does not continuously calculate ECO.
        #
        # ====================================================

        opening = (
            opening_service
            .recognize_from_san_moves(
                [
                    move.san

                    for move
                    in payload.moves
                ]
            )
        )


        # ====================================================
        # FULL MOVE COUNT
        # ====================================================

        total_moves = 0


        if payload.moves:

            total_moves = max(
                move.move_number

                for move
                in payload.moves
            )


        # ====================================================
        # GAME
        # ====================================================

        game = (
            Game(

                white_player_id=
                    white_player.id,

                black_player_id=
                    black_player.id,


                initial_fen=
                    payload.initial_fen,

                final_fen=
                    payload.final_fen,

                pgn=
                    payload.pgn,


                result=
                    payload.result,

                termination=
                    payload.termination,


                opening_name=
                    opening.opening_name,

                eco_code=
                    opening.eco_code,


                total_moves=
                    total_moves,


                started_at=
                    payload.started_at,

                ended_at=
                    (
                        payload.ended_at
                        or
                        datetime.utcnow()
                    ),
            )
        )


        db.add(
            game
        )


        db.flush()


        # ====================================================
        # MOVES
        # ====================================================

        for move_data in (
            payload.moves
        ):

            move = (
                Move(

                    game_id=
                        game.id,

                    ply=
                        move_data.ply,

                    move_number=
                        move_data.move_number,

                    color=
                        move_data.color,

                    uci=
                        move_data.uci,

                    san=
                        move_data.san,

                    fen_before=
                        move_data.fen_before,

                    fen_after=
                        move_data.fen_after,
                )
            )


            db.add(
                move
            )


        # ====================================================
        # COMMIT
        # ====================================================

        db.commit()


        db.refresh(
            game
        )


        return {
            "saved":
                True,

            "game_id":
                game.id,

            "opening":
                game.opening_name,

            "eco_code":
                game.eco_code,
        }


    except HTTPException:

        db.rollback()

        raise


    except Exception as error:

        db.rollback()


        raise HTTPException(
            status_code=
                500,

            detail=
                f"Could not save game: {error}",
        ) from error


# ============================================================
# GAMES HISTORY
# ============================================================

@router.get(
    ""
)
def list_games(
    db: Session = Depends(
        get_db
    ),
):

    white_player = aliased(
        Player
    )


    black_player = aliased(
        Player
    )


    rows = (
        db.execute(

            select(

                Game,

                white_player.name.label(
                    "white_name"
                ),

                black_player.name.label(
                    "black_name"
                ),
            )

            .outerjoin(

                white_player,

                Game.white_player_id
                ==
                white_player.id,
            )

            .outerjoin(

                black_player,

                Game.black_player_id
                ==
                black_player.id,
            )

            .order_by(

                Game.created_at.desc(),

                Game.id.desc(),
            )
        )

        .all()
    )


    return [

        _serialize_game_row(
            game,
            white_name,
            black_name,
        )

        for (
            game,
            white_name,
            black_name,
        )
        in rows
    ]


# ============================================================
# GAME DETAIL
# ============================================================

@router.get(
    "/{game_id}"
)
def get_game(
    game_id: int,

    db: Session = Depends(
        get_db
    ),
):

    white_player = aliased(
        Player
    )


    black_player = aliased(
        Player
    )


    row = (
        db.execute(

            select(

                Game,

                white_player.name.label(
                    "white_name"
                ),

                black_player.name.label(
                    "black_name"
                ),
            )

            .outerjoin(

                white_player,

                Game.white_player_id
                ==
                white_player.id,
            )

            .outerjoin(

                black_player,

                Game.black_player_id
                ==
                black_player.id,
            )

            .where(
                Game.id
                ==
                game_id
            )

            .limit(
                1
            )
        )

        .first()
    )


    if row is None:

        raise HTTPException(
            status_code=
                404,

            detail=
                "Game not found.",
        )


    (
        game,
        white_name,
        black_name,
    ) = row


    moves = (
        db.scalars(

            select(
                Move
            )

            .where(
                Move.game_id
                ==
                game_id
            )

            .order_by(
                Move.ply.asc()
            )
        )

        .all()
    )


    return {
        **_serialize_game_row(
            game,
            white_name,
            black_name,
        ),

        "initial_fen":
            game.initial_fen,

        "final_fen":
            game.final_fen,

        "pgn":
            game.pgn,

        "termination":
            game.termination,

        "started_at":
            (
                game.started_at
                .isoformat()

                if game.started_at

                else None
            ),

        "ended_at":
            (
                game.ended_at
                .isoformat()

                if game.ended_at

                else None
            ),

        "move_list":
            [
                {
                    "ply":
                        move.ply,

                    "move_number":
                        move.move_number,

                    "color":
                        move.color,

                    "uci":
                        move.uci,

                    "san":
                        move.san,

                    "fen_before":
                        move.fen_before,

                    "fen_after":
                        move.fen_after,
                }

                for move
                in moves
            ],
    }


# ============================================================
# OPENING SERVICE STATUS
# ============================================================

@router.get(
    "/opening/status/service"
)
def opening_status():

    return (
        opening_service
        .get_status()
    )
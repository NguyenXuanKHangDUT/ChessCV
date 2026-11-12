from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text
)

from sqlalchemy.orm import (
    Mapped,
    mapped_column
)

from backend.app.database.db import Base


class Game(Base):

    __tablename__ = "games"


    # ========================================================
    # ID
    # ========================================================

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True
    )


    # ========================================================
    # PLAYERS
    # ========================================================

    white_player_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "players.id",
            ondelete="SET NULL"
        ),
        nullable=True,
        index=True
    )


    black_player_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "players.id",
            ondelete="SET NULL"
        ),
        nullable=True,
        index=True
    )


    # ========================================================
    # BOARD STATE
    # ========================================================

    initial_fen: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )


    final_fen: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True
    )


    pgn: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )


    # ========================================================
    # RESULT
    # ========================================================

    result: Mapped[str] = mapped_column(
        String(20),
        default="*",
        nullable=False
    )


    termination: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True
    )


    # ========================================================
    # OPENING
    # ========================================================

    opening_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True
    )


    eco_code: Mapped[str | None] = mapped_column(
        String(10),
        nullable=True
    )


    # ========================================================
    # MOVE COUNT
    # ========================================================

    total_moves: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False
    )


    # ========================================================
    # TIME
    # ========================================================

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True
    )


    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True
    )


    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String
)

from sqlalchemy.orm import (
    Mapped,
    mapped_column
)

from backend.app.database.db import Base


class Move(Base):

    __tablename__ = "moves"


    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True
    )


    game_id: Mapped[int] = mapped_column(
        ForeignKey(
            "games.id",
            ondelete="CASCADE"
        ),
        nullable=False,
        index=True
    )


    # half-move number
    # 1.e4 = ply 1
    # 1...e5 = ply 2
    ply: Mapped[int] = mapped_column(
        Integer,
        nullable=False
    )


    move_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False
    )


    color: Mapped[str] = mapped_column(
        String(10),
        nullable=False
    )


    # e2e4
    uci: Mapped[str] = mapped_column(
        String(10),
        nullable=False
    )


    # e4 / Nf3 / O-O / Qh7#
    san: Mapped[str] = mapped_column(
        String(30),
        nullable=False
    )


    fen_before: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )


    fen_after: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )


    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )
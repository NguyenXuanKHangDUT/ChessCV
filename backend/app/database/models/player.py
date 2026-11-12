from datetime import datetime

from sqlalchemy import (
    DateTime,
    String
)

from sqlalchemy.orm import (
    Mapped,
    mapped_column
)

from backend.app.database.db import Base


class Player(Base):

    __tablename__ = "players"


    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True
    )


    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True
    )


    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )
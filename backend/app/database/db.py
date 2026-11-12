from __future__ import annotations

from sqlalchemy import (
    create_engine,
)

from sqlalchemy.orm import (
    DeclarativeBase,
    sessionmaker,
)

from backend.app.core.config import (
    settings,
)


# ============================================================
# BASE
# ============================================================

class Base(
    DeclarativeBase
):

    pass


# ============================================================
# ENGINE
# ============================================================
#
# DATABASE_URL được đọc từ:
#
# B:\PBL4_ChessCV\.env
#
# Ví dụ:
#
# mysql+pymysql://root:PASSWORD@127.0.0.1:3306/chesscv
#
# Backend KHÔNG tạo database ở đây.
#
# Database chesscv phải tồn tại sẵn.
#
# ============================================================

engine = (
    create_engine(

        settings.DATABASE_URL,

        pool_pre_ping=
            True,

        echo=
            False,
    )
)


# ============================================================
# SESSION
# ============================================================

SessionLocal = (
    sessionmaker(

        bind=
            engine,

        autoflush=
            False,

        autocommit=
            False,
    )
)


# ============================================================
# FASTAPI DATABASE DEPENDENCY
# ============================================================

def get_db():

    db = (
        SessionLocal()
    )


    try:

        yield db


    finally:

        db.close()
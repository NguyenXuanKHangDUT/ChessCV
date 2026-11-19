
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.health import router as health_router
from backend.app.api.positions import router as positions_router
from backend.app.api.camera import router as camera_router
from backend.app.api.live_game import router as live_game_router
from backend.app.api.bot import router as bot_router
from backend.app.api.games import router as games_router
from backend.app.api.calibration import router as calibration_router
from backend.app.api.game_analysis import router as game_analysis_router
from backend.app.api.voice import router as voice_router
from backend.app.api.pgn_import import router as pgn_import_router

from backend.app.core.config import settings
from backend.app.services.bot_service import bot_service


# ============================================================
# LIFESPAN
# ============================================================

@asynccontextmanager
async def lifespan(_app: FastAPI):

    try:
        yield

    finally:
        bot_service.shutdown()


# ============================================================
# APP
# ============================================================

app = FastAPI(
    title=settings.APP_NAME,
    version="0.6.1",
    lifespan=lifespan,
)


# ============================================================
# CORS
# ============================================================

app.add_middleware(
    CORSMiddleware,

    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],

    allow_credentials=True,

    allow_methods=["*"],

    allow_headers=["*"],
)


# ============================================================
# ROUTERS
# ============================================================

app.include_router(
    health_router,
    prefix=settings.API_PREFIX,
)

app.include_router(
    positions_router,
    prefix=settings.API_PREFIX,
)

app.include_router(
    camera_router,
    prefix=settings.API_PREFIX,
)

app.include_router(
    live_game_router,
    prefix=settings.API_PREFIX,
)

app.include_router(
    bot_router,
    prefix=settings.API_PREFIX,
)

app.include_router(
    games_router,
    prefix=settings.API_PREFIX,
)

app.include_router(
    calibration_router,
    prefix=settings.API_PREFIX,
)

app.include_router(
    game_analysis_router,
    prefix=settings.API_PREFIX,
)

app.include_router(
    voice_router,
    prefix=settings.API_PREFIX,
)

app.include_router(
    pgn_import_router,
    prefix=settings.API_PREFIX,
)


# ============================================================
# ROOT
# ============================================================

@app.get("/")
def root():

    return {
        "name": settings.APP_NAME,
        "status": "running",
        "version": "0.6.1",
        "api": settings.API_PREFIX,
        "docs": "/docs",
    }

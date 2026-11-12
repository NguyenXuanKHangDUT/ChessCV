from pathlib import Path

from pydantic_settings import (
    BaseSettings,
    SettingsConfigDict,
)


# ============================================================
# PROJECT ROOT
# ============================================================

PROJECT_ROOT = (
    Path(__file__)
    .resolve()
    .parents[3]
)


# ============================================================
# SETTINGS
# ============================================================

class Settings(BaseSettings):

    # ========================================================
    # APP
    # ========================================================

    APP_NAME: str = "PBL4 ChessCV"

    API_PREFIX: str = "/api"


    # ========================================================
    # DATABASE
    # ========================================================
    #
    # DATABASE_URL phải được lấy từ:
    #
    # B:\PBL4_ChessCV\.env
    #
    # ========================================================

    DATABASE_URL: str


    # ========================================================
    # CAMERA
    # ========================================================

    CAMERA_RTSP_URL: str = ""


    # ========================================================
    # STOCKFISH BOT
    # ========================================================

    STOCKFISH_PATH: Path = (
        PROJECT_ROOT
        / "engines"
        / "stockfish"
        / "stockfish.exe"
    )


    # ========================================================
    # OCCUPANCY MODEL
    # ========================================================

    OCCUPANCY_MODEL_PATH: Path = (
        PROJECT_ROOT
        / "models"
        / "occupancy"
        / "resnet18_occupancy_best.pt"
    )


    # ========================================================
    # PIECE MODEL
    # ========================================================

    PIECE_MODEL_PATH: Path = (
        PROJECT_ROOT
        / "models"
        / "pieces"
        / "convnext_tiny_pieces_best.pt"
    )


    # ========================================================
    # ENV CONFIG
    # ========================================================

    model_config = SettingsConfigDict(

        env_file=(
            PROJECT_ROOT
            / ".env"
        ),

        env_file_encoding=
            "utf-8",

        extra=
            "ignore",
    )


# ============================================================
# SINGLETON
# ============================================================

settings = Settings()
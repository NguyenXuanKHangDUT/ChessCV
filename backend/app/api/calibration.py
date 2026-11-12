from __future__ import annotations

import json
import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.app.services.camera_service import camera_service
from backend.app.services.live_game_service import live_game_service


router = APIRouter(
    prefix="/calibration",
    tags=["Fixed Board Calibration"],
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
CALIBRATION_PATH = PROJECT_ROOT / "config" / "calibration.json"
BOARD_SIZE = 800


class SaveCalibrationRequest(BaseModel):
    camera_width: int = Field(gt=0)
    camera_height: int = Field(gt=0)
    source_points: list[list[float]]


@router.post("/fixed")
def save_fixed_calibration(payload: SaveCalibrationRequest):
    """
    Save the same calibration format as src/calibration.py,
    without opening a desktop OpenCV window.
    """

    # Do not change the physical board geometry mid-game.
    if live_game_service.get_state()["running"]:
        raise HTTPException(
            status_code=409,
            detail=(
                "Stop the current Live Game "
                "before changing calibration."
            ),
        )

    # Get the same working frame used by Live Game.
    try:
        frame = camera_service.get_frame(timeout=3.0)

    except RuntimeError as error:
        raise HTTPException(
            status_code=503,
            detail=str(error),
        ) from error

    height, width = frame.shape[:2]

    if (
        payload.camera_width,
        payload.camera_height,
    ) != (width, height):

        raise HTTPException(
            status_code=409,
            detail=(
                "Camera frame size changed. "
                f"Current frame is {width}x{height}; "
                "freeze a new frame and select the corners again."
            ),
        )

    # Validate exactly four selected points.
    if (
        len(payload.source_points) != 4
        or any(
            len(point) != 2
            for point in payload.source_points
        )
    ):
        raise HTTPException(
            status_code=422,
            detail=(
                "Select exactly four points "
                "in TL -> TR -> BR -> BL order."
            ),
        )

    points = np.asarray(
        payload.source_points,
        dtype=np.float32,
    )

    if not np.isfinite(points).all():
        raise HTTPException(
            status_code=422,
            detail="Corner coordinates must be finite.",
        )

    # Coordinates must belong to the actual camera frame.
    if (
        np.any(points[:, 0] < 0)
        or np.any(points[:, 0] >= width)
        or np.any(points[:, 1] < 0)
        or np.any(points[:, 1] >= height)
    ):
        raise HTTPException(
            status_code=422,
            detail=(
                "All four corners must be "
                "within the camera frame."
            ),
        )

    # Reject invalid or self-crossing quadrilaterals.
    if not cv2.isContourConvex(
        points.reshape(-1, 1, 2)
    ):
        raise HTTPException(
            status_code=422,
            detail=(
                "The four corners must form "
                "a non-crossing convex board."
            ),
        )

    # Same minimum board area policy as src/calibration.py.
    area = abs(
        float(cv2.contourArea(points))
    )

    if area < width * height * 0.05:
        raise HTTPException(
            status_code=422,
            detail=(
                "Selected board region is too small "
                "(less than 5% of the frame)."
            ),
        )

    # Map physical corners to an 800x800 board.
    destination = np.asarray(
        [
            [0, 0],
            [BOARD_SIZE - 1, 0],
            [BOARD_SIZE - 1, BOARD_SIZE - 1],
            [0, BOARD_SIZE - 1],
        ],
        dtype=np.float32,
    )

    homography = cv2.getPerspectiveTransform(
        points,
        destination,
    )

    if not np.isfinite(homography).all():
        raise HTTPException(
            status_code=422,
            detail="Invalid board perspective.",
        )

    # Same JSON structure expected by fixed_calibration.py.
    config = {
        "camera_width": width,
        "camera_height": height,
        "board_size": BOARD_SIZE,
        "point_order": "TL_TR_BR_BL",
        "camera_source": "rtsp",
        "source_points": points.tolist(),
        "homography": homography.tolist(),
        "created_at": datetime.now().isoformat(
            timespec="seconds"
        ),
    }

    CALIBRATION_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temp_path: Path | None = None

    try:
        # Write a temporary file and replace atomically.
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=CALIBRATION_PATH.parent,
            prefix="calibration_",
            suffix=".tmp",
            delete=False,
        ) as handle:

            temp_path = Path(handle.name)

            json.dump(
                config,
                handle,
                ensure_ascii=False,
                indent=4,
            )

            handle.flush()
            os.fsync(handle.fileno())

        # Preserve previous calibration.
        if CALIBRATION_PATH.exists():
            shutil.copy2(
                CALIBRATION_PATH,
                CALIBRATION_PATH.with_suffix(
                    ".json.bak"
                ),
            )

        os.replace(
            temp_path,
            CALIBRATION_PATH,
        )

    except OSError as error:
        raise HTTPException(
            status_code=500,
            detail=(
                "Could not save calibration.json: "
                f"{error}"
            ),
        ) from error

    finally:
        if temp_path is not None:
            temp_path.unlink(
                missing_ok=True
            )

    return {
        "saved": True,
        "path": str(CALIBRATION_PATH),
        "camera_width": width,
        "camera_height": height,
        "source_points": config["source_points"],
        "created_at": config["created_at"],
    }
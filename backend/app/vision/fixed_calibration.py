from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np


# ============================================================
# PATHS / CONSTANTS
# ============================================================

PROJECT_ROOT = (
    Path(__file__)
    .resolve()
    .parents[3]
)


CALIBRATION_PATH = (
    PROJECT_ROOT
    / "config"
    / "calibration.json"
)


BOARD_SIZE = 800


OUTER_SCALE = 1.18


MIN_BOARD_AREA_RATIO = 0.03


# ============================================================
# LOAD CONFIG
# ============================================================

def _load_config() -> dict:

    if not CALIBRATION_PATH.exists():

        raise RuntimeError(
            "Fixed board calibration is missing. "
            f"Expected file: {CALIBRATION_PATH}"
        )


    try:

        with open(
            CALIBRATION_PATH,
            "r",
            encoding="utf-8",
        ) as file:

            config = (
                json.load(
                    file
                )
            )


    except Exception as error:

        raise RuntimeError(
            "Could not read calibration file: "
            f"{error}"
        ) from error


    return config


# ============================================================
# CREATE OUTER AREA
# ============================================================

def _create_outer_points(
    board_points: np.ndarray,
    scale: float = OUTER_SCALE,
) -> np.ndarray:

    center = (
        np.mean(
            board_points,
            axis=0,
        )
    )


    outer = (
        center
        +
        (
            board_points
            -
            center
        )
        *
        scale
    )


    return outer.astype(
        np.float32
    )


# ============================================================
# VALIDATE BOARD QUADRILATERAL
# ============================================================

def _validate_quad(
    board_points: np.ndarray,
    frame_width: int,
    frame_height: int,
):

    if (
        board_points.shape
        !=
        (
            4,
            2,
        )
    ):

        raise RuntimeError(
            "calibration.json source_points "
            "must contain exactly 4 [x, y] points."
        )


    if not (
        np.isfinite(
            board_points
        )
        .all()
    ):

        raise RuntimeError(
            "Calibration contains invalid coordinates."
        )


    x_values = (
        board_points[
            :,
            0,
        ]
    )


    y_values = (
        board_points[
            :,
            1,
        ]
    )


    # ========================================================
    # BOARD CORNERS MUST BE INSIDE CURRENT WORKING FRAME
    # ========================================================

    if (
        np.min(
            x_values
        )
        <
        0

        or

        np.min(
            y_values
        )
        <
        0

        or

        np.max(
            x_values
        )
        >=
        frame_width

        or

        np.max(
            y_values
        )
        >=
        frame_height
    ):

        raise RuntimeError(
            "Scaled calibration points fall outside "
            f"the current frame "
            f"{frame_width}x{frame_height}."
        )


    # ========================================================
    # BOARD AREA
    # ========================================================

    board_area = abs(

        cv2.contourArea(
            board_points.astype(
                np.float32
            )
        )
    )


    frame_area = float(
        frame_width
        *
        frame_height
    )


    if (
        frame_area
        <=
        0
    ):

        raise RuntimeError(
            "Current camera frame has invalid dimensions."
        )


    board_ratio = (
        board_area
        /
        frame_area
    )


    if (
        board_ratio
        <
        MIN_BOARD_AREA_RATIO
    ):

        raise RuntimeError(
            "Scaled calibration board area is too small. "
            f"Board/frame ratio = {board_ratio:.4f}"
        )


# ============================================================
# LOAD FIXED BOARD GEOMETRY
# ============================================================

def load_fixed_board_geometry(
    frame: np.ndarray,
) -> dict:

    if frame is None:

        raise RuntimeError(
            "Camera frame is None."
        )


    current_height, current_width = (
        frame.shape[:2]
    )


    config = (
        _load_config()
    )


    # ========================================================
    # SOURCE POINTS
    # ========================================================

    raw_points = (
        config.get(
            "source_points"
        )
    )


    if raw_points is None:

        raise RuntimeError(
            "calibration.json does not contain "
            "source_points."
        )


    try:

        source_points = (
            np.asarray(
                raw_points,
                dtype=np.float32,
            )
            .reshape(
                4,
                2,
            )
        )


    except Exception as error:

        raise RuntimeError(
            "Invalid source_points in calibration.json."
        ) from error


    # ========================================================
    # CALIBRATION FRAME SIZE
    # ========================================================

    calibration_width = int(

        config.get(
            "camera_width",
            0,
        )

        or

        0
    )


    calibration_height = int(

        config.get(
            "camera_height",
            0,
        )

        or

        0
    )


    if (
        calibration_width
        <=
        0

        or

        calibration_height
        <=
        0
    ):

        raise RuntimeError(
            "calibration.json is missing "
            "camera_width / camera_height."
        )


    # ========================================================
    # IMPORTANT
    # ========================================================
    #
    # Calibration was performed on the native IMOU frame.
    #
    # Example:
    #
    #     native:
    #         2688 x 1664
    #
    # The backend may use a resized working frame:
    #
    #     working:
    #         1280 x 720
    #
    # This project historically resizes the camera frame to
    # the working resolution.
    #
    # Therefore X and Y MUST be scaled independently.
    #
    # DO NOT reject different aspect ratios here.
    #
    # ========================================================

    scale_x = (
        float(
            current_width
        )
        /
        float(
            calibration_width
        )
    )


    scale_y = (
        float(
            current_height
        )
        /
        float(
            calibration_height
        )
    )


    scale_matrix = (
        np.array(
            [
                scale_x,
                scale_y,
            ],
            dtype=np.float32,
        )
    )


    board_points = (
        source_points
        *
        scale_matrix
    )


    board_points = (
        board_points.astype(
            np.float32
        )
    )


    # ========================================================
    # VALIDATE SCALED POINTS
    # ========================================================

    _validate_quad(
        board_points,
        current_width,
        current_height,
    )


    # ========================================================
    # OUTER CONTEXT
    # ========================================================

    outer_points = (
        _create_outer_points(
            board_points,
        )
    )


    # ========================================================
    # DEBUG INFORMATION
    # ========================================================

    return {

        "board_points":
            board_points.tolist(),

        "outer_points":
            outer_points.tolist(),

        "method":
            "fixed_calibration",

        "score":
            1.0,

        "calibration_frame_size": [
            calibration_width,
            calibration_height,
        ],

        "current_frame_size": [
            current_width,
            current_height,
        ],

        "scale_x":
            scale_x,

        "scale_y":
            scale_y,
    }


# ============================================================
# CHECKER VISIBILITY SCORE
# ============================================================
#
# This does NOT move the board.
#
# Geometry is fixed.
#
# This score is used only as an auxiliary signal for:
#
# - hand entering board
# - large foreign object
# - board being obscured
#
# ============================================================

def calculate_checker_score(
    frame: np.ndarray,
    board_points: list[
        list[
            float
        ]
    ],
) -> float:

    source = (
        np.asarray(
            board_points,
            dtype=np.float32,
        )
        .reshape(
            4,
            2,
        )
    )


    destination = (
        np.array(
            [
                [
                    0,
                    0,
                ],

                [
                    BOARD_SIZE - 1,
                    0,
                ],

                [
                    BOARD_SIZE - 1,
                    BOARD_SIZE - 1,
                ],

                [
                    0,
                    BOARD_SIZE - 1,
                ],
            ],
            dtype=np.float32,
        )
    )


    homography = (
        cv2.getPerspectiveTransform(
            source,
            destination,
        )
    )


    warped = (
        cv2.warpPerspective(
            frame,
            homography,
            (
                BOARD_SIZE,
                BOARD_SIZE,
            ),
        )
    )


    gray = (
        cv2.cvtColor(
            warped,
            cv2.COLOR_BGR2GRAY,
        )
    )


    square_size = (
        BOARD_SIZE
        //
        8
    )


    # ========================================================
    # CENTRAL REGION OF EACH SQUARE
    # ========================================================

    inset = 28


    parity_zero = []

    parity_one = []


    for row in range(
        8
    ):

        for col in range(
            8
        ):

            x1 = (
                col
                *
                square_size
                +
                inset
            )


            y1 = (
                row
                *
                square_size
                +
                inset
            )


            x2 = (
                (
                    col
                    +
                    1
                )
                *
                square_size
                -
                inset
            )


            y2 = (
                (
                    row
                    +
                    1
                )
                *
                square_size
                -
                inset
            )


            patch = (
                gray[
                    y1:y2,
                    x1:x2,
                ]
            )


            if (
                patch.size
                ==
                0
            ):

                continue


            mean_value = float(

                np.mean(
                    patch
                )
            )


            if (
                (
                    row
                    +
                    col
                )
                %
                2
                ==
                0
            ):

                parity_zero.append(
                    mean_value
                )


            else:

                parity_one.append(
                    mean_value
                )


    if (
        not parity_zero

        or

        not parity_one
    ):

        return 0.0


    parity_zero_mean = float(

        np.mean(
            parity_zero
        )
    )


    parity_one_mean = float(

        np.mean(
            parity_one
        )
    )


    contrast = abs(

        parity_zero_mean
        -
        parity_one_mean
    )


    score = (
        contrast
        /
        255.0
    )


    return float(

        np.clip(
            score,
            0.0,
            1.0,
        )
    )
from __future__ import annotations

import math

import cv2
import numpy as np


# ============================================================
# CONSTANTS
# ============================================================

BOARD_SIZE = 800
SQUARE_SIZE = 100
CONTEXT_SAFETY_MARGIN = 20
MAX_CONTEXT_MARGIN = 250

CAMERA_ORIENTATIONS = {
    "white_left",
    "black_left",
}


# ============================================================
# VALIDATION
# ============================================================

def validate_points(
    outer_points: list[list[float]],
    board_points: list[list[float]],
):
    if len(outer_points) != 4:
        raise ValueError(
            "outer_points must contain exactly 4 points."
        )

    if len(board_points) != 4:
        raise ValueError(
            "board_points must contain exactly 4 points."
        )

    for points, name in [
        (outer_points, "outer_points"),
        (board_points, "board_points"),
    ]:
        for point in points:
            if (
                not isinstance(point, (list, tuple))
                or len(point) != 2
            ):
                raise ValueError(
                    f"{name} must contain [x, y] points."
                )


def validate_camera_orientation(
    camera_orientation: str,
):
    if camera_orientation not in CAMERA_ORIENTATIONS:
        raise ValueError(
            "camera_orientation must be "
            "'white_left' or 'black_left'."
        )


# ============================================================
# BOARD INSIDE OUTER
# ============================================================

def validate_board_inside_outer(
    outer_points: list[list[float]],
    board_points: list[list[float]],
):
    outer = np.array(
        outer_points,
        dtype=np.float32,
    )

    contour = outer.reshape(
        (-1, 1, 2)
    )

    for point in board_points:
        result = cv2.pointPolygonTest(
            contour,
            (
                float(point[0]),
                float(point[1]),
            ),
            False,
        )

        if result < 0:
            raise ValueError(
                "All BOARD points must be inside "
                "the OUTER polygon."
            )


# ============================================================
# CANONICAL ORIENTATION
# ============================================================

def _get_canonical_board(
    camera_orientation: str,
) -> np.ndarray:
    """
    Return destination points corresponding to raw points ordered as:

        TL, TR, BR, BL

    Desired normalized board is always:

        Black at top
        White at bottom
        a-file at left
        h-file at right

    WHITE LEFT camera:
        rotate raw view 90 degrees counter-clockwise.

        raw TL -> canonical BL
        raw TR -> canonical TL
        raw BR -> canonical TR
        raw BL -> canonical BR

    BLACK LEFT camera:
        rotate raw view 90 degrees clockwise.

        raw TL -> canonical TR
        raw TR -> canonical BR
        raw BR -> canonical BL
        raw BL -> canonical TL
    """
    validate_camera_orientation(
        camera_orientation
    )

    b = BOARD_SIZE - 1

    if camera_orientation == "white_left":
        return np.array(
            [
                [0, b],
                [0, 0],
                [b, 0],
                [b, b],
            ],
            dtype=np.float32,
        )

    return np.array(
        [
            [b, 0],
            [b, b],
            [0, b],
            [0, 0],
        ],
        dtype=np.float32,
    )


# ============================================================
# CREATE NORMALIZED CONTEXT
# ============================================================

def create_normalized_context(
    frame: np.ndarray,
    outer_points: list[list[float]],
    board_points: list[list[float]],
    piece_crop_sizes: list[int],
    camera_orientation: str = "white_left",
):
    validate_points(
        outer_points,
        board_points,
    )

    validate_board_inside_outer(
        outer_points,
        board_points,
    )

    validate_camera_orientation(
        camera_orientation
    )

    outer = np.array(
        outer_points,
        dtype=np.float32,
    )

    board = np.array(
        board_points,
        dtype=np.float32,
    )

    canonical_board = _get_canonical_board(
        camera_orientation
    )

    # ========================================================
    # HOMOGRAPHY TO EXACT BOARD
    # ========================================================

    h_base = cv2.getPerspectiveTransform(
        board,
        canonical_board,
    )

    # ========================================================
    # TRANSFORM OUTER POLYGON
    # ========================================================

    outer_transformed = cv2.perspectiveTransform(
        outer.reshape(
            1,
            -1,
            2,
        ),
        h_base,
    )[0]

    b = BOARD_SIZE - 1

    min_x = float(
        np.min(
            outer_transformed[:, 0]
        )
    )

    min_y = float(
        np.min(
            outer_transformed[:, 1]
        )
    )

    max_x = float(
        np.max(
            outer_transformed[:, 0]
        )
    )

    max_y = float(
        np.max(
            outer_transformed[:, 1]
        )
    )

    required_left = max(
        0.0,
        -min_x,
    )

    required_top = max(
        0.0,
        -min_y,
    )

    required_right = max(
        0.0,
        max_x - b,
    )

    required_bottom = max(
        0.0,
        max_y - b,
    )

    largest_crop = max(
        piece_crop_sizes
    )

    max_piece_half = (
        largest_crop / 2
    )

    required_context = max(
        required_left,
        required_top,
        required_right,
        required_bottom,
        max_piece_half,
    )

    context_margin = math.ceil(
        required_context
        + CONTEXT_SAFETY_MARGIN
    )

    if context_margin > MAX_CONTEXT_MARGIN:
        raise ValueError(
            "Required context margin is too large "
            f"({context_margin}px). "
            "Check the selected OUTER/BOARD points."
        )

    context_size = (
        BOARD_SIZE
        + context_margin * 2
    )

    # ========================================================
    # TRANSLATION
    # ========================================================

    translation = np.array(
        [
            [
                1,
                0,
                context_margin,
            ],
            [
                0,
                1,
                context_margin,
            ],
            [
                0,
                0,
                1,
            ],
        ],
        dtype=np.float64,
    )

    homography = (
        translation
        @ h_base
    )

    # ========================================================
    # WARP ENTIRE RAW IMAGE
    # ========================================================

    context = cv2.warpPerspective(
        frame,
        homography,
        (
            context_size,
            context_size,
        ),
        flags=cv2.INTER_LINEAR,
    )

    board_origin = (
        context_margin,
        context_margin,
    )

    board_image = context[
        context_margin:
        context_margin + BOARD_SIZE,
        context_margin:
        context_margin + BOARD_SIZE,
    ].copy()

    if board_image.shape[:2] != (
        BOARD_SIZE,
        BOARD_SIZE,
    ):
        raise RuntimeError(
            "Normalized board has incorrect size."
        )

    return {
        "context":
            context,
        "board":
            board_image,
        "board_origin":
            board_origin,
        "homography":
            homography,
        "context_margin":
            context_margin,
        "camera_orientation":
            camera_orientation,
    }


# ============================================================
# OCCUPANCY CROP
# ============================================================

def extract_occupancy_crop(
    board: np.ndarray,
    row: int,
    col: int,
):
    x1 = (
        col
        * SQUARE_SIZE
    )

    y1 = (
        row
        * SQUARE_SIZE
    )

    x2 = (
        x1
        + SQUARE_SIZE
    )

    y2 = (
        y1
        + SQUARE_SIZE
    )

    crop = board[
        y1:y2,
        x1:x2,
    ].copy()

    if crop.shape[:2] != (
        SQUARE_SIZE,
        SQUARE_SIZE,
    ):
        raise RuntimeError(
            "Invalid occupancy crop size."
        )

    return crop


# ============================================================
# PIECE CROP
# ============================================================

def extract_piece_crop(
    context: np.ndarray,
    board_origin: tuple[int, int],
    row: int,
    col: int,
    crop_size: int,
):
    origin_x, origin_y = (
        board_origin
    )

    center_x = (
        origin_x
        + col * SQUARE_SIZE
        + SQUARE_SIZE // 2
    )

    center_y = (
        origin_y
        + row * SQUARE_SIZE
        + SQUARE_SIZE // 2
    )

    half = (
        crop_size // 2
    )

    x1 = (
        center_x
        - half
    )

    y1 = (
        center_y
        - half
    )

    x2 = (
        x1
        + crop_size
    )

    y2 = (
        y1
        + crop_size
    )

    if (
        x1 < 0
        or y1 < 0
        or x2 > context.shape[1]
        or y2 > context.shape[0]
    ):
        raise RuntimeError(
            f"Piece crop {crop_size}px "
            "extends outside normalized context."
        )

    crop = context[
        y1:y2,
        x1:x2,
    ].copy()

    if crop.shape[:2] != (
        crop_size,
        crop_size,
    ):
        raise RuntimeError(
            "Invalid piece crop size."
        )

    return crop

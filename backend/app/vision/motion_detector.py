from __future__ import annotations

import time

import cv2
import numpy as np


# ============================================================
# CONFIG
# ============================================================

MOTION_BOARD_SIZE = 320

PIXEL_DIFF_THRESHOLD = 18

MOTION_RATIO_THRESHOLD = 0.015

STABLE_DURATION_SECONDS = 0.80


# ============================================================
# MOTION RESULT
# ============================================================

class MotionResult:

    def __init__(
        self,
        *,
        moving: bool,
        stable: bool,
        motion_ratio: float,
        stable_for_seconds: float,
    ):

        self.moving = moving

        self.stable = stable

        self.motion_ratio = motion_ratio

        self.stable_for_seconds = (
            stable_for_seconds
        )


# ============================================================
# BOARD MOTION DETECTOR
# ============================================================

class BoardMotionDetector:

    def __init__(
        self,
        *,
        pixel_diff_threshold: int = PIXEL_DIFF_THRESHOLD,
        motion_ratio_threshold: float = MOTION_RATIO_THRESHOLD,
        stable_duration_seconds: float = STABLE_DURATION_SECONDS,
    ):

        self.pixel_diff_threshold = (
            pixel_diff_threshold
        )

        self.motion_ratio_threshold = (
            motion_ratio_threshold
        )

        self.stable_duration_seconds = (
            stable_duration_seconds
        )


        self.previous_board: (
            np.ndarray
            |
            None
        ) = None


        self.last_motion_at: (
            float
            |
            None
        ) = None


    # ========================================================
    # RESET
    # ========================================================

    def reset(
        self,
    ):

        self.previous_board = None

        self.last_motion_at = None


    # ========================================================
    # NORMALIZE BOARD FOR MOTION CHECK
    # ========================================================

    def _normalize_board(
        self,
        frame: np.ndarray,
        board_points: list[list[float]],
    ) -> np.ndarray:

        source = np.asarray(
            board_points,
            dtype=np.float32,
        ).reshape(
            4,
            2,
        )


        B = (
            MOTION_BOARD_SIZE
            -
            1
        )


        # ====================================================
        # ORIENTATION
        # ====================================================
        #
        # Physical camera:
        #
        # WHITE = LEFT
        # BLACK = RIGHT
        #
        #
        # Canonical:
        #
        # BLACK = TOP
        # WHITE = BOTTOM
        #
        #
        # raw TL -> canonical BL
        # raw TR -> canonical TL
        # raw BR -> canonical TR
        # raw BL -> canonical BR
        #
        # ====================================================

        destination = np.asarray(
            [
                [0, B],
                [0, 0],
                [B, 0],
                [B, B],
            ],
            dtype=np.float32,
        )


        H = cv2.getPerspectiveTransform(
            source,
            destination,
        )


        # ====================================================
        # GRAYSCALE
        # ====================================================

        gray = cv2.cvtColor(
            frame,
            cv2.COLOR_BGR2GRAY,
        )


        # ====================================================
        # WARP BOARD
        # ====================================================

        board = cv2.warpPerspective(
            gray,
            H,
            (
                MOTION_BOARD_SIZE,
                MOTION_BOARD_SIZE,
            ),
            flags=cv2.INTER_LINEAR,
        )


        # ====================================================
        # REDUCE CAMERA / RTSP NOISE
        # ====================================================

        board = cv2.GaussianBlur(
            board,
            (
                5,
                5,
            ),
            0,
        )


        return board


    # ========================================================
    # UPDATE
    # ========================================================

    def update(
        self,
        frame: np.ndarray,
        board_points: list[list[float]],
    ) -> MotionResult:

        now = time.monotonic()


        current_board = (
            self._normalize_board(
                frame,
                board_points,
            )
        )


        # ====================================================
        # FIRST FRAME
        # ====================================================

        if self.previous_board is None:

            self.previous_board = (
                current_board
            )

            self.last_motion_at = now


            return MotionResult(
                moving=False,
                stable=False,
                motion_ratio=0.0,
                stable_for_seconds=0.0,
            )


        # ====================================================
        # DIFFERENCE
        # ====================================================

        difference = cv2.absdiff(
            self.previous_board,
            current_board,
        )


        # ====================================================
        # CHANGE MASK
        # ====================================================

        _, changed = cv2.threshold(
            difference,
            self.pixel_diff_threshold,
            255,
            cv2.THRESH_BINARY,
        )


        kernel = np.ones(
            (
                3,
                3,
            ),
            dtype=np.uint8,
        )


        changed = cv2.morphologyEx(
            changed,
            cv2.MORPH_OPEN,
            kernel,
        )


        # ====================================================
        # MOTION RATIO
        # ====================================================

        changed_pixels = (
            cv2.countNonZero(
                changed
            )
        )


        total_pixels = (
            MOTION_BOARD_SIZE
            *
            MOTION_BOARD_SIZE
        )


        motion_ratio = (
            changed_pixels
            /
            total_pixels
        )


        moving = (
            motion_ratio
            >=
            self.motion_ratio_threshold
        )


        # ====================================================
        # STABILITY TIMER
        # ====================================================

        if moving:

            self.last_motion_at = now


        if self.last_motion_at is None:

            self.last_motion_at = now


        stable_for_seconds = max(
            0.0,
            now
            -
            self.last_motion_at,
        )


        stable = (
            not moving
            and
            stable_for_seconds
            >=
            self.stable_duration_seconds
        )


        # ====================================================
        # SAVE CURRENT FRAME
        # ====================================================

        self.previous_board = (
            current_board
        )


        return MotionResult(
            moving=moving,
            stable=stable,
            motion_ratio=float(
                motion_ratio
            ),
            stable_for_seconds=float(
                stable_for_seconds
            ),
        )
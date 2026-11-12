from __future__ import annotations

import os
import threading
import time

import cv2
import numpy as np

from backend.app.core.config import (
    settings,
)


# ============================================================
# WORKING FRAME
# ============================================================
#
# Camera can keep streaming its native MAIN STREAM resolution.
#
# Current IMOU main stream:
#
#   2688 x 1664
#
# But the rest of this project was designed around:
#
#   1280 x 720
#
# This is also the same strategy used by dataset_capture.py:
#
# native stream
#     ↓
# decode
#     ↓
# resize once
#     ↓
# 1280 x 720 working frame
#
# ============================================================

WORKING_WIDTH = 1280

WORKING_HEIGHT = 720


# ============================================================
# RTSP / HEVC DECODER SAFETY
# ============================================================
#
# Decode at native camera resolution before resizing.
# Reduce decoder frame-thread buffer pressure for HEVC.
# These VideoCapture properties are open-only with FFmpeg.
#
# ============================================================

FFMPEG_DECODER_THREADS = 2

CAMERA_OPEN_TIMEOUT_MS = 7000

CAMERA_READ_TIMEOUT_MS = 5000

# Reject an old cached frame when decoder stops producing frames.

MAX_FRAME_AGE_SECONDS = 3.0


# ============================================================
# CAMERA SERVICE
# ============================================================

class CameraService:

    def __init__(
        self,
    ):

        self.rtsp_url = (
            settings.CAMERA_RTSP_URL
        )


        self.cap: (
            cv2.VideoCapture
            |
            None
        ) = None


        self.latest_frame: (
            np.ndarray
            |
            None
        ) = None


        # Monotonic time of the most recently decoded frame.
        # Used to prevent stale frames being mistaken for live video.

        self.latest_frame_time = 0.0


        self.running = False


        # Protect:
        #
        # - latest_frame
        # - running
        # - thread startup

        self.lock = (
            threading.Lock()
        )


        self.thread: (
            threading.Thread
            |
            None
        ) = None


    # ========================================================
    # DISCONNECT
    # ========================================================

    def _disconnect(
        self,
    ):

        if self.cap is not None:

            try:

                self.cap.release()

            except Exception:

                pass


        self.cap = None


        with self.lock:

            self.latest_frame = None

            self.latest_frame_time = 0.0


    # ========================================================
    # CONNECT
    # ========================================================

    def _connect(
        self,
    ):

        if not self.rtsp_url:

            raise RuntimeError(
                "CAMERA_RTSP_URL is not configured."
            )


        if self.cap is not None:

            try:

                self.cap.release()

            except Exception:

                pass


            self.cap = None


        print()

        print(
            "Connecting to RTSP camera..."
        )


        # Prefer TCP for RTSP; preserve an explicit user override.
        # This is read by OpenCV's FFmpeg backend when opening.

        os.environ.setdefault(
            "OPENCV_FFMPEG_CAPTURE_OPTIONS",
            "rtsp_transport;tcp",
        )


        capture_params = []

        if hasattr(cv2, "CAP_PROP_OPEN_TIMEOUT_MSEC"):
            capture_params.extend([
                cv2.CAP_PROP_OPEN_TIMEOUT_MSEC,
                CAMERA_OPEN_TIMEOUT_MS,
            ])

        if hasattr(cv2, "CAP_PROP_READ_TIMEOUT_MSEC"):
            capture_params.extend([
                cv2.CAP_PROP_READ_TIMEOUT_MSEC,
                CAMERA_READ_TIMEOUT_MS,
            ])

        if hasattr(cv2, "CAP_PROP_N_THREADS"):
            capture_params.extend([
                cv2.CAP_PROP_N_THREADS,
                FFMPEG_DECODER_THREADS,
            ])


        # Some older OpenCV builds do not support the params
        # constructor, or a specific open-only property.
        # Fall back to the project's original VideoCapture call.

        try:
            self.cap = cv2.VideoCapture(
                self.rtsp_url,
                cv2.CAP_FFMPEG,
                capture_params,
            )

        except (TypeError, cv2.error):
            self.cap = cv2.VideoCapture(
                self.rtsp_url,
                cv2.CAP_FFMPEG,
            )

        if not self.cap.isOpened() and capture_params:
            self.cap.release()

            self.cap = cv2.VideoCapture(
                self.rtsp_url,
                cv2.CAP_FFMPEG,
            )


        # CAP_PROP_BUFFERSIZE may be ignored by FFmpeg, but
        # retain the original setting for compatible backends.

        self.cap.set(
            cv2.CAP_PROP_BUFFERSIZE,
            1,
        )


        if not self.cap.isOpened():

            self.cap.release()

            self.cap = None


            raise RuntimeError(
                "Could not connect to RTSP camera."
            )


        print(
            "RTSP camera connected."
        )


    # ========================================================
    # PREPARE WORKING FRAME
    # ========================================================

    def _prepare_frame(
        self,
        frame: np.ndarray,
    ) -> np.ndarray:

        height, width = (
            frame.shape[:2]
        )


        # ====================================================
        # ALREADY CORRECT SIZE
        # ====================================================

        if (
            width
            ==
            WORKING_WIDTH
            and
            height
            ==
            WORKING_HEIGHT
        ):

            return frame


        # ====================================================
        # NATIVE STREAM -> 1280 x 720
        # ====================================================

        interpolation = (
            cv2.INTER_AREA
            if (
                width
                >
                WORKING_WIDTH
                or
                height
                >
                WORKING_HEIGHT
            )
            else
            cv2.INTER_LINEAR
        )


        resized = cv2.resize(
            frame,
            (
                WORKING_WIDTH,
                WORKING_HEIGHT,
            ),
            interpolation=
                interpolation,
        )


        return resized


    # ========================================================
    # BACKGROUND LOOP
    # ========================================================

    def _capture_loop(
        self,
    ):

        while True:

            # =================================================
            # STILL RUNNING?
            # =================================================

            with self.lock:

                if not self.running:

                    break


            # =================================================
            # CONNECT IF NEEDED
            # =================================================

            if (
                self.cap is None
                or
                not self.cap.isOpened()
            ):

                try:

                    self._connect()

                except RuntimeError as error:

                    print(
                        f"RTSP connect error: {error}"
                    )


                    time.sleep(
                        2
                    )


                    continue


            # =================================================
            # READ NATIVE FRAME
            # =================================================

            try:

                ret, frame = (
                    self.cap.read()
                )

            except (
                cv2.error,
                MemoryError,
            ) as error:

                print(
                    "RTSP frame read error:"
                )

                print(
                    error
                )


                self._disconnect()


                time.sleep(
                    1
                )


                continue


            # =================================================
            # FRAME LOST
            # =================================================

            if (
                not ret
                or
                frame is None
            ):

                print(
                    "RTSP frame lost. Reconnecting..."
                )


                self._disconnect()


                time.sleep(
                    1
                )


                continue


            # =================================================
            # RESIZE IMMEDIATELY
            # =================================================
            #
            # IMPORTANT:
            #
            # Do this BEFORE storing latest_frame.
            #
            # We do not want the rest of the backend holding
            # multiple 2688x1664 copies.
            #
            # =================================================

            try:

                frame = (
                    self._prepare_frame(
                        frame
                    )
                )

            except (
                cv2.error,
                MemoryError,
            ) as error:

                print(
                    "Could not create camera working frame:"
                )

                print(
                    error
                )


                # Drop this frame.
                #
                # Camera connection itself may still be valid.

                time.sleep(
                    0.1
                )


                continue


            # ========================================================
            # STORE LATEST FRAME
            # ========================================================
            #
            # No frame.copy() here.
            #
            # cap.read() / cv2.resize() already returned a new
            # ndarray owned by this iteration.
            #
            # We transfer that reference to latest_frame.
            #
            # Consumers still receive their own copy through
            # get_frame(), so they cannot mutate this buffer.
            #
            # ========================================================

            with self.lock:

                self.latest_frame = (
                    frame
                )

                self.latest_frame_time = (
                    time.monotonic()
                )


        # ========================================================
        # THREAD EXIT
        # ========================================================

        self._disconnect()


    # ========================================================
    # START
    # ========================================================

    def start(
        self,
    ):

        # ========================================================
        # THREAD-SAFE START
        # ========================================================
        #
        # MJPEG stream and LiveGame may call get_frame()
        # at almost the same time.
        #
        # Without this lock it is possible for both callers
        # to start their own capture thread.
        #
        # ========================================================

        with self.lock:

            if (
                self.running
                and
                self.thread is not None
                and
                self.thread.is_alive()
            ):

                return


            self.running = True


            self.thread = threading.Thread(
                target=
                    self._capture_loop,

                daemon=True,

                name=
                    "CameraCapture",
            )


            self.thread.start()


    # ========================================================
    # STOP
    # ========================================================

    def stop(
        self,
    ):

        with self.lock:

            self.running = False


            thread = (
                self.thread
            )


        if (
            thread is not None
            and
            thread.is_alive()
            and
            thread
            is not
            threading.current_thread()
        ):

            thread.join(
                timeout=3.0
            )


        with self.lock:

            self.thread = None

            self.latest_frame = None

            self.latest_frame_time = 0.0


    # ========================================================
    # GET FRAME
    # ========================================================

    def get_frame(
        self,
        timeout: float = 5.0,
    ) -> np.ndarray:

        self.start()


        start_time = (
            time.monotonic()
        )


        while (
            time.monotonic()
            -
            start_time
            <
            timeout
        ):

            with self.lock:

                if (
                    self.latest_frame
                    is not None
                    and
                    self.latest_frame_time > 0.0
                    and
                    time.monotonic()
                    - self.latest_frame_time
                    <= MAX_FRAME_AGE_SECONDS
                ):

                    # =========================================
                    # ONLY COPY THE FRESH 1280x720 WORKING FRAME
                    # =========================================
                    # Never let Live Game score an indefinitely
                    # cached frame when HEVC decoding has stalled.

                    return (
                        self.latest_frame.copy()
                    )


            time.sleep(
                0.03
            )


        raise RuntimeError(
            "No fresh camera frame received. "
            "Check RTSP stream or HEVC decoder."
        )


    # ========================================================
    # JPEG
    # ========================================================

    def get_jpeg(
        self,
        quality: int = 90,
    ) -> bytes:

        frame = (
            self.get_frame()
        )


        quality = max(
            1,
            min(
                100,
                int(
                    quality
                ),
            ),
        )


        try:

            success, encoded = (
                cv2.imencode(
                    ".jpg",
                    frame,

                    [
                        cv2.IMWRITE_JPEG_QUALITY,
                        quality,
                    ],
                )
            )

        except (
            cv2.error,
            MemoryError,
        ) as error:

            raise RuntimeError(
                "Could not encode camera frame."
            ) from error


        if not success:

            raise RuntimeError(
                "Could not encode camera frame."
            )


        return (
            encoded.tobytes()
        )


# ============================================================
# SINGLETON
# ============================================================

camera_service = (
    CameraService()
)
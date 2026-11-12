from __future__ import annotations

import time

from fastapi import (
    APIRouter,
    HTTPException,
)

from fastapi.responses import (
    Response,
    StreamingResponse,
)

from backend.app.services.camera_service import (
    camera_service,
)


router = APIRouter(
    prefix="/camera",
    tags=["Camera"],
)


# ============================================================
# STREAM CONFIG
# ============================================================

STREAM_JPEG_QUALITY = 75

STREAM_FRAME_INTERVAL = 0.04


# ============================================================
# SNAPSHOT
# ============================================================

@router.get(
    "/snapshot"
)
def camera_snapshot():

    try:

        jpeg = (
            camera_service
            .get_jpeg(
                quality=90
            )
        )


        return Response(
            content=
                jpeg,

            media_type=
                "image/jpeg",

            headers={
                "Cache-Control":
                    "no-store",
            },
        )


    except RuntimeError as error:

        raise HTTPException(
            status_code=503,
            detail=str(error),
        ) from error


# ============================================================
# MJPEG STREAM
# ============================================================

def mjpeg_generator():

    while True:

        try:

            # =================================================
            # CAMERA SERVICE ALREADY RETURNS THE 1280x720
            # WORKING FRAME.
            #
            # JPEG encoding is also centralized there.
            # =================================================

            jpeg = (
                camera_service
                .get_jpeg(
                    quality=
                        STREAM_JPEG_QUALITY
                )
            )


            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n"
                +
                jpeg
                +
                b"\r\n"
            )


            time.sleep(
                STREAM_FRAME_INTERVAL
            )


        except RuntimeError:

            # Camera may temporarily reconnect.
            #
            # Keep the MJPEG response alive and try again.

            time.sleep(
                0.5
            )


# ============================================================
# CAMERA STREAM
# ============================================================

@router.get(
    "/stream"
)
def camera_stream():

    return StreamingResponse(
        mjpeg_generator(),

        media_type=(
            "multipart/x-mixed-replace;"
            "boundary=frame"
        ),

        headers={
            "Cache-Control":
                "no-store",
        },
    )
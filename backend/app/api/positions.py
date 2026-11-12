import json

import cv2
import numpy as np

from fastapi import (
    APIRouter,
    File,
    Form,
    HTTPException,
    UploadFile,
)

from backend.app.schemas.position import (
    PositionRecognitionResponse,
)

from backend.app.vision.pipeline import (
    recognize_position,
    recognize_position_auto,
)


router = APIRouter(
    prefix="/positions",
    tags=["Positions"],
)


# ============================================================
# MANUAL RECOGNITION
# ============================================================

@router.post(
    "/recognize",
    response_model=PositionRecognitionResponse,
)
async def recognize_position_endpoint(
    image: UploadFile = File(...),
    outer_points: str = Form(...),
    board_points: str = Form(...),
):

    if (
        image.content_type is not None
        and
        not image.content_type.startswith("image/")
    ):
        raise HTTPException(
            status_code=400,
            detail="Uploaded file must be an image.",
        )


    try:
        parsed_outer_points = json.loads(
            outer_points
        )

        parsed_board_points = json.loads(
            board_points
        )

    except json.JSONDecodeError as error:
        raise HTTPException(
            status_code=400,
            detail=(
                "outer_points and board_points "
                "must be valid JSON arrays."
            ),
        ) from error


    image_bytes = await image.read()


    np_buffer = np.frombuffer(
        image_bytes,
        dtype=np.uint8,
    )


    frame = cv2.imdecode(
        np_buffer,
        cv2.IMREAD_COLOR,
    )


    if frame is None:
        raise HTTPException(
            status_code=400,
            detail="Could not decode uploaded image.",
        )


    try:
        result = recognize_position(
            frame=frame,
            outer_points=parsed_outer_points,
            board_points=parsed_board_points,
        )

    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        ) from error

    except RuntimeError as error:
        raise HTTPException(
            status_code=500,
            detail=str(error),
        ) from error


    return result


# ============================================================
# AUTO RECOGNITION
# ============================================================

@router.post(
    "/recognize-auto",
    response_model=PositionRecognitionResponse,
)
async def recognize_position_auto_endpoint(
    image: UploadFile = File(...),
):

    if (
        image.content_type is not None
        and
        not image.content_type.startswith("image/")
    ):
        raise HTTPException(
            status_code=400,
            detail="Uploaded file must be an image.",
        )


    image_bytes = await image.read()


    np_buffer = np.frombuffer(
        image_bytes,
        dtype=np.uint8,
    )


    frame = cv2.imdecode(
        np_buffer,
        cv2.IMREAD_COLOR,
    )


    if frame is None:
        raise HTTPException(
            status_code=400,
            detail="Could not decode uploaded image.",
        )


    try:
        result = recognize_position_auto(
            frame
        )

    except ValueError as error:
        raise HTTPException(
            status_code=422,
            detail=str(error),
        ) from error

    except RuntimeError as error:
        raise HTTPException(
            status_code=500,
            detail=str(error),
        ) from error


    return result
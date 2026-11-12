from __future__ import annotations

import asyncio
import json
import time

import cv2

from fastapi import (
    APIRouter,
    HTTPException,
    WebSocket,
    WebSocketDisconnect,
)

from fastapi.responses import (
    StreamingResponse,
)

from pydantic import (
    BaseModel,
    Field,
)

from backend.app.services.camera_service import (
    camera_service,
)

from backend.app.services.live_game_service import (
    live_game_service,
)


router = APIRouter(
    prefix="/live",
    tags=["Live Game"],
)


# ============================================================
# START REQUEST
# ============================================================

class LiveGameStartRequest(BaseModel):

    white_name: str = Field(
        default="White",
        max_length=100,
    )

    black_name: str = Field(
        default="Black",
        max_length=100,
    )

    game_mode: str = "human_vs_human"

    bot_type: str = "beginner"

    human_color: (
        str
        | None
    ) = None

    side_to_move: str = "w"

    camera_orientation: str = "white_left"

    position_mode: str = "detect"


# ============================================================
# STATE
# ============================================================

@router.get("/state")
def live_state():
    return live_game_service.get_state()


# ============================================================
# START
# ============================================================

@router.post("/start")
def start_live_game(
    payload: LiveGameStartRequest | None = None,
):

    if payload is None:
        payload = LiveGameStartRequest()

    try:
        return live_game_service.start(
            white_name=payload.white_name,
            black_name=payload.black_name,
            game_mode=payload.game_mode,
            bot_type=payload.bot_type,
            human_color=payload.human_color,
            side_to_move=payload.side_to_move,
            camera_orientation=payload.camera_orientation,
            position_mode=payload.position_mode,
        )

    except ValueError as error:
        raise HTTPException(
            status_code=422,
            detail=str(error),
        ) from error

    except RuntimeError as error:
        raise HTTPException(
            status_code=503,
            detail=str(error),
        ) from error


# ============================================================
# STOP
# ============================================================

@router.post("/stop")
def stop_live_game():
    return live_game_service.stop()


# ============================================================
# DEBUG / BOARD ALIGNMENT STREAM
# ============================================================

def debug_stream_generator():

    while True:
        try:
            frame = camera_service.get_frame(
                timeout=2.0
            )

            frame = live_game_service.draw_debug_overlay(
                frame
            )

            success, encoded = cv2.imencode(
                ".jpg",
                frame,
                [
                    cv2.IMWRITE_JPEG_QUALITY,
                    78,
                ],
            )

            if not success:
                continue

            jpeg = encoded.tobytes()

            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n"
                + jpeg
                + b"\r\n"
            )

            time.sleep(0.08)

        except RuntimeError:
            time.sleep(0.5)


@router.get("/debug-stream")
def debug_stream():

    return StreamingResponse(
        debug_stream_generator(),
        media_type=(
            "multipart/x-mixed-replace;"
            "boundary=frame"
        ),
        headers={
            "Cache-Control": "no-store",
        },
    )


# ============================================================
# WEBSOCKET
# ============================================================

@router.websocket("/ws")
async def live_game_websocket(
    websocket: WebSocket,
):

    await websocket.accept()

    previous_payload: str | None = None

    try:
        while True:

            state = live_game_service.get_state()

            payload = json.dumps(
                state,
                sort_keys=True,
            )

            if payload != previous_payload:

                await websocket.send_json(
                    state
                )

                previous_payload = payload

            await asyncio.sleep(0.20)

    except WebSocketDisconnect:
        return
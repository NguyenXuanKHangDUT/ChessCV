from __future__ import annotations

import json
import sys

from datetime import datetime
from pathlib import Path

import cv2
import numpy as np


# ============================================================
# PROJECT IMPORT PATH
# ============================================================

PROJECT_ROOT = (
    Path(__file__)
    .resolve()
    .parent
    .parent
)


if str(
    PROJECT_ROOT
) not in sys.path:

    sys.path.insert(
        0,
        str(
            PROJECT_ROOT
        ),
    )


from backend.app.core.config import (  # noqa: E402
    settings,
)


# ============================================================
# CONSTANTS
# ============================================================

CALIBRATION_PATH = (
    PROJECT_ROOT
    /
    "config"
    /
    "calibration.json"
)


BOARD_SIZE = 800


WINDOW_NAME = (
    "PBL4 ChessCV - Fixed Board Calibration"
)


LABELS = [
    "TL",
    "TR",
    "BR",
    "BL",
]


# ============================================================
# STATE
# ============================================================

clicked_points: list[
    tuple[int, int]
] = []


frozen_frame: (
    np.ndarray
    |
    None
) = None


# ============================================================
# ORDER 4 CORNERS
# ============================================================
#
# Result:
#
# TL
# TR
# BR
# BL
#
# ============================================================

def order_quad_points(
    points: np.ndarray,
) -> np.ndarray:

    points = np.asarray(
        points,
        dtype=np.float32,
    ).reshape(
        4,
        2,
    )


    ordered = np.zeros(
        (
            4,
            2,
        ),
        dtype=np.float32,
    )


    sums = (
        points.sum(
            axis=1,
        )
    )


    diffs = (
        np.diff(
            points,
            axis=1,
        )
        .reshape(
            -1,
        )
    )


    ordered[0] = points[
        np.argmin(
            sums
        )
    ]


    ordered[2] = points[
        np.argmax(
            sums
        )
    ]


    ordered[1] = points[
        np.argmin(
            diffs
        )
    ]


    ordered[3] = points[
        np.argmax(
            diffs
        )
    ]


    return ordered


# ============================================================
# MOUSE CLICK
# ============================================================

def mouse_callback(
    event,
    x,
    y,
    flags,
    userdata,
):

    del flags
    del userdata


    global clicked_points


    if (
        event
        !=
        cv2.EVENT_LBUTTONDOWN
    ):

        return


    if frozen_frame is None:

        return


    if len(
        clicked_points
    ) >= 4:

        return


    clicked_points.append(
        (
            int(
                x
            ),
            int(
                y
            ),
        )
    )


# ============================================================
# DRAW 8x8 GRID
# ============================================================

def draw_grid(
    output: np.ndarray,
    board_points: np.ndarray,
):

    canonical = np.array(
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


    inverse_h = (
        cv2.getPerspectiveTransform(
            canonical,
            board_points.astype(
                np.float32
            ),
        )
    )


    def project(
        points,
    ):

        array = np.asarray(
            points,
            dtype=np.float32,
        ).reshape(
            -1,
            1,
            2,
        )


        return (

            cv2.perspectiveTransform(
                array,
                inverse_h,
            )

            .reshape(
                -1,
                2,
            )

            .astype(
                np.int32
            )
        )


    for index in range(
        9
    ):

        p = (
            index
            *
            (
                BOARD_SIZE
                -
                1
            )
            /
            8.0
        )


        vertical = project(
            [
                [
                    p,
                    0,
                ],

                [
                    p,
                    BOARD_SIZE - 1,
                ],
            ]
        )


        horizontal = project(
            [
                [
                    0,
                    p,
                ],

                [
                    BOARD_SIZE - 1,
                    p,
                ],
            ]
        )


        cv2.line(
            output,
            tuple(
                vertical[0]
            ),
            tuple(
                vertical[1]
            ),
            (
                0,
                255,
                0,
            ),
            1,
            cv2.LINE_AA,
        )


        cv2.line(
            output,
            tuple(
                horizontal[0]
            ),
            tuple(
                horizontal[1]
            ),
            (
                0,
                255,
                0,
            ),
            1,
            cv2.LINE_AA,
        )


# ============================================================
# DRAW UI
# ============================================================

def draw_overlay(
    frame: np.ndarray,
) -> np.ndarray:

    output = (
        frame.copy()
    )


    cv2.rectangle(
        output,

        (
            10,
            10,
        ),

        (
            min(
                output.shape[1]
                -
                10,

                980,
            ),

            92,
        ),

        (
            0,
            0,
            0,
        ),

        -1,
    )


    if frozen_frame is None:

        line1 = (
            "LIVE - press SPACE to freeze"
        )


        line2 = (
            "Then click the 4 exact PLAYING-AREA corners: "
            "TL -> TR -> BR -> BL"
        )


    else:

        line1 = (
            f"FROZEN - points "
            f"{len(clicked_points)}/4"
        )


        line2 = (
            "U=undo | R=reset | SPACE=live | "
            "ENTER=save when the green grid is correct"
        )


    cv2.putText(
        output,

        line1,

        (
            20,
            40,
        ),

        cv2.FONT_HERSHEY_SIMPLEX,

        0.68,

        (
            255,
            255,
            255,
        ),

        2,

        cv2.LINE_AA,
    )


    cv2.putText(
        output,

        line2,

        (
            20,
            72,
        ),

        cv2.FONT_HERSHEY_SIMPLEX,

        0.55,

        (
            255,
            255,
            255,
        ),

        1,

        cv2.LINE_AA,
    )


    # ========================================================
    # CLICKED CORNERS
    # ========================================================

    for index, point in enumerate(
        clicked_points
    ):

        cv2.circle(
            output,

            point,

            7,

            (
                0,
                255,
                0,
            ),

            -1,
        )


        cv2.putText(
            output,

            LABELS[
                index
            ],

            (
                point[0]
                +
                9,

                point[1]
                -
                9,
            ),

            cv2.FONT_HERSHEY_SIMPLEX,

            0.55,

            (
                0,
                255,
                0,
            ),

            2,

            cv2.LINE_AA,
        )


    # ========================================================
    # FULL GRID PREVIEW
    # ========================================================

    if len(
        clicked_points
    ) == 4:

        ordered = (
            order_quad_points(
                np.asarray(
                    clicked_points,
                    dtype=np.float32,
                )
            )
        )


        cv2.polylines(
            output,

            [
                ordered
                .astype(
                    np.int32
                )
                .reshape(
                    -1,
                    1,
                    2,
                )
            ],

            True,

            (
                0,
                255,
                0,
            ),

            3,

            cv2.LINE_AA,
        )


        draw_grid(
            output,
            ordered,
        )


    return output


# ============================================================
# SAVE CALIBRATION
# ============================================================

def save_calibration(
    frame: np.ndarray,
):

    if len(
        clicked_points
    ) != 4:

        raise RuntimeError(
            "Need exactly 4 board corners."
        )


    board_points = (
        order_quad_points(
            np.asarray(
                clicked_points,
                dtype=np.float32,
            )
        )
    )


    area = abs(
        cv2.contourArea(
            board_points
        )
    )


    height, width = (
        frame.shape[:2]
    )


    if (
        area
        <
        width
        *
        height
        *
        0.05
    ):

        raise RuntimeError(
            "Selected board region is too small."
        )


    destination = np.array(
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


    homography = (
        cv2.getPerspectiveTransform(
            board_points,
            destination,
        )
    )


    config = {

        "camera_width":
            int(
                width
            ),

        "camera_height":
            int(
                height
            ),

        "board_size":
            BOARD_SIZE,

        "point_order":
            "TL_TR_BR_BL",

        "camera_source":
            "rtsp",

        "source_points":
            board_points.tolist(),

        "homography":
            homography.tolist(),

        "created_at":
            datetime.now()
            .isoformat(
                timespec="seconds"
            ),
    }


    CALIBRATION_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )


    with open(
        CALIBRATION_PATH,
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            config,
            file,
            indent=4,
        )


    print()

    print(
        "=========================================="
    )

    print(
        "FIXED BOARD CALIBRATION SAVED"
    )

    print(
        "=========================================="
    )

    print(
        f"Path : "
        f"{CALIBRATION_PATH}"
    )

    print(
        f"Frame: "
        f"{width}x{height}"
    )

    print(
        "Points:"
    )


    for label, point in zip(
        LABELS,
        board_points,
    ):

        print(
            f"  {label}: "
            f"({point[0]:.1f}, "
            f"{point[1]:.1f})"
        )


    print(
        "=========================================="
    )

    print()


# ============================================================
# MAIN
# ============================================================

def main():

    global frozen_frame
    global clicked_points


    rtsp_url = (
        settings.CAMERA_RTSP_URL
    )


    if not rtsp_url:

        raise RuntimeError(
            "CAMERA_RTSP_URL is not configured in .env"
        )


    print()

    print(
        "=========================================="
    )

    print(
        "PBL4 CHESSCV - FIXED BOARD CALIBRATION"
    )

    print(
        "=========================================="
    )

    print(
        "Stop the FastAPI backend before calibration."
    )

    print(
        "SPACE : freeze / return to live"
    )

    print(
        "Click : TL -> TR -> BR -> BL"
    )

    print(
        "U     : undo"
    )

    print(
        "R     : reset"
    )

    print(
        "ENTER : save"
    )

    print(
        "Q/ESC : quit"
    )

    print(
        "=========================================="
    )

    print()


    cap = cv2.VideoCapture(
        rtsp_url,
        cv2.CAP_FFMPEG,
    )


    cap.set(
        cv2.CAP_PROP_BUFFERSIZE,
        1,
    )


    if not cap.isOpened():

        raise RuntimeError(
            "Could not connect to RTSP camera."
        )


    cv2.namedWindow(
        WINDOW_NAME,
        cv2.WINDOW_NORMAL,
    )


    cv2.setMouseCallback(
        WINDOW_NAME,
        mouse_callback,
    )


    latest_frame = None


    try:

        while True:

            # =================================================
            # LIVE MODE
            # =================================================

            if frozen_frame is None:

                ok, frame = (
                    cap.read()
                )


                if not ok:

                    continue


                latest_frame = (
                    frame.copy()
                )


                display_frame = (
                    frame
                )


            # =================================================
            # FROZEN MODE
            # =================================================

            else:

                display_frame = (
                    frozen_frame
                )


            preview = (
                draw_overlay(
                    display_frame
                )
            )


            cv2.imshow(
                WINDOW_NAME,
                preview,
            )


            key = (
                cv2.waitKey(
                    1
                )
                &
                0xFF
            )


            # =================================================
            # QUIT
            # =================================================

            if key in (
                ord("q"),
                ord("Q"),
                27,
            ):

                break


            # =================================================
            # SPACE
            # =================================================

            if key == 32:

                if frozen_frame is None:

                    if latest_frame is not None:

                        frozen_frame = (
                            latest_frame.copy()
                        )

                        clicked_points = []


                else:

                    frozen_frame = None

                    clicked_points = []


                continue


            # =================================================
            # UNDO
            # =================================================

            if key in (
                ord("u"),
                ord("U"),
            ):

                if clicked_points:

                    clicked_points.pop()


                continue


            # =================================================
            # RESET
            # =================================================

            if key in (
                ord("r"),
                ord("R"),
            ):

                clicked_points = []

                continue


            # =================================================
            # ENTER / SAVE
            # =================================================

            if key in (
                13,
                10,
            ):

                if frozen_frame is None:

                    print(
                        "Press SPACE first."
                    )

                    continue


                if len(
                    clicked_points
                ) != 4:

                    print(
                        "Need exactly 4 points."
                    )

                    continue


                save_calibration(
                    frozen_frame
                )


                break


    finally:

        cap.release()

        cv2.destroyAllWindows()


# ============================================================
# ENTRY
# ============================================================

if __name__ == "__main__":

    main()
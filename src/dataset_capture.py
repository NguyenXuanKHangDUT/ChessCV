import cv2
import numpy as np
import chess
import json
import os

from pathlib import Path
from datetime import datetime


# ============================================================
# CONFIG
# ============================================================

# IMOU RTSP camera.
#
# subtype=0 = MAIN STREAM.
# Set the camera MAIN STREAM to 3K in IMOU / ConfigTool.
# This code decodes that native stream first.
#
# The program does NOT ask for the URL at runtime.
IMOU_RTSP_URL = os.getenv(
    "IMOU_RTSP_URL",
    "rtsp://admin:L278A5D7@192.168.1.106:554/cam/realmonitor?channel=1&subtype=0"
).strip()


# ============================================================
# 3K -> WORKING FRAME
# ============================================================
#
# True (recommended):
#   camera streams native 3K
#   -> OpenCV/FFmpeg decodes native 3K
#   -> Python resizes to 1280x720
#   -> display/click/freeze/homography remain exactly like before
#
# False:
#   keep native frame for the whole pipeline.
#   Not recommended with the current click UI because the window can
#   be very large.
#
REFRAME_TO_720P = True

WORKING_WIDTH = 1280
WORKING_HEIGHT = 720

# Backward-compatible names used by the existing code.
CAMERA_WIDTH = WORKING_WIDTH
CAMERA_HEIGHT = WORKING_HEIGHT

RTSP_BUFFER_SIZE = 1
RTSP_OPEN_TIMEOUT_MS = 15000
RTSP_READ_TIMEOUT_MS = 15000

# Normalized board
BOARD_SIZE = 800
SQUARE_SIZE = BOARD_SIZE // 8   # 100px


# ============================================================
# PIECE MULTI-SCALE CONFIG
# ============================================================
#
# Occupancy:
#   100x100 exact square
#
# Piece classification:
#
#   140x140 = tight
#   180x180 = medium
#   220x220 = large
#
# Same target square is ALWAYS centered.
#
# Later during inference:
#
#   140 -> ConvNeXt
#   180 -> ConvNeXt
#   220 -> ConvNeXt
#
#   average probabilities
#          ↓
#   final piece class
#
# ============================================================

PIECE_CROP_SIZES = [
    140,
    180,
    220
]

MAX_PIECE_CROP_SIZE = max(
    PIECE_CROP_SIZES
)

MAX_PIECE_HALF = (
    MAX_PIECE_CROP_SIZE // 2
)


# ============================================================
# CONTEXT CONFIG
# ============================================================
#
# Outer points tell us how much REAL camera context
# exists outside the board.
#
# But output size is hard-limited to avoid giant
# warpPerspective images.
#
# ============================================================

CONTEXT_SAFETY_MARGIN = 20

MAX_CONTEXT_MARGIN = 250


# ============================================================
# PATHS
# ============================================================

PROJECT_ROOT = (
    Path(__file__)
    .resolve()
    .parent
    .parent
)

DATA_ROOT = (
    PROJECT_ROOT /
    "data"
)

RAW_DIR = (
    DATA_ROOT /
    "raw"
)

CONTEXT_DIR = (
    DATA_ROOT /
    "context"
)

BOARDS_DIR = (
    DATA_ROOT /
    "boards"
)

OCCUPANCY_DIR = (
    DATA_ROOT /
    "occupancy"
)

EMPTY_DIR = (
    OCCUPANCY_DIR /
    "empty"
)

OCCUPIED_DIR = (
    OCCUPANCY_DIR /
    "occupied"
)

PIECES_DIR = (
    DATA_ROOT /
    "pieces"
)


# ============================================================
# PIECE CLASS NAMES
# ============================================================

PIECE_NAMES = {

    chess.PAWN:
        "pawn",

    chess.KNIGHT:
        "knight",

    chess.BISHOP:
        "bishop",

    chess.ROOK:
        "rook",

    chess.QUEEN:
        "queen",

    chess.KING:
        "king"
}


# ============================================================
# GLOBAL STATE
# ============================================================
#
# Click order:
#
# 0 = OUTER TL
# 1 = OUTER TR
# 2 = OUTER BR
# 3 = OUTER BL
#
# 4 = BOARD TL
# 5 = BOARD TR
# 6 = BOARD BR
# 7 = BOARD BL
#
# ============================================================

clicked_points = []

frozen_frame = None


# ============================================================
# CREATE DATASET FOLDERS
# ============================================================

def create_dataset_folders():

    RAW_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    CONTEXT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    BOARDS_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    EMPTY_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    OCCUPIED_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    colors = [
        "white",
        "black"
    ]

    pieces = [
        "pawn",
        "knight",
        "bishop",
        "rook",
        "queen",
        "king"
    ]

    for color in colors:

        for piece in pieces:

            folder = (
                PIECES_DIR /
                f"{color}_{piece}"
            )

            folder.mkdir(
                parents=True,
                exist_ok=True
            )


# ============================================================
# POINT HELPERS
# ============================================================

def get_outer_points():

    if len(clicked_points) < 4:
        return []

    return clicked_points[:4]


def get_board_points():

    if len(clicked_points) < 8:
        return []

    return clicked_points[4:8]


# ============================================================
# MOUSE CALLBACK
# ============================================================

def mouse_callback(
    event,
    x,
    y,
    flags,
    param
):

    global clicked_points

    if event != cv2.EVENT_LBUTTONDOWN:
        return

    if frozen_frame is None:
        return

    if len(clicked_points) >= 8:
        return


    clicked_points.append(
        [x, y]
    )


    labels = [
        "OUTER TL",
        "OUTER TR",
        "OUTER BR",
        "OUTER BL",

        "BOARD TL",
        "BOARD TR",
        "BOARD BR",
        "BOARD BL"
    ]


    index = len(clicked_points) - 1

    print(
        f"{labels[index]} = ({x}, {y})"
    )


    if len(clicked_points) == 4:

        print()
        print(
            "OUTER region completed."
        )

        print(
            "Now click exact BOARD corners:"
        )

        print(
            "TL -> TR -> BR -> BL"
        )

        print()


    elif len(clicked_points) == 8:

        print()
        print(
            "All 8 points selected."
        )

        print(
            "Press ENTER to preview."
        )

        print()


# ============================================================
# DRAW SELECTED POINTS
# ============================================================

def draw_selected_points(frame):

    output = frame.copy()


    outer_labels = [
        "O-TL",
        "O-TR",
        "O-BR",
        "O-BL"
    ]


    board_labels = [
        "B-TL",
        "B-TR",
        "B-BR",
        "B-BL"
    ]


    # ========================================================
    # OUTER POINTS
    # ========================================================

    outer_count = min(
        len(clicked_points),
        4
    )


    for i in range(
        outer_count
    ):

        x, y = (
            clicked_points[i]
        )

        color = (
            0,
            255,
            255
        )

        cv2.circle(
            output,
            (x, y),
            8,
            color,
            -1
        )

        cv2.putText(
            output,
            outer_labels[i],

            (
                x + 10,
                y - 10
            ),

            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,

            color,
            2
        )


    if outer_count == 4:

        polygon = np.array(
            clicked_points[:4],
            dtype=np.int32
        )

        cv2.polylines(
            output,
            [polygon],
            True,

            (
                0,
                255,
                255
            ),

            2
        )


    # ========================================================
    # BOARD POINTS
    # ========================================================

    board_clicks = (
        clicked_points[4:8]
    )


    for i, point in enumerate(
        board_clicks
    ):

        x, y = point

        color = (
            0,
            255,
            0
        )

        cv2.circle(
            output,
            (x, y),
            8,
            color,
            -1
        )

        cv2.putText(
            output,
            board_labels[i],

            (
                x + 10,
                y - 10
            ),

            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,

            color,
            2
        )


    if len(board_clicks) == 4:

        polygon = np.array(
            board_clicks,
            dtype=np.int32
        )

        cv2.polylines(
            output,
            [polygon],
            True,

            (
                0,
                255,
                0
            ),

            2
        )


    # ========================================================
    # STATUS
    # ========================================================

    if len(clicked_points) < 4:

        status = (
            "OUTER: "
            f"{len(clicked_points)}/4"
        )

    elif len(clicked_points) < 8:

        status = (
            "BOARD: "
            f"{len(clicked_points) - 4}/4"
        )

    else:

        status = (
            "READY - Press ENTER"
        )


    cv2.putText(
        output,
        status,

        (
            20,
            75
        ),

        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,

        (
            255,
            255,
            255
        ),

        2
    )


    return output


# ============================================================
# VALIDATE OUTER AREA
# ============================================================

def validate_outer_contains_board():

    outer = np.array(
        get_outer_points(),
        dtype=np.float32
    )

    board_points = (
        get_board_points()
    )


    contour = outer.reshape(
        (
            -1,
            1,
            2
        )
    )


    for point in board_points:

        test = cv2.pointPolygonTest(
            contour,

            (
                float(point[0]),
                float(point[1])
            ),

            False
        )


        if test < 0:

            return False


    return True


# ============================================================
# CREATE NORMALIZED CONTEXT
# ============================================================
#
# Physical camera setup:
#
# WHITE = LEFT
# BLACK = RIGHT
#
#
# Normalized output:
#
# BLACK = TOP
# WHITE = BOTTOM
#
#
# Raw camera board:
#
# raw TL -> canonical BL
# raw TR -> canonical TL
# raw BR -> canonical TR
# raw BL -> canonical BR
#
# ============================================================

def create_normalized_context(
    frame
):

    if len(clicked_points) != 8:

        raise ValueError(
            "Need exactly 8 points."
        )


    # ========================================================
    # RAW POINTS
    # ========================================================

    outer_points = np.array(
        get_outer_points(),
        dtype=np.float32
    )


    board_points = np.array(
        get_board_points(),
        dtype=np.float32
    )


    # ========================================================
    # CANONICAL BOARD
    # ========================================================

    B = BOARD_SIZE - 1


    canonical_board = np.array(
        [

            # raw TL -> bottom-left
            [
                0,
                B
            ],

            # raw TR -> top-left
            [
                0,
                0
            ],

            # raw BR -> top-right
            [
                B,
                0
            ],

            # raw BL -> bottom-right
            [
                B,
                B
            ]

        ],

        dtype=np.float32
    )


    # ========================================================
    # HOMOGRAPHY FOR BOARD
    # ========================================================

    H_base = cv2.getPerspectiveTransform(
        board_points,
        canonical_board
    )


    # ========================================================
    # TRANSFORM OUTER POINTS
    # ========================================================

    outer_input = (
        outer_points.reshape(
            (
                -1,
                1,
                2
            )
        )
    )


    transformed_outer = (
        cv2.perspectiveTransform(
            outer_input,
            H_base
        )
        .reshape(
            (
                -1,
                2
            )
        )
    )


    # ========================================================
    # CALCULATE REAL CONTEXT
    # ========================================================

    min_x = float(
        np.min(
            transformed_outer[:, 0]
        )
    )

    max_x = float(
        np.max(
            transformed_outer[:, 0]
        )
    )

    min_y = float(
        np.min(
            transformed_outer[:, 1]
        )
    )

    max_y = float(
        np.max(
            transformed_outer[:, 1]
        )
    )


    required_left = max(
        0.0,
        -min_x
    )

    required_top = max(
        0.0,
        -min_y
    )

    required_right = max(
        0.0,
        max_x - B
    )

    required_bottom = max(
        0.0,
        max_y - B
    )


    # ========================================================
    # REQUIRED CONTEXT
    #
    # Need at least half of largest piece crop
    #
    # largest = 220
    # half = 110
    #
    # ========================================================

    required_context = max(

        required_left,

        required_top,

        required_right,

        required_bottom,

        float(
            MAX_PIECE_HALF
        )
    )


    context_margin = int(
        np.ceil(

            required_context
            +
            CONTEXT_SAFETY_MARGIN
        )
    )


    # ========================================================
    # SAFETY CAP
    # ========================================================

    if context_margin > MAX_CONTEXT_MARGIN:

        raise RuntimeError(

            "\nContext is too large.\n"

            f"Required margin: "
            f"{context_margin}px\n"

            f"Maximum allowed: "
            f"{MAX_CONTEXT_MARGIN}px\n\n"

            "Probably one BOARD corner "
            "or OUTER corner was clicked badly.\n"

            "Press R and select again."
        )


    # ========================================================
    # FINAL CANVAS
    # ========================================================

    context_size = (
        BOARD_SIZE
        +
        2 * context_margin
    )


    # ========================================================
    # TRANSLATE BOARD TO CENTER
    # ========================================================

    T = np.array(
        [

            [
                1.0,
                0.0,
                context_margin
            ],

            [
                0.0,
                1.0,
                context_margin
            ],

            [
                0.0,
                0.0,
                1.0
            ]

        ],

        dtype=np.float64
    )


    H = (
        T @ H_base
    )


    # ========================================================
    # WARP FULL FRAME
    # ========================================================

    context = cv2.warpPerspective(
        frame,
        H,

        (
            context_size,
            context_size
        )
    )


    # ========================================================
    # EXACT BOARD LOCATION
    # ========================================================

    board_x = context_margin
    board_y = context_margin


    board = context[

        board_y:
        board_y + BOARD_SIZE,

        board_x:
        board_x + BOARD_SIZE

    ].copy()


    # ========================================================
    # TRANSFORM OUTER FOR PREVIEW
    # ========================================================

    transformed_outer_final = (

        cv2.perspectiveTransform(

            outer_input,

            H.astype(
                np.float32
            )

        )

        .reshape(
            (
                -1,
                2
            )
        )
    )


    return {

        "context":
            context,

        "board":
            board,

        "H":
            H,

        "board_origin":
            (
                board_x,
                board_y
            ),

        "context_size":
            (
                context_size,
                context_size
            ),

        "context_margin":
            context_margin,

        "transformed_outer":
            transformed_outer_final
    }


# ============================================================
# CHESS SQUARE MAPPING
# ============================================================

def get_square_name(
    row,
    col
):

    files = "abcdefgh"

    return (
        f"{files[col]}"
        f"{8 - row}"
    )


def get_chess_square(
    row,
    col
):

    file_index = col

    rank_index = (
        7 - row
    )


    return chess.square(
        file_index,
        rank_index
    )


# ============================================================
# DRAW NORMALIZED PREVIEW
# ============================================================

def draw_context_preview(
    result
):

    output = (
        result["context"]
        .copy()
    )


    board_x, board_y = (
        result[
            "board_origin"
        ]
    )


    # ========================================================
    # GRID
    # ========================================================

    for i in range(9):

        x = (
            board_x
            +
            i * SQUARE_SIZE
        )

        y = (
            board_y
            +
            i * SQUARE_SIZE
        )


        cv2.line(
            output,

            (
                x,
                board_y
            ),

            (
                x,
                board_y + BOARD_SIZE
            ),

            (
                0,
                0,
                255
            ),

            1
        )


        cv2.line(
            output,

            (
                board_x,
                y
            ),

            (
                board_x + BOARD_SIZE,
                y
            ),

            (
                0,
                0,
                255
            ),

            1
        )


    # ========================================================
    # LABELS
    # ========================================================

    for row in range(8):

        for col in range(8):

            name = get_square_name(
                row,
                col
            )


            x = (
                board_x
                +
                col * SQUARE_SIZE
                +
                5
            )


            y = (
                board_y
                +
                row * SQUARE_SIZE
                +
                18
            )


            cv2.putText(
                output,
                name,

                (
                    x,
                    y
                ),

                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,

                (
                    0,
                    0,
                    255
                ),

                1,

                cv2.LINE_AA
            )


    # ========================================================
    # BOARD OUTLINE
    # ========================================================

    cv2.rectangle(
        output,

        (
            board_x,
            board_y
        ),

        (
            board_x + BOARD_SIZE,
            board_y + BOARD_SIZE
        ),

        (
            0,
            255,
            0
        ),

        3
    )


    # ========================================================
    # OUTER REGION
    # ========================================================

    outer_polygon = (

        result[
            "transformed_outer"
        ]

        .astype(
            np.int32
        )

        .reshape(
            (
                -1,
                1,
                2
            )
        )
    )


    cv2.polylines(
        output,
        [outer_polygon],
        True,

        (
            0,
            255,
            255
        ),

        2
    )


    # ========================================================
    # INFO
    # ========================================================

    cv2.putText(
        output,

        (
            "Context margin: "
            f"{result['context_margin']} px"
        ),

        (
            15,
            30
        ),

        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,

        (
            255,
            255,
            255
        ),

        2
    )


    return output


# ============================================================
# FIT PREVIEW TO SCREEN
# ============================================================

def fit_preview(
    image,
    max_width=1000,
    max_height=850
):

    height, width = (
        image.shape[:2]
    )


    scale = min(

        1.0,

        max_width / width,

        max_height / height
    )


    if scale >= 1.0:

        return image


    new_width = int(
        width * scale
    )

    new_height = int(
        height * scale
    )


    return cv2.resize(
        image,

        (
            new_width,
            new_height
        )
    )


# ============================================================
# CONFIRM RESULT
# ============================================================

def confirm_result(
    result
):

    preview = (
        draw_context_preview(
            result
        )
    )


    preview = (
        fit_preview(
            preview
        )
    )


    cv2.namedWindow(
        "Dataset Preview"
    )


    cv2.imshow(
        "Dataset Preview",
        preview
    )


    print()
    print(
        "========================================"
    )

    print(
        "CHECK DATASET PREVIEW"
    )

    print()

    print(
        "GREEN = exact 800x800 board"
    )

    print(
        "YELLOW = outer context"
    )

    print()

    print(
        "ENTER = ACCEPT"
    )

    print(
        "Any other key = DISCARD"
    )

    print(
        "========================================"
    )

    print()


    key = (
        cv2.waitKey(0)
        &
        0xFF
    )


    cv2.destroyWindow(
        "Dataset Preview"
    )


    return key in (
        13,
        10
    )


# ============================================================
# OCCUPANCY CROP
# ============================================================

def extract_occupancy_crop(
    board,
    row,
    col
):

    x1 = (
        col *
        SQUARE_SIZE
    )

    y1 = (
        row *
        SQUARE_SIZE
    )

    x2 = (
        x1 +
        SQUARE_SIZE
    )

    y2 = (
        y1 +
        SQUARE_SIZE
    )


    crop = board[
        y1:y2,
        x1:x2
    ]


    return crop.copy()


# ============================================================
# PIECE MULTI-SCALE CROP
# ============================================================
#
# Example:
#
# square center
#      ↓
#
# 140x140
# 180x180
# 220x220
#
# All have SAME center.
#
# ============================================================

def extract_piece_crop(
    context,
    board_origin,
    row,
    col,
    crop_size
):

    board_x, board_y = (
        board_origin
    )


    # ========================================================
    # CENTER OF TARGET SQUARE
    # ========================================================

    center_x = (

        board_x

        +
        col * SQUARE_SIZE

        +
        SQUARE_SIZE // 2
    )


    center_y = (

        board_y

        +
        row * SQUARE_SIZE

        +
        SQUARE_SIZE // 2
    )


    half = (
        crop_size // 2
    )


    x1 = (
        center_x - half
    )

    y1 = (
        center_y - half
    )


    x2 = (
        x1 + crop_size
    )

    y2 = (
        y1 + crop_size
    )


    crop = context[
        y1:y2,
        x1:x2
    ]


    if (
        crop.shape[0] != crop_size
        or
        crop.shape[1] != crop_size
    ):

        raise RuntimeError(

            f"Invalid piece crop. "

            f"Expected "
            f"{crop_size}x{crop_size}, "

            f"got "
            f"{crop.shape[1]}x"
            f"{crop.shape[0]}"
        )


    return crop.copy()


# ============================================================
# READ FEN
# ============================================================

def read_fen():

    print()

    print(
        "Paste FEN from Chess.com / Lichess."
    )

    print(
        "Full FEN or board-only FEN supported."
    )

    print()

    print(
        "Blank ENTER = cancel sample."
    )

    print()


    while True:

        fen = input(
            "FEN > "
        ).strip()


        if fen == "":

            return (
                None,
                None
            )


        try:


            # =================================================
            # FULL FEN
            # =================================================

            if " " in fen:

                board = chess.Board(
                    fen
                )

                return (
                    board,
                    fen
                )


            # =================================================
            # BOARD-ONLY FEN
            # =================================================

            board = chess.Board(
                None
            )

            board.set_board_fen(
                fen
            )


            return (
                board,
                fen
            )


        except ValueError as error:

            print()

            print(
                "INVALID FEN:"
            )

            print(
                error
            )

            print()

            print(
                "Paste again."
            )

            print()


# ============================================================
# SAVE DATASET SAMPLE
# ============================================================

def save_dataset_sample(
    raw_frame,
    result,
    fen_board,
    fen_text
):

    sample_id = (
        datetime.now()
        .strftime(
            "%Y%m%d_%H%M%S_%f"
        )[:-3]
    )


    context = (
        result["context"]
    )

    board = (
        result["board"]
    )

    H = (
        result["H"]
    )

    board_origin = (
        result[
            "board_origin"
        ]
    )


    # ========================================================
    # SAVE RAW CAMERA IMAGE
    # ========================================================

    raw_path = (

        RAW_DIR /

        f"{sample_id}.png"
    )


    cv2.imwrite(
        str(raw_path),
        raw_frame
    )


    # ========================================================
    # SAVE FULL NORMALIZED CONTEXT
    # ========================================================

    context_path = (

        CONTEXT_DIR /

        f"{sample_id}.png"
    )


    cv2.imwrite(
        str(context_path),
        context
    )


    # ========================================================
    # SAVE EXACT 800x800 BOARD
    # ========================================================

    board_path = (

        BOARDS_DIR /

        f"{sample_id}.png"
    )


    cv2.imwrite(
        str(board_path),
        board
    )


    # ========================================================
    # METADATA
    # ========================================================

    metadata = {

        "sample_id":
            sample_id,

        "fen":
            fen_text,

        "board_fen":
            fen_board.board_fen(),

        "outer_points":
            get_outer_points(),

        "board_points":
            get_board_points(),

        "homography":
            H.tolist(),

        "board_size":
            BOARD_SIZE,

        "square_size":
            SQUARE_SIZE,

        "board_origin":
            list(
                board_origin
            ),

        "context_size":
            list(
                result[
                    "context_size"
                ]
            ),

        "context_margin":
            result[
                "context_margin"
            ],

        "occupancy_crop_size":
            SQUARE_SIZE,

        "piece_crop_sizes":
            PIECE_CROP_SIZES,

        "orientation":
            "black_top_white_bottom",

        "camera_source":
            "imou_rtsp",

        "working_frame_size": [
            CAMERA_WIDTH,
            CAMERA_HEIGHT
        ]
    }


    metadata_path = (

        BOARDS_DIR /

        f"{sample_id}.json"
    )


    with open(
        metadata_path,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            metadata,
            file,
            indent=4
        )


    # ========================================================
    # COUNTERS
    # ========================================================

    empty_count = 0

    occupied_count = 0

    piece_count = 0

    saved_piece_crops = 0

    piece_counts = {}


    # ========================================================
    # LOOP 64 SQUARES
    # ========================================================

    for row in range(8):

        for col in range(8):


            # =================================================
            # CHESS SQUARE
            # =================================================

            square = get_chess_square(
                row,
                col
            )


            square_name = (
                chess.square_name(
                    square
                )
            )


            piece = (
                fen_board.piece_at(
                    square
                )
            )


            occupancy_filename = (

                f"{sample_id}_"
                f"{square_name}.png"
            )


            # =================================================
            # RESNET OCCUPANCY
            # =================================================

            occupancy_crop = (
                extract_occupancy_crop(
                    board,
                    row,
                    col
                )
            )


            # =================================================
            # EMPTY
            # =================================================

            if piece is None:

                path = (

                    EMPTY_DIR /

                    occupancy_filename
                )


                cv2.imwrite(
                    str(path),
                    occupancy_crop
                )


                empty_count += 1


            # =================================================
            # OCCUPIED
            # =================================================

            else:

                path = (

                    OCCUPIED_DIR /

                    occupancy_filename
                )


                cv2.imwrite(
                    str(path),
                    occupancy_crop
                )


                occupied_count += 1

                piece_count += 1


                # =============================================
                # PIECE CLASS
                # =============================================

                color = (

                    "white"

                    if piece.color
                    == chess.WHITE

                    else

                    "black"
                )


                piece_name = (
                    PIECE_NAMES[
                        piece.piece_type
                    ]
                )


                class_name = (

                    f"{color}_"
                    f"{piece_name}"
                )


                # =============================================
                # MULTI-SCALE CROPS
                # =============================================

                for crop_size in (
                    PIECE_CROP_SIZES
                ):

                    piece_crop = (
                        extract_piece_crop(
                            context,
                            board_origin,
                            row,
                            col,
                            crop_size
                        )
                    )


                    piece_filename = (

                        f"{sample_id}_"
                        f"{square_name}_"
                        f"s{crop_size}.png"
                    )


                    piece_path = (

                        PIECES_DIR /

                        class_name /

                        piece_filename
                    )


                    cv2.imwrite(
                        str(piece_path),
                        piece_crop
                    )


                    saved_piece_crops += 1


                # =============================================
                # COUNT ACTUAL PIECES
                # =============================================

                piece_counts[
                    class_name
                ] = (

                    piece_counts.get(
                        class_name,
                        0
                    )

                    +
                    1
                )


    # ========================================================
    # SUMMARY
    # ========================================================

    print()

    print(
        "========================================"
    )

    print(
        "DATASET SAMPLE SAVED"
    )

    print(
        "========================================"
    )


    print(
        f"Sample ID:"
        f" {sample_id}"
    )


    print()


    print(
        "OCCUPANCY / ResNet-18"
    )


    print(
        f"  Empty     : "
        f"{empty_count}"
    )


    print(
        f"  Occupied  : "
        f"{occupied_count}"
    )


    print(
        f"  Total     : "
        f"{empty_count + occupied_count}"
    )


    print(
        f"  Crop size : "
        f"{SQUARE_SIZE}x"
        f"{SQUARE_SIZE}"
    )


    print()


    print(
        "PIECES / ConvNeXt-Tiny"
    )


    print(
        f"  Actual pieces : "
        f"{piece_count}"
    )


    print(
        f"  Scales        : "
        f"{PIECE_CROP_SIZES}"
    )


    print(
        f"  Saved crops   : "
        f"{saved_piece_crops}"
    )


    print()


    print(
        "Piece counts:"
    )


    for name in sorted(
        piece_counts.keys()
    ):

        print(

            f"  {name:<16}"
            f" {piece_counts[name]}"
        )


    print()

    print(
        "========================================"
    )

    print()


# ============================================================
# OPEN IMOU RTSP CAMERA
# ============================================================

def open_imou_camera():

    # subtype=0 in IMOU_RTSP_URL is the camera MAIN STREAM.
    # If MAIN STREAM is configured as 3K, RTSP delivers 3K here.
    os.environ[
        "OPENCV_FFMPEG_CAPTURE_OPTIONS"
    ] = "rtsp_transport;tcp"

    print()
    print(
        "Opening IMOU MAIN RTSP stream..."
    )
    print(
        "Requested: subtype=0 (main stream)"
    )

    params = []

    if hasattr(
        cv2,
        "CAP_PROP_OPEN_TIMEOUT_MSEC"
    ):
        params.extend(
            [
                cv2.CAP_PROP_OPEN_TIMEOUT_MSEC,
                RTSP_OPEN_TIMEOUT_MS
            ]
        )

    if hasattr(
        cv2,
        "CAP_PROP_READ_TIMEOUT_MSEC"
    ):
        params.extend(
            [
                cv2.CAP_PROP_READ_TIMEOUT_MSEC,
                RTSP_READ_TIMEOUT_MS
            ]
        )

    # Try FFmpeg with hardware acceleration first when supported.
    hw_params = list(params)

    if (
        hasattr(
            cv2,
            "CAP_PROP_HW_ACCELERATION"
        )
        and
        hasattr(
            cv2,
            "VIDEO_ACCELERATION_ANY"
        )
    ):
        hw_params.extend(
            [
                cv2.CAP_PROP_HW_ACCELERATION,
                cv2.VIDEO_ACCELERATION_ANY
            ]
        )

    cap = None

    try:
        cap = cv2.VideoCapture(
            IMOU_RTSP_URL,
            cv2.CAP_FFMPEG,
            hw_params
        )
    except Exception:
        cap = None

    # Retry without hardware acceleration.
    if (
        cap is None
        or
        not cap.isOpened()
    ):
        if cap is not None:
            cap.release()

        print(
            "HW decode open failed. "
            "Retrying normal FFmpeg..."
        )

        try:
            cap = cv2.VideoCapture(
                IMOU_RTSP_URL,
                cv2.CAP_FFMPEG,
                params
            )
        except Exception:
            cap = None

    # Final fallback.
    if (
        cap is None
        or
        not cap.isOpened()
    ):
        if cap is not None:
            cap.release()

        print(
            "FFmpeg backend failed. "
            "Trying default OpenCV backend..."
        )

        cap = cv2.VideoCapture(
            IMOU_RTSP_URL
        )

    if not cap.isOpened():
        raise RuntimeError(
            "Cannot open IMOU RTSP main stream.\n"
            "Check IP / port 554 / subtype=0 / camera main-stream settings."
        )

    cap.set(
        cv2.CAP_PROP_BUFFERSIZE,
        RTSP_BUFFER_SIZE
    )

    # Read one actual frame so we know what resolution RTSP really sends.
    ret, native_frame = cap.read()

    if (
        not ret
        or
        native_frame is None
    ):
        cap.release()
        raise RuntimeError(
            "RTSP connection opened, but the main-stream frame "
            "could not be decoded."
        )

    native_h, native_w = (
        native_frame.shape[:2]
    )

    fps = cap.get(
        cv2.CAP_PROP_FPS
    )

    print()
    print(
        f"Native RTSP frame: {native_w}x{native_h}"
    )
    print(
        f"Reported FPS: {fps:.2f}"
    )

    if REFRAME_TO_720P:
        print(
            "Working pipeline: "
            f"{native_w}x{native_h} -> "
            f"{WORKING_WIDTH}x{WORKING_HEIGHT}"
        )
        print(
            "Resize happens AFTER native RTSP decode."
        )
    else:
        print(
            "Working pipeline: native frame (no resize)"
        )

    print(
        "Controls remain the same as before."
    )
    print()

    return cap


# ============================================================
# READ ONE IMOU FRAME
# ============================================================

def read_imou_frame(
    cap
):

    ret, frame = cap.read()

    if (
        not ret
        or
        frame is None
    ):
        return (
            False,
            None
        )

    # The camera stream itself can stay 3K.
    # We only resize after decoding so the rest of the current project
    # keeps exactly the same 1280x720 click / freeze / homography system.
    if REFRAME_TO_720P:

        height, width = (
            frame.shape[:2]
        )

        if (
            width != WORKING_WIDTH
            or
            height != WORKING_HEIGHT
        ):
            frame = cv2.resize(
                frame,
                (
                    WORKING_WIDTH,
                    WORKING_HEIGHT
                ),
                interpolation=cv2.INTER_AREA
            )

    return (
        True,
        frame
    )


# ============================================================
# MAIN
# ============================================================

def main():

    global frozen_frame

    global clicked_points


    create_dataset_folders()


    # ========================================================
    # OPEN IMOU CAMERA
    # ========================================================

    cap = open_imou_camera()


    # ========================================================
    # CAMERA WINDOW
    # ========================================================

    cv2.namedWindow(
        "Camera"
    )


    cv2.setMouseCallback(
        "Camera",
        mouse_callback
    )


    # ========================================================
    # HELP
    # ========================================================

    print()

    print(
        "========================================"
    )

    print(
        "PBL4 CHESS DATASET CAPTURE"
    )

    print(
        "========================================"
    )


    print()


    print(
        "SPACE = freeze / unfreeze"
    )


    print()


    print(
        "FIRST 4 CLICKS:"
    )

    print(
        "OUTER TL -> TR -> BR -> BL"
    )


    print(
        "OUTER should contain full "
        "heads/bodies of edge pieces."
    )


    print()


    print(
        "NEXT 4 CLICKS:"
    )

    print(
        "BOARD TL -> TR -> BR -> BL"
    )


    print(
        "BOARD = exact corners of 8x8 area."
    )


    print()


    print(
        "ENTER = preview"
    )

    print(
        "U     = undo last point"
    )

    print(
        "R     = reset all points"
    )

    print(
        "Q     = quit"
    )


    print()

    print(
        "========================================"
    )

    print()


    # ========================================================
    # MAIN LOOP
    # ========================================================

    while True:


        # ====================================================
        # LIVE
        # ====================================================

        if frozen_frame is None:


            ret, frame = (
                read_imou_frame(cap)
            )


            if not ret:

                print(
                    "Failed to read frame."
                )

                break


            display = (
                frame.copy()
            )


            cv2.putText(
                display,

                "LIVE - SPACE to freeze",

                (
                    20,
                    40
                ),

                cv2.FONT_HERSHEY_SIMPLEX,

                1,

                (
                    0,
                    255,
                    0
                ),

                2
            )


        # ====================================================
        # FROZEN
        # ====================================================

        else:

            display = (
                draw_selected_points(
                    frozen_frame
                )
            )


            cv2.putText(
                display,

                "FROZEN",

                (
                    20,
                    40
                ),

                cv2.FONT_HERSHEY_SIMPLEX,

                1,

                (
                    0,
                    0,
                    255
                ),

                2
            )


        # ====================================================
        # SHOW
        # ====================================================

        cv2.imshow(
            "Camera",
            display
        )


        key = (
            cv2.waitKey(1)
            &
            0xFF
        )


        # ====================================================
        # SPACE
        # ====================================================

        if key == 32:


            # LIVE -> FROZEN
            if frozen_frame is None:

                frozen_frame = (
                    frame.copy()
                )

                clicked_points = []


                print()

                print(
                    "Frame frozen."
                )

                print()

                print(
                    "Click OUTER:"
                )

                print(
                    "TL -> TR -> BR -> BL"
                )

                print()


            # FROZEN -> LIVE
            else:

                frozen_frame = None

                clicked_points = []


                print(
                    "Back to LIVE."
                )


        # ====================================================
        # UNDO
        # ====================================================

        elif key in (
            ord("u"),
            ord("U")
        ):

            if clicked_points:

                removed = (
                    clicked_points.pop()
                )

                print(
                    f"Undo: {removed}"
                )


        # ====================================================
        # RESET
        # ====================================================

        elif key in (
            ord("r"),
            ord("R")
        ):

            clicked_points = []

            print(
                "All points reset."
            )


        # ====================================================
        # ENTER
        # ====================================================

        elif key in (
            13,
            10
        ):


            # ------------------------------------------------
            # Must be frozen
            # ------------------------------------------------

            if frozen_frame is None:

                print(
                    "Press SPACE first."
                )

                continue


            # ------------------------------------------------
            # Need exactly 8
            # ------------------------------------------------

            if len(clicked_points) != 8:

                print()

                print(
                    "Need exactly 8 points."
                )

                print(
                    f"Current: "
                    f"{len(clicked_points)}/8"
                )

                continue


            # ------------------------------------------------
            # Outer validation
            # ------------------------------------------------

            if not validate_outer_contains_board():

                print()

                print(
                    "ERROR:"
                )

                print(
                    "All BOARD corners must "
                    "be inside OUTER polygon."
                )

                print()

                print(
                    "Press R and select again."
                )

                continue


            # =================================================
            # BUILD NORMALIZED CONTEXT
            # =================================================

            try:

                result = (
                    create_normalized_context(
                        frozen_frame
                    )
                )


            except Exception as error:

                print()

                print(
                    "Cannot build context:"
                )

                print(
                    error
                )

                print()

                continue


            # =================================================
            # PREVIEW
            # =================================================

            accepted = (
                confirm_result(
                    result
                )
            )


            # =================================================
            # DISCARD
            # =================================================

            if not accepted:

                print()

                print(
                    "Sample discarded."
                )

                print(
                    "Returning to LIVE..."
                )


                frozen_frame = None

                clicked_points = []


                continue


            # =================================================
            # ACCEPT
            # =================================================

            print()

            print(
                "Image accepted."
            )


            # =================================================
            # FEN
            # =================================================

            fen_board, fen_text = (
                read_fen()
            )


            # =================================================
            # FEN CANCEL
            # =================================================

            if fen_board is None:

                print()

                print(
                    "Sample cancelled."
                )


                frozen_frame = None

                clicked_points = []


                continue


            # =================================================
            # SAVE DATASET
            # =================================================

            try:

                save_dataset_sample(

                    frozen_frame,

                    result,

                    fen_board,

                    fen_text
                )


            except Exception as error:

                print()

                print(
                    "ERROR WHILE SAVING:"
                )

                print(
                    error
                )

                print()

                frozen_frame = None

                clicked_points = []

                continue


            # =================================================
            # NEXT POSITION
            # =================================================

            frozen_frame = None

            clicked_points = []


            print(
                "Ready for next position."
            )

            print()


        # ====================================================
        # QUIT
        # ====================================================

        elif key in (
            ord("q"),
            ord("Q"),
            27
        ):

            break


    # ========================================================
    # CLEANUP
    # ========================================================

    cap.release()

    cv2.destroyAllWindows()


# ============================================================
# ENTRY
# ============================================================

if __name__ == "__main__":

    main()
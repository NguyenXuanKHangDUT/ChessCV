from __future__ import annotations

import chess
import numpy as np

from backend.app.vision.geometry import (
    create_normalized_context,
)
from backend.app.vision.inference import (
    predict_occupancy,
    predict_pieces,
)
from backend.app.vision.model_manager import (
    get_model_manager,
)
from backend.app.vision.board_detector import (
    create_outer_points_from_board,
    detect_board_corners,
)


# ============================================================
# PIECE MAP
# ============================================================

PIECE_TYPE_MAP = {
    "pawn":
        chess.PAWN,
    "knight":
        chess.KNIGHT,
    "bishop":
        chess.BISHOP,
    "rook":
        chess.ROOK,
    "queen":
        chess.QUEEN,
    "king":
        chess.KING,
}


# ============================================================
# ROW/COL -> CHESS SQUARE
# ============================================================

def get_chess_square(
    row: int,
    col: int,
):
    # Canonical normalized board:
    # row 0 -> rank 8
    # row 7 -> rank 1
    # col 0 -> file a
    # col 7 -> file h
    return chess.square(
        col,
        7 - row,
    )


# ============================================================
# CLASS -> CHESS PIECE
# ============================================================

def class_to_chess_piece(
    class_name: str,
):
    color_name, piece_name = (
        class_name.split(
            "_",
            1,
        )
    )

    if color_name == "white":
        color = chess.WHITE
    elif color_name == "black":
        color = chess.BLACK
    else:
        raise ValueError(
            f"Invalid piece color: {color_name}"
        )

    if piece_name not in PIECE_TYPE_MAP:
        raise ValueError(
            f"Invalid piece type: {piece_name}"
        )

    return chess.Piece(
        PIECE_TYPE_MAP[
            piece_name
        ],
        color,
    )


# ============================================================
# RECOGNIZE
# ============================================================

def recognize_position(
    frame: np.ndarray,
    outer_points: list[list[float]],
    board_points: list[list[float]],
    camera_orientation: str = "white_left",
):
    manager = get_model_manager()

    # ========================================================
    # GEOMETRY
    # ========================================================

    normalized = create_normalized_context(
        frame=frame,
        outer_points=
            outer_points,
        board_points=
            board_points,
        piece_crop_sizes=
            manager.piece_crop_sizes,
        camera_orientation=
            camera_orientation,
    )

    board_image = normalized[
        "board"
    ]

    context = normalized[
        "context"
    ]

    board_origin = normalized[
        "board_origin"
    ]

    # ========================================================
    # MODEL 1: OCCUPANCY
    # ========================================================

    occupancy_results = (
        predict_occupancy(
            manager,
            board_image,
        )
    )

    # ========================================================
    # MODEL 2: PIECES
    # ========================================================

    piece_results = (
        predict_pieces(
            manager,
            context,
            board_origin,
            occupancy_results,
        )
    )

    # ========================================================
    # BUILD CHESS BOARD
    # ========================================================

    chess_board = chess.Board(
        None
    )

    squares = {}

    for row in range(8):
        for col in range(8):
            index = (
                row * 8
                + col
            )

            square = get_chess_square(
                row,
                col,
            )

            square_name = (
                chess.square_name(
                    square
                )
            )

            occupancy = (
                occupancy_results[
                    index
                ]
            )

            square_result = {
                "square":
                    square_name,
                "occupied":
                    occupancy[
                        "occupied"
                    ],
                "occupancy_confidence":
                    occupancy[
                        "confidence"
                    ],
                "empty_probability":
                    occupancy[
                        "empty_probability"
                    ],
                "occupied_probability":
                    occupancy[
                        "occupied_probability"
                    ],
                "piece":
                    None,
                "piece_confidence":
                    None,
                "scale_predictions":
                    [],
            }

            if occupancy[
                "occupied"
            ]:
                piece_result = (
                    piece_results.get(
                        index
                    )
                )

                if piece_result is None:
                    raise RuntimeError(
                        "Occupied square did not "
                        "receive a piece prediction."
                    )

                class_name = (
                    piece_result[
                        "piece"
                    ]
                )

                piece = (
                    class_to_chess_piece(
                        class_name
                    )
                )

                chess_board.set_piece_at(
                    square,
                    piece,
                )

                square_result[
                    "piece"
                ] = class_name

                square_result[
                    "piece_confidence"
                ] = (
                    piece_result[
                        "confidence"
                    ]
                )

                square_result[
                    "scale_predictions"
                ] = (
                    piece_result[
                        "scale_predictions"
                    ]
                )

            squares[
                square_name
            ] = square_result

    board_fen = (
        chess_board.board_fen()
    )

    return {
        "board_fen":
            board_fen,
        "squares":
            squares,
        "context_margin":
            normalized[
                "context_margin"
            ],
        "camera_orientation":
            camera_orientation,
    }


# ============================================================
# AUTO RECOGNIZE
# ============================================================

def recognize_position_auto(
    frame: np.ndarray,
    camera_orientation: str = "white_left",
):
    detection = detect_board_corners(
        frame
    )

    board_points = detection[
        "board_points"
    ]

    outer_points = (
        create_outer_points_from_board(
            board_points,
            scale=1.18,
        )
    )

    result = recognize_position(
        frame=frame,
        outer_points=
            outer_points,
        board_points=
            board_points,
        camera_orientation=
            camera_orientation,
    )

    result[
        "detected_board_points"
    ] = board_points

    result[
        "board_detection_score"
    ] = detection[
        "score"
    ]

    result[
        "board_checker_score"
    ] = detection.get(
        "checker_score"
    )

    result[
        "board_detection_method"
    ] = detection.get(
        "method"
    )

    return result

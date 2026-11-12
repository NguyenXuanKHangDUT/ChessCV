import cv2
import chess

from pathlib import Path

import torch
from torch import nn

from PIL import Image
from torchvision import transforms
from torchvision.models import (
    resnet18,
    convnext_tiny
)

import dataset_capture as dc


# ============================================================
# PATHS
# ============================================================

PROJECT_ROOT = (
    Path(__file__)
    .resolve()
    .parent
    .parent
)

OCCUPANCY_MODEL_PATH = (
    PROJECT_ROOT
    / "models"
    / "occupancy"
    / "resnet18_occupancy_best.pt"
)

PIECE_MODEL_PATH = (
    PROJECT_ROOT
    / "models"
    / "pieces"
    / "convnext_tiny_pieces_best.pt"
)


# ============================================================
# DEVICE
# ============================================================

DEVICE = torch.device(
    "cuda"
    if torch.cuda.is_available()
    else "cpu"
)


# ============================================================
# LOAD OCCUPANCY MODEL
# ============================================================

def load_occupancy_model():

    checkpoint = torch.load(
        OCCUPANCY_MODEL_PATH,
        map_location=DEVICE,
        weights_only=False
    )

    model = resnet18(
        weights=None
    )

    model.fc = nn.Linear(
        model.fc.in_features,
        2
    )

    model.load_state_dict(
        checkpoint["model_state_dict"]
    )

    model = model.to(DEVICE)
    model.eval()


    transform = transforms.Compose(
        [
            transforms.Resize(
                (
                    checkpoint["image_size"],
                    checkpoint["image_size"]
                )
            ),

            transforms.ToTensor(),

            transforms.Normalize(
                checkpoint["imagenet_mean"],
                checkpoint["imagenet_std"]
            )
        ]
    )


    return (
        model,
        transform,
        checkpoint
    )


# ============================================================
# LOAD PIECE MODEL
# ============================================================

def load_piece_model():

    checkpoint = torch.load(
        PIECE_MODEL_PATH,
        map_location=DEVICE,
        weights_only=False
    )

    class_names = checkpoint[
        "class_names"
    ]


    model = convnext_tiny(
        weights=None
    )

    model.classifier[2] = nn.Linear(
        model.classifier[2].in_features,
        len(class_names)
    )

    model.load_state_dict(
        checkpoint["model_state_dict"]
    )

    model = model.to(DEVICE)
    model.eval()


    transform = transforms.Compose(
        [
            transforms.Resize(
                (
                    checkpoint["image_size"],
                    checkpoint["image_size"]
                )
            ),

            transforms.ToTensor(),

            transforms.Normalize(
                checkpoint["imagenet_mean"],
                checkpoint["imagenet_std"]
            )
        ]
    )


    crop_sizes = checkpoint[
        "piece_crop_sizes"
    ]


    return (
        model,
        transform,
        class_names,
        crop_sizes,
        checkpoint
    )


# ============================================================
# OPENCV -> TORCH
# ============================================================

def crop_to_tensor(
    crop,
    transform
):

    rgb = cv2.cvtColor(
        crop,
        cv2.COLOR_BGR2RGB
    )

    image = Image.fromarray(
        rgb
    )

    return transform(
        image
    )


# ============================================================
# OCCUPANCY PREDICTION
# ============================================================

@torch.no_grad()
def predict_occupancy(
    model,
    transform,
    board
):

    tensors = []


    for row in range(8):

        for col in range(8):

            crop = (
                dc.extract_occupancy_crop(
                    board,
                    row,
                    col
                )
            )

            tensor = crop_to_tensor(
                crop,
                transform
            )

            tensors.append(
                tensor
            )


    batch = torch.stack(
        tensors
    ).to(
        DEVICE
    )


    logits = model(
        batch
    )


    probabilities = torch.softmax(
        logits,
        dim=1
    )


    predictions = torch.argmax(
        probabilities,
        dim=1
    )


    results = []


    for index in range(64):

        predicted = int(
            predictions[index].item()
        )

        confidence = float(
            probabilities[
                index,
                predicted
            ].item()
        )

        results.append(
            {
                "occupied":
                    predicted == 1,

                "confidence":
                    confidence,

                "empty_probability":
                    float(
                        probabilities[
                            index,
                            0
                        ].item()
                    ),

                "occupied_probability":
                    float(
                        probabilities[
                            index,
                            1
                        ].item()
                    )
            }
        )


    return results


# ============================================================
# PIECE PREDICTION
# ============================================================
#
# For one occupied square:
#
# s140 -> ConvNeXt probabilities
# s180 -> ConvNeXt probabilities
# s220 -> ConvNeXt probabilities
#
# average probabilities
#       ↓
# final class
#
# ============================================================

@torch.no_grad()
def predict_piece(
    model,
    transform,
    class_names,
    crop_sizes,
    context,
    board_origin,
    row,
    col
):

    tensors = []


    for crop_size in crop_sizes:

        crop = dc.extract_piece_crop(
            context,
            board_origin,
            row,
            col,
            crop_size
        )

        tensor = crop_to_tensor(
            crop,
            transform
        )

        tensors.append(
            tensor
        )


    batch = torch.stack(
        tensors
    ).to(
        DEVICE
    )


    logits = model(
        batch
    )


    probabilities = torch.softmax(
        logits,
        dim=1
    )


    # Average probability over scales
    mean_probabilities = (
        probabilities.mean(
            dim=0
        )
    )


    predicted_index = int(
        torch.argmax(
            mean_probabilities
        ).item()
    )


    confidence = float(
        mean_probabilities[
            predicted_index
        ].item()
    )


    # Individual scale diagnostics
    scale_predictions = []


    for index, crop_size in enumerate(
        crop_sizes
    ):

        scale_class_index = int(
            torch.argmax(
                probabilities[index]
            ).item()
        )

        scale_confidence = float(
            probabilities[
                index,
                scale_class_index
            ].item()
        )

        scale_predictions.append(
            {
                "scale":
                    crop_size,

                "class_name":
                    class_names[
                        scale_class_index
                    ],

                "confidence":
                    scale_confidence
            }
        )


    return {
        "class_name":
            class_names[
                predicted_index
            ],

        "confidence":
            confidence,

        "scale_predictions":
            scale_predictions
    }


# ============================================================
# EXPECTED CLASS FROM CHESS PIECE
# ============================================================

PIECE_TYPE_NAMES = {
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


def chess_piece_to_class(
    piece
):

    if piece is None:
        return None


    color = (
        "white"
        if piece.color == chess.WHITE
        else "black"
    )


    name = PIECE_TYPE_NAMES[
        piece.piece_type
    ]


    return (
        f"{color}_{name}"
    )


# ============================================================
# CLASS -> CHESS PIECE
# ============================================================

CLASS_TO_PIECE_TYPE = {
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
        chess.KING
}


def class_to_chess_piece(
    class_name
):

    color_name, piece_name = (
        class_name.split(
            "_",
            1
        )
    )


    color = (
        chess.WHITE
        if color_name == "white"
        else chess.BLACK
    )


    piece_type = (
        CLASS_TO_PIECE_TYPE[
            piece_name
        ]
    )


    return chess.Piece(
        piece_type,
        color
    )


# ============================================================
# SHORT DISPLAY NAME
# ============================================================

def short_class_name(
    class_name
):

    if class_name is None:
        return "."


    color, piece = class_name.split(
        "_",
        1
    )


    color_letter = (
        "w"
        if color == "white"
        else "b"
    )


    letters = {
        "pawn":
            "P",

        "knight":
            "N",

        "bishop":
            "B",

        "rook":
            "R",

        "queen":
            "Q",

        "king":
            "K"
    }


    return (
        color_letter
        +
        letters[piece]
    )


# ============================================================
# FULL BOARD PREDICTION
# ============================================================

def predict_full_board(
    occupancy_model,
    occupancy_transform,
    piece_model,
    piece_transform,
    class_names,
    crop_sizes,
    result
):

    board_image = result[
        "board"
    ]

    context = result[
        "context"
    ]

    board_origin = result[
        "board_origin"
    ]


    occupancy_results = predict_occupancy(
        occupancy_model,
        occupancy_transform,
        board_image
    )


    final_results = []


    for row in range(8):

        for col in range(8):

            index = (
                row * 8 + col
            )


            square = (
                dc.get_chess_square(
                    row,
                    col
                )
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


            result_item = {
                "row":
                    row,

                "col":
                    col,

                "square":
                    square,

                "square_name":
                    square_name,

                "occupied":
                    occupancy[
                        "occupied"
                    ],

                "occupancy_confidence":
                    occupancy[
                        "confidence"
                    ],

                "piece":
                    None
            }


            if occupancy[
                "occupied"
            ]:

                piece_result = (
                    predict_piece(
                        piece_model,
                        piece_transform,
                        class_names,
                        crop_sizes,
                        context,
                        board_origin,
                        row,
                        col
                    )
                )

                result_item[
                    "piece"
                ] = piece_result


            final_results.append(
                result_item
            )


    return final_results


# ============================================================
# PRINT BOARD
# ============================================================

def print_predicted_board(
    predictions
):

    print()
    print(
        "PREDICTED BOARD"
    )

    print()


    for row in range(8):

        values = []


        for col in range(8):

            item = predictions[
                row * 8 + col
            ]


            if not item[
                "occupied"
            ]:

                values.append(
                    ". "
                )

            else:

                values.append(
                    short_class_name(
                        item[
                            "piece"
                        ][
                            "class_name"
                        ]
                    )
                )


        print(
            " ".join(values)
        )


# ============================================================
# GROUND TRUTH BOARD
# ============================================================

def print_ground_truth(
    fen_board
):

    print()
    print(
        "GROUND TRUTH"
    )

    print()


    for row in range(8):

        values = []


        for col in range(8):

            square = (
                dc.get_chess_square(
                    row,
                    col
                )
            )


            piece = fen_board.piece_at(
                square
            )


            class_name = (
                chess_piece_to_class(
                    piece
                )
            )


            values.append(
                short_class_name(
                    class_name
                )
            )


        print(
            " ".join(values)
        )


# ============================================================
# BUILD PREDICTED FEN BOARD
# ============================================================

def build_predicted_chess_board(
    predictions
):

    board = chess.Board(
        None
    )


    for item in predictions:

        if not item[
            "occupied"
        ]:

            continue


        piece_result = item[
            "piece"
        ]


        if piece_result is None:
            continue


        piece = class_to_chess_piece(
            piece_result[
                "class_name"
            ]
        )


        board.set_piece_at(
            item["square"],
            piece
        )


    return board


# ============================================================
# EVALUATE
# ============================================================

def evaluate_predictions(
    predictions,
    fen_board
):

    occupancy_correct = 0

    piece_correct = 0

    total_true_pieces = 0

    full_square_correct = 0

    errors = []


    for item in predictions:

        square = item[
            "square"
        ]


        square_name = item[
            "square_name"
        ]


        true_piece = (
            fen_board.piece_at(
                square
            )
        )


        true_occupied = (
            true_piece is not None
        )


        # ====================================================
        # OCCUPANCY
        # ====================================================

        if (
            item["occupied"]
            ==
            true_occupied
        ):

            occupancy_correct += 1


        # ====================================================
        # TRUE EMPTY
        # ====================================================

        if not true_occupied:

            if not item[
                "occupied"
            ]:

                full_square_correct += 1

            else:

                errors.append(
                    {
                        "square":
                            square_name,

                        "expected":
                            "empty",

                        "predicted":
                            item[
                                "piece"
                            ][
                                "class_name"
                            ],

                        "confidence":
                            item[
                                "piece"
                            ][
                                "confidence"
                            ]
                    }
                )


            continue


        # ====================================================
        # TRUE PIECE
        # ====================================================

        total_true_pieces += 1


        expected_class = (
            chess_piece_to_class(
                true_piece
            )
        )


        # Occupancy missed a real piece
        if not item[
            "occupied"
        ]:

            errors.append(
                {
                    "square":
                        square_name,

                    "expected":
                        expected_class,

                    "predicted":
                        "empty",

                    "confidence":
                        item[
                            "occupancy_confidence"
                        ]
                }
            )

            continue


        predicted_class = (
            item[
                "piece"
            ][
                "class_name"
            ]
        )


        confidence = (
            item[
                "piece"
            ][
                "confidence"
            ]
        )


        if (
            predicted_class
            ==
            expected_class
        ):

            piece_correct += 1
            full_square_correct += 1

        else:

            errors.append(
                {
                    "square":
                        square_name,

                    "expected":
                        expected_class,

                    "predicted":
                        predicted_class,

                    "confidence":
                        confidence,

                    "scales":
                        item[
                            "piece"
                        ][
                            "scale_predictions"
                        ]
                }
            )


    # ========================================================
    # RESULTS
    # ========================================================

    occupancy_accuracy = (
        occupancy_correct
        / 64
    )


    piece_accuracy = (
        piece_correct
        / total_true_pieces
        if total_true_pieces > 0
        else 0.0
    )


    full_accuracy = (
        full_square_correct
        / 64
    )


    print()
    print(
        "=========================================="
    )

    print(
        "FULL BOARD TEST RESULT"
    )

    print(
        "=========================================="
    )


    print(
        f"Occupancy : "
        f"{occupancy_correct}/64 "
        f"({occupancy_accuracy * 100:.2f}%)"
    )


    print(
        f"Pieces    : "
        f"{piece_correct}/"
        f"{total_true_pieces} "
        f"({piece_accuracy * 100:.2f}%)"
    )


    print(
        f"Full board: "
        f"{full_square_correct}/64 "
        f"({full_accuracy * 100:.2f}%)"
    )


    print(
        f"Errors    : "
        f"{len(errors)}"
    )


    # ========================================================
    # PREDICTED FEN
    # ========================================================

    predicted_board = (
        build_predicted_chess_board(
            predictions
        )
    )


    print()
    print(
        "Predicted board FEN:"
    )

    print(
        predicted_board.board_fen()
    )


    print()
    print(
        "Ground truth FEN:"
    )

    print(
        fen_board.board_fen()
    )


    # ========================================================
    # ERRORS
    # ========================================================

    if errors:

        print()
        print(
            "WRONG SQUARES"
        )

        print()


        for error in errors:

            print(
                f"{error['square']}: "
                f"{error['expected']} "
                f"-> "
                f"{error['predicted']} "
                f"(conf "
                f"{error['confidence']:.3f})"
            )


            if "scales" in error:

                for scale_result in (
                    error["scales"]
                ):

                    print(
                        "    "
                        f"s{scale_result['scale']}: "
                        f"{scale_result['class_name']} "
                        f"{scale_result['confidence']:.3f}"
                    )


    else:

        print()
        print(
            "PERFECT FULL BOARD: 64/64"
        )


    print()
    print(
        "=========================================="
    )


# ============================================================
# INPUT SOURCE HELPERS
# ============================================================

def choose_input_mode():

    print()
    print("==========================================")
    print("SELECT TEST INPUT")
    print("==========================================")
    print("1 = IMOU live camera")
    print("2 = Existing image")
    print()

    while True:

        choice = input(
            "Mode [1/2] > "
        ).strip().lower()

        if choice in (
            "1",
            "camera",
            "cam"
        ):
            return "camera"

        if choice in (
            "2",
            "image",
            "img"
        ):
            return "image"

        print(
            "Please enter 1 or 2."
        )


def choose_image_path():

    # ========================================================
    # WINDOWS FILE PICKER
    # ========================================================

    try:

        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()

        root.withdraw()

        root.attributes(
            "-topmost",
            True
        )

        filename = (
            filedialog.askopenfilename(
                title="Select chessboard image",
                filetypes=[
                    (
                        "Image files",
                        "*.png *.jpg *.jpeg *.bmp *.webp"
                    ),
                    (
                        "All files",
                        "*.*"
                    )
                ]
            )
        )

        root.destroy()

        if filename:

            return Path(
                filename
            )

    except Exception as error:

        print()
        print(
            "File picker unavailable:"
        )

        print(
            error
        )

        print()


    # ========================================================
    # FALLBACK: MANUAL PATH
    # ========================================================

    while True:

        value = input(
            "Image path > "
        ).strip().strip('"')

        if not value:

            return None

        path = Path(
            value
        )

        if path.exists():

            return path

        print(
            "File does not exist."
        )


def load_existing_test_image():

    path = choose_image_path()

    if path is None:

        raise RuntimeError(
            "No image selected."
        )

    frame = cv2.imread(
        str(path),
        cv2.IMREAD_COLOR
    )

    if frame is None:

        raise RuntimeError(
            f"Cannot read image:\n{path}"
        )

    original_height, original_width = (
        frame.shape[:2]
    )

    # ========================================================
    # MATCH DATASET WORKING FRAME
    # ========================================================

    target_width = int(
        getattr(
            dc,
            "WORKING_WIDTH",
            1280
        )
    )

    target_height = int(
        getattr(
            dc,
            "WORKING_HEIGHT",
            720
        )
    )

    if (
        original_width != target_width
        or
        original_height != target_height
    ):

        frame = cv2.resize(
            frame,
            (
                target_width,
                target_height
            ),
            interpolation=cv2.INTER_AREA
        )

    print()
    print(
        "Image loaded:"
    )

    print(
        path
    )

    print(
        f"Original size : "
        f"{original_width}x"
        f"{original_height}"
    )

    print(
        f"Working size  : "
        f"{frame.shape[1]}x"
        f"{frame.shape[0]}"
    )

    print()

    return (
        frame,
        path
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print(
        "Loading models..."
    )


    (
        occupancy_model,
        occupancy_transform,
        occupancy_checkpoint
    ) = load_occupancy_model()


    (
        piece_model,
        piece_transform,
        class_names,
        crop_sizes,
        piece_checkpoint
    ) = load_piece_model()


    print()
    print(
        f"Device : {DEVICE}"
    )


    if torch.cuda.is_available():

        print(
            "GPU    : "
            f"{torch.cuda.get_device_name(0)}"
        )


    print(
        "Occupancy: ResNet-18"
    )

    print(
        "Pieces   : ConvNeXt-Tiny"
    )

    print(
        f"Scales   : {crop_sizes}"
    )

    print()


    # ========================================================
    # CHOOSE INPUT
    # ========================================================

    input_mode = (
        choose_input_mode()
    )


    dc.frozen_frame = None

    dc.clicked_points = []


    cap = None

    static_image = None

    image_path = None


    # ========================================================
    # MODE 1: IMOU LIVE CAMERA
    # ========================================================

    if input_mode == "camera":

        cap = dc.open_imou_camera()


    # ========================================================
    # MODE 2: EXISTING IMAGE
    # ========================================================

    else:

        (
            static_image,
            image_path
        ) = load_existing_test_image()


        # Existing image is immediately treated as a frozen
        # frame so mouse_callback works exactly like it does
        # after pressing SPACE in camera mode.

        dc.frozen_frame = (
            static_image.copy()
        )

        dc.clicked_points = []


    # ========================================================
    # WINDOW
    # ========================================================

    cv2.namedWindow(
        "Camera"
    )


    cv2.setMouseCallback(
        "Camera",
        dc.mouse_callback
    )


    # ========================================================
    # HELP
    # ========================================================

    print(
        "=========================================="
    )

    print(
        "UNSEEN FULL-BOARD TEST"
    )

    print(
        "=========================================="
    )

    print()


    if input_mode == "camera":

        print(
            "MODE: IMOU LIVE CAMERA"
        )

        print(
            "SPACE = freeze / unfreeze"
        )

    else:

        print(
            "MODE: EXISTING IMAGE"
        )

        print(
            f"Image: {image_path}"
        )

        print(
            "Image is already frozen."
        )


    print()

    print(
        "4 OUTER: TL -> TR -> BR -> BL"
    )

    print(
        "4 BOARD: TL -> TR -> BR -> BL"
    )

    print()

    print(
        "ENTER = preview"
    )

    print(
        "U = undo"
    )

    print(
        "R = reset"
    )

    print(
        "Q = quit"
    )

    print()


    if input_mode == "image":

        print(
            "Click 4 OUTER then 4 BOARD."
        )

        print()


    # ========================================================
    # LOOP
    # ========================================================

    while True:


        # ====================================================
        # CAMERA MODE - LIVE
        # ====================================================

        if (
            input_mode == "camera"
            and
            dc.frozen_frame is None
        ):

            ret, frame = (
                dc.read_imou_frame(
                    cap
                )
            )


            if (
                not ret
                or
                frame is None
            ):

                print()
                print(
                    "RTSP / HEVC frame lost."
                )

                print(
                    "Reconnecting IMOU..."
                )


                cap.release()

                cv2.waitKey(
                    500
                )


                try:

                    cap = (
                        dc.open_imou_camera()
                    )

                    print(
                        "IMOU reconnected."
                    )

                    print()

                    continue


                except Exception as error:

                    print(
                        "Cannot reconnect IMOU:"
                    )

                    print(
                        error
                    )

                    print()

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
        # FROZEN FRAME
        # ====================================================

        else:

            # Image mode should always remain frozen.
            if (
                dc.frozen_frame is None
                and
                static_image is not None
            ):

                dc.frozen_frame = (
                    static_image.copy()
                )


            display = (
                dc.draw_selected_points(
                    dc.frozen_frame
                )
            )


            mode_text = (
                "IMAGE - SELECT 8 POINTS"
                if input_mode == "image"
                else "FROZEN"
            )


            cv2.putText(
                display,
                mode_text,
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


            # ------------------------------------------------
            # CAMERA MODE
            # ------------------------------------------------

            if input_mode == "camera":

                if dc.frozen_frame is None:

                    dc.frozen_frame = (
                        frame.copy()
                    )

                    dc.clicked_points = []


                    print()

                    print(
                        "Frame frozen."
                    )

                    print(
                        "Click 4 OUTER then 4 BOARD."
                    )


                else:

                    dc.frozen_frame = None

                    dc.clicked_points = []


            # ------------------------------------------------
            # IMAGE MODE
            # ------------------------------------------------

            else:

                print(
                    "Image mode is already frozen. "
                    "Click 4 OUTER then 4 BOARD."
                )


        # ====================================================
        # UNDO
        # ====================================================

        elif key in (
            ord("u"),
            ord("U")
        ):

            if dc.clicked_points:

                removed = (
                    dc.clicked_points.pop()
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

            dc.clicked_points = []

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


            if dc.frozen_frame is None:

                print(
                    "Press SPACE first."
                )

                continue


            if len(
                dc.clicked_points
            ) != 8:

                print(
                    "Need exactly 8 points."
                )

                continue


            if not (
                dc.validate_outer_contains_board()
            ):

                print(
                    "BOARD must be inside OUTER."
                )

                continue


            # =================================================
            # HOMOGRAPHY / NORMALIZED CONTEXT
            # =================================================

            try:

                result = (
                    dc.create_normalized_context(
                        dc.frozen_frame
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
                dc.confirm_result(
                    result
                )
            )


            # =================================================
            # DISCARD / RESELECT
            # =================================================

            if not accepted:

                dc.clicked_points = []


                if input_mode == "camera":

                    dc.frozen_frame = None

                    print(
                        "Returning to LIVE..."
                    )


                else:

                    dc.frozen_frame = (
                        static_image.copy()
                    )

                    print(
                        "Preview discarded."
                    )

                    print(
                        "Click the 8 points again."
                    )


                continue


            # =================================================
            # FEN
            # =================================================

            print()

            print(
                "Paste FEN of the unseen position:"
            )


            fen_board, fen_text = (
                dc.read_fen()
            )


            # =================================================
            # FEN CANCEL
            # =================================================

            if fen_board is None:

                dc.clicked_points = []


                if input_mode == "camera":

                    dc.frozen_frame = None


                else:

                    dc.frozen_frame = (
                        static_image.copy()
                    )


                continue


            # =================================================
            # INFERENCE
            # =================================================

            print()

            print(
                "Running ResNet + ConvNeXt..."
            )


            predictions = (
                predict_full_board(
                    occupancy_model,
                    occupancy_transform,
                    piece_model,
                    piece_transform,
                    class_names,
                    crop_sizes,
                    result
                )
            )


            # =================================================
            # OUTPUT
            # =================================================

            print_predicted_board(
                predictions
            )


            print_ground_truth(
                fen_board
            )


            evaluate_predictions(
                predictions,
                fen_board
            )


            break


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

    if cap is not None:

        cap.release()


    cv2.destroyAllWindows()


# ============================================================
# ENTRY
# ============================================================

if __name__ == "__main__":

    main()

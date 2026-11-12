import cv2
import chess

from pathlib import Path

import torch
from torch import nn

from PIL import Image

from torchvision import transforms
from torchvision.models import resnet18

import dataset_capture as dc


# ============================================================
# CONFIG
# ============================================================

PROJECT_ROOT = (
    Path(__file__)
    .resolve()
    .parent
    .parent
)

MODEL_PATH = (
    PROJECT_ROOT
    / "models"
    / "occupancy"
    / "resnet18_occupancy_best.pt"
)

DEVICE = torch.device(
    "cuda"
    if torch.cuda.is_available()
    else "cpu"
)


# ============================================================
# LOAD MODEL
# ============================================================

def load_model():

    checkpoint = torch.load(
        MODEL_PATH,
        map_location=DEVICE,
        weights_only=False
    )

    model = resnet18(
        weights=None
    )

    in_features = (
        model.fc.in_features
    )

    model.fc = nn.Linear(
        in_features,
        2
    )

    model.load_state_dict(
        checkpoint[
            "model_state_dict"
        ]
    )

    model = model.to(
        DEVICE
    )

    model.eval()

    mean = checkpoint[
        "imagenet_mean"
    ]

    std = checkpoint[
        "imagenet_std"
    ]

    image_size = checkpoint[
        "image_size"
    ]

    transform = transforms.Compose(
        [
            transforms.Resize(
                (
                    image_size,
                    image_size
                )
            ),

            transforms.ToTensor(),

            transforms.Normalize(
                mean,
                std
            )
        ]
    )

    return (
        model,
        transform,
        checkpoint
    )


# ============================================================
# CONVERT ONE OPENCV CROP
# ============================================================

def crop_to_tensor(
    crop,
    transform
):

    rgb = cv2.cvtColor(
        crop,
        cv2.COLOR_BGR2RGB
    )

    pil_image = Image.fromarray(
        rgb
    )

    tensor = transform(
        pil_image
    )

    return tensor


# ============================================================
# RUN OCCUPANCY ON ALL 64 SQUARES
# ============================================================

@torch.no_grad()
def predict_board(
    model,
    transform,
    normalized_board
):

    tensors = []

    square_info = []


    for row in range(8):

        for col in range(8):

            crop = (
                dc.extract_occupancy_crop(
                    normalized_board,
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

            square = dc.get_chess_square(
                row,
                col
            )

            square_name = (
                chess.square_name(
                    square
                )
            )

            square_info.append(
                {
                    "row": row,
                    "col": col,
                    "square": square,
                    "name": square_name
                }
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


    for i, info in enumerate(
        square_info
    ):

        predicted_class = int(
            predictions[i].item()
        )

        confidence = float(
            probabilities[
                i,
                predicted_class
            ].item()
        )

        results.append(
            {
                **info,

                "predicted":
                    predicted_class,

                "confidence":
                    confidence
            }
        )


    return results


# ============================================================
# COMPARE WITH FEN
# ============================================================

def evaluate_position(
    predictions,
    fen_board
):

    correct = 0

    mismatches = []


    print()
    print(
        "PREDICTED OCCUPANCY"
    )

    print()


    for row in range(8):

        row_text = []

        for col in range(8):

            index = (
                row * 8 + col
            )

            prediction = (
                predictions[index]
            )

            if (
                prediction[
                    "predicted"
                ]
                == 1
            ):

                row_text.append(
                    "X"
                )

            else:

                row_text.append(
                    "."
                )

        print(
            " ".join(
                row_text
            )
        )


    print()
    print(
        "GROUND TRUTH"
    )

    print()


    for row in range(8):

        row_text = []

        for col in range(8):

            square = (
                dc.get_chess_square(
                    row,
                    col
                )
            )

            occupied = (
                fen_board.piece_at(
                    square
                )
                is not None
            )

            row_text.append(
                "X"
                if occupied
                else "."
            )

        print(
            " ".join(
                row_text
            )
        )


    # ========================================================
    # PER SQUARE COMPARISON
    # ========================================================

    for prediction in predictions:

        square = prediction[
            "square"
        ]

        actual_occupied = (
            fen_board.piece_at(
                square
            )
            is not None
        )

        expected_class = (
            1
            if actual_occupied
            else 0
        )

        if (
            prediction[
                "predicted"
            ]
            ==
            expected_class
        ):

            correct += 1

        else:

            mismatches.append(
                {
                    "square":
                        prediction[
                            "name"
                        ],

                    "expected":
                        (
                            "occupied"
                            if actual_occupied
                            else "empty"
                        ),

                    "predicted":
                        (
                            "occupied"
                            if prediction[
                                "predicted"
                            ] == 1
                            else "empty"
                        ),

                    "confidence":
                        prediction[
                            "confidence"
                        ]
                }
            )


    accuracy = (
        correct / 64
    )


    print()
    print(
        "======================================"
    )

    print(
        "OCCUPANCY TEST RESULT"
    )

    print(
        "======================================"
    )

    print(
        f"Correct  : {correct}/64"
    )

    print(
        f"Accuracy : "
        f"{accuracy * 100:.2f}%"
    )

    print(
        f"Errors   : "
        f"{len(mismatches)}"
    )


    if mismatches:

        print()
        print(
            "Wrong squares:"
        )

        for error in mismatches:

            print(
                f"  {error['square']}: "
                f"expected "
                f"{error['expected']}, "
                f"predicted "
                f"{error['predicted']} "
                f"(confidence "
                f"{error['confidence']:.3f})"
            )


    else:

        print()
        print(
            "PERFECT: 64/64"
        )


    print(
        "======================================"
    )

    return accuracy


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print(
        "Loading occupancy model..."
    )

    model, transform, checkpoint = (
        load_model()
    )

    print(
        f"Device : {DEVICE}"
    )

    if torch.cuda.is_available():

        print(
            "GPU    : "
            f"{torch.cuda.get_device_name(0)}"
        )

    print(
        "Model  : ResNet-18 occupancy"
    )

    print()


    # ========================================================
    # CAMERA
    # ========================================================

    cap = cv2.VideoCapture(
        dc.CAMERA_INDEX,
        cv2.CAP_DSHOW
    )

    if not cap.isOpened():

        cap = cv2.VideoCapture(
            dc.CAMERA_INDEX
        )

    if not cap.isOpened():

        raise RuntimeError(
            "Cannot open camera."
        )


    cap.set(
        cv2.CAP_PROP_FRAME_WIDTH,
        dc.CAMERA_WIDTH
    )

    cap.set(
        cv2.CAP_PROP_FRAME_HEIGHT,
        dc.CAMERA_HEIGHT
    )


    cv2.namedWindow(
        "Camera"
    )

    cv2.setMouseCallback(
        "Camera",
        dc.mouse_callback
    )


    print(
        "======================================"
    )

    print(
        "TEST POSITION - NOT SAVED TO DATASET"
    )

    print(
        "======================================"
    )

    print()

    print(
        "SPACE = freeze"
    )

    print(
        "4 OUTER clicks:"
    )

    print(
        "TL -> TR -> BR -> BL"
    )

    print()

    print(
        "4 BOARD clicks:"
    )

    print(
        "TL -> TR -> BR -> BL"
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


    # ========================================================
    # LOOP
    # ========================================================

    while True:


        # ====================================================
        # LIVE
        # ====================================================

        if dc.frozen_frame is None:

            ret, frame = cap.read()

            if not ret:

                break


            display = (
                frame.copy()
            )


            cv2.putText(
                display,
                "LIVE - SPACE to freeze",
                (20, 40),
                cv2.FONT_HERSHEY_SIMPLEX,
                1,
                (0, 255, 0),
                2
            )


        # ====================================================
        # FROZEN
        # ====================================================

        else:

            display = (
                dc.draw_selected_points(
                    dc.frozen_frame
                )
            )


            cv2.putText(
                display,
                "FROZEN",
                (20, 40),
                cv2.FONT_HERSHEY_SIMPLEX,
                1,
                (0, 0, 255),
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
                    "Click 4 OUTER, "
                    "then 4 BOARD."
                )

            else:

                dc.frozen_frame = None
                dc.clicked_points = []


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
                "Points reset."
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
                    f"Need 8 points. "
                    f"Current: "
                    f"{len(dc.clicked_points)}"
                )

                continue


            if not (
                dc.validate_outer_contains_board()
            ):

                print(
                    "BOARD must be inside OUTER."
                )

                continue


            try:

                result = (
                    dc.create_normalized_context(
                        dc.frozen_frame
                    )
                )

            except Exception as error:

                print(
                    error
                )

                continue


            accepted = (
                dc.confirm_result(
                    result
                )
            )


            if not accepted:

                dc.frozen_frame = None
                dc.clicked_points = []

                print(
                    "Discarded."
                )

                continue


            # =================================================
            # FEN
            # =================================================

            print()
            print(
                "Paste FEN of THIS test position."
            )

            print(
                "This image will NOT be saved "
                "to training data."
            )

            print()


            fen_board, fen_text = (
                dc.read_fen()
            )


            if fen_board is None:

                dc.frozen_frame = None
                dc.clicked_points = []

                continue


            # =================================================
            # PREDICT
            # =================================================

            predictions = predict_board(
                model,
                transform,
                result["board"]
            )


            evaluate_position(
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


    cap.release()

    cv2.destroyAllWindows()


if __name__ == "__main__":

    main()
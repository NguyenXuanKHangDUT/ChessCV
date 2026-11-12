from __future__ import annotations

import cv2
import numpy as np
import torch

from PIL import Image

from backend.app.vision.geometry import (
    extract_occupancy_crop,
    extract_piece_crop,
)

from backend.app.vision.model_manager import (
    ModelManager,
)


# ============================================================
# IMAGE -> TENSOR
# ============================================================

def cv2_to_tensor(
    image: np.ndarray,
    transform,
):

    rgb = cv2.cvtColor(
        image,
        cv2.COLOR_BGR2RGB,
    )

    pil_image = Image.fromarray(
        rgb
    )

    return transform(
        pil_image
    )


# ============================================================
# OCCUPANCY
# ============================================================

@torch.inference_mode()
def predict_occupancy(
    manager: ModelManager,
    board: np.ndarray,
):

    tensors = []


    for row in range(8):

        for col in range(8):

            crop = extract_occupancy_crop(
                board,
                row,
                col,
            )

            tensor = cv2_to_tensor(
                crop,
                manager.occupancy_transform,
            )

            tensors.append(
                tensor
            )


    batch = torch.stack(
        tensors
    ).to(
        manager.device
    )


    logits = manager.occupancy_model(
        batch
    )


    probabilities = torch.softmax(
        logits,
        dim=1,
    )


    predictions = torch.argmax(
        probabilities,
        dim=1,
    )


    try:

        empty_index = (
            manager
            .occupancy_classes
            .index("empty")
        )

        occupied_index = (
            manager
            .occupancy_classes
            .index("occupied")
        )

    except ValueError as error:

        raise RuntimeError(
            "Occupancy checkpoint must contain "
            "'empty' and 'occupied' classes."
        ) from error


    results = []


    for index in range(64):

        predicted_index = int(
            predictions[index].item()
        )

        occupied = (
            predicted_index
            ==
            occupied_index
        )


        confidence = float(
            probabilities[
                index,
                predicted_index,
            ].item()
        )


        results.append(
            {
                "occupied":
                    occupied,

                "confidence":
                    confidence,

                "empty_probability":
                    float(
                        probabilities[
                            index,
                            empty_index,
                        ].item()
                    ),

                "occupied_probability":
                    float(
                        probabilities[
                            index,
                            occupied_index,
                        ].item()
                    ),
            }
        )


    return results


# ============================================================
# PIECES
# ============================================================

@torch.inference_mode()
def predict_pieces(
    manager: ModelManager,
    context: np.ndarray,
    board_origin: tuple[int, int],
    occupancy_results: list[dict],
):

    # ========================================================
    # One big batch:
    #
    # occupied_square_1:
    #   s140
    #   s180
    #   s220
    #
    # occupied_square_2:
    #   s140
    #   s180
    #   s220
    #
    # ...
    #
    # Much faster than ConvNeXt call per square.
    # ========================================================

    tensors = []

    metadata = []


    for row in range(8):

        for col in range(8):

            square_index = (
                row * 8
                +
                col
            )


            if not occupancy_results[
                square_index
            ]["occupied"]:

                continue


            for crop_size in (
                manager.piece_crop_sizes
            ):

                crop = extract_piece_crop(
                    context,
                    board_origin,
                    row,
                    col,
                    crop_size,
                )


                tensor = cv2_to_tensor(
                    crop,
                    manager.piece_transform,
                )


                tensors.append(
                    tensor
                )


                metadata.append(
                    {
                        "square_index":
                            square_index,

                        "row":
                            row,

                        "col":
                            col,

                        "crop_size":
                            crop_size,
                    }
                )


    if not tensors:

        return {}


    batch = torch.stack(
        tensors
    ).to(
        manager.device
    )


    logits = manager.piece_model(
        batch
    )


    probabilities = torch.softmax(
        logits,
        dim=1,
    ).cpu()


    # ========================================================
    # GROUP BY BOARD SQUARE
    # ========================================================

    grouped = {}


    for index, meta in enumerate(
        metadata
    ):

        square_index = meta[
            "square_index"
        ]


        if square_index not in grouped:

            grouped[
                square_index
            ] = []


        grouped[
            square_index
        ].append(
            {
                "crop_size":
                    meta[
                        "crop_size"
                    ],

                "probabilities":
                    probabilities[
                        index
                    ],
            }
        )


    # ========================================================
    # AVERAGE 3 SCALES
    # ========================================================

    results = {}


    for (
        square_index,
        scale_results,
    ) in grouped.items():


        probability_stack = torch.stack(
            [
                item[
                    "probabilities"
                ]

                for item in scale_results
            ]
        )


        mean_probabilities = (
            probability_stack.mean(
                dim=0
            )
        )


        class_index = int(
            torch.argmax(
                mean_probabilities
            ).item()
        )


        class_name = (
            manager
            .piece_classes[
                class_index
            ]
        )


        confidence = float(
            mean_probabilities[
                class_index
            ].item()
        )


        scale_predictions = []


        for item in scale_results:

            probs = item[
                "probabilities"
            ]


            scale_class_index = int(
                torch.argmax(
                    probs
                ).item()
            )


            scale_predictions.append(
                {
                    "crop_size":
                        item[
                            "crop_size"
                        ],

                    "piece":
                        manager.piece_classes[
                            scale_class_index
                        ],

                    "confidence":
                        float(
                            probs[
                                scale_class_index
                            ].item()
                        ),
                }
            )


        results[
            square_index
        ] = {
            "piece":
                class_name,

            "confidence":
                confidence,

            "scale_predictions":
                scale_predictions,
        }


    return results
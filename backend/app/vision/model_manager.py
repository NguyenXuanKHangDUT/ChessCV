from __future__ import annotations

from dataclasses import dataclass

import torch
from torch import nn

from torchvision import transforms
from torchvision.models import (
    resnet18,
    convnext_tiny,
)

from backend.app.core.config import settings


# ============================================================
# MODEL BUNDLE
# ============================================================

@dataclass
class VisionModels:

    device: torch.device

    occupancy_model: nn.Module
    occupancy_transform: transforms.Compose
    occupancy_classes: list[str]

    piece_model: nn.Module
    piece_transform: transforms.Compose
    piece_classes: list[str]

    piece_crop_sizes: list[int]


# ============================================================
# MANAGER
# ============================================================

class ModelManager:

    def __init__(self):

        self.device = torch.device(
            "cuda"
            if torch.cuda.is_available()
            else "cpu"
        )

        print()
        print("==========================================")
        print("LOADING VISION MODELS")
        print("==========================================")
        print(f"Device: {self.device}")

        if torch.cuda.is_available():

            print(
                "GPU   : "
                f"{torch.cuda.get_device_name(0)}"
            )

        (
            self.occupancy_model,
            self.occupancy_transform,
            self.occupancy_classes,
        ) = self._load_occupancy_model()

        (
            self.piece_model,
            self.piece_transform,
            self.piece_classes,
            self.piece_crop_sizes,
        ) = self._load_piece_model()

        print()
        print("Vision models loaded successfully.")
        print("==========================================")
        print()


    # ========================================================
    # OCCUPANCY
    # ========================================================

    def _load_occupancy_model(self):

        checkpoint = torch.load(
            settings.OCCUPANCY_MODEL_PATH,
            map_location=self.device,
            weights_only=False,
        )

        class_names = checkpoint.get(
            "class_names",
            [
                "empty",
                "occupied",
            ]
        )

        model = resnet18(
            weights=None
        )

        model.fc = nn.Linear(
            model.fc.in_features,
            len(class_names),
        )

        model.load_state_dict(
            checkpoint[
                "model_state_dict"
            ]
        )

        model = model.to(
            self.device
        )

        model.eval()


        image_size = checkpoint.get(
            "image_size",
            224
        )

        mean = checkpoint.get(
            "imagenet_mean",
            [
                0.485,
                0.456,
                0.406,
            ]
        )

        std = checkpoint.get(
            "imagenet_std",
            [
                0.229,
                0.224,
                0.225,
            ]
        )


        transform = transforms.Compose(
            [
                transforms.Resize(
                    (
                        image_size,
                        image_size,
                    )
                ),

                transforms.ToTensor(),

                transforms.Normalize(
                    mean,
                    std,
                ),
            ]
        )


        print(
            "Occupancy model:",
            settings.OCCUPANCY_MODEL_PATH
        )

        print(
            "Occupancy classes:",
            class_names
        )


        return (
            model,
            transform,
            class_names,
        )


    # ========================================================
    # PIECES
    # ========================================================

    def _load_piece_model(self):

        checkpoint = torch.load(
            settings.PIECE_MODEL_PATH,
            map_location=self.device,
            weights_only=False,
        )

        class_names = checkpoint[
            "class_names"
        ]

        model = convnext_tiny(
            weights=None
        )

        model.classifier[2] = nn.Linear(
            model.classifier[2].in_features,
            len(class_names),
        )

        model.load_state_dict(
            checkpoint[
                "model_state_dict"
            ]
        )

        model = model.to(
            self.device
        )

        model.eval()


        image_size = checkpoint.get(
            "image_size",
            224
        )

        mean = checkpoint.get(
            "imagenet_mean",
            [
                0.485,
                0.456,
                0.406,
            ]
        )

        std = checkpoint.get(
            "imagenet_std",
            [
                0.229,
                0.224,
                0.225,
            ]
        )

        crop_sizes = checkpoint.get(
            "piece_crop_sizes",
            [
                140,
                180,
                220,
            ]
        )


        transform = transforms.Compose(
            [
                transforms.Resize(
                    (
                        image_size,
                        image_size,
                    )
                ),

                transforms.ToTensor(),

                transforms.Normalize(
                    mean,
                    std,
                ),
            ]
        )


        print(
            "Piece model:",
            settings.PIECE_MODEL_PATH
        )

        print(
            "Piece classes:",
            class_names
        )

        print(
            "Piece crop sizes:",
            crop_sizes
        )


        return (
            model,
            transform,
            class_names,
            crop_sizes,
        )


# ============================================================
# SINGLETON
# ============================================================

_model_manager: ModelManager | None = None


def get_model_manager() -> ModelManager:

    global _model_manager

    if _model_manager is None:

        _model_manager = ModelManager()

    return _model_manager
import json
import random
import re
from collections import Counter
from pathlib import Path

from PIL import Image

import torch
from torch import nn
from torch.utils.data import Dataset, DataLoader

from torchvision import transforms
from torchvision.models import (
    resnet18,
    ResNet18_Weights,
)


# ============================================================
# CONFIG
# ============================================================

SEED = 42

IMAGE_SIZE = 224
BATCH_SIZE = 16

# Transfer learning:
#
# Phase 1:
#   freeze ResNet backbone
#   train classification head only
#
# Phase 2:
#   unfreeze entire model
#   fine-tune everything
#
HEAD_EPOCHS = 3
FULL_EPOCHS = 12

HEAD_LR = 1e-3
FULL_LR = 1e-4

WEIGHT_DECAY = 1e-4

VAL_RATIO = 0.20


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
    PROJECT_ROOT
    / "data"
    / "occupancy"
)

EMPTY_DIR = (
    DATA_ROOT
    / "empty"
)

OCCUPIED_DIR = (
    DATA_ROOT
    / "occupied"
)

MODEL_DIR = (
    PROJECT_ROOT
    / "models"
    / "occupancy"
)

MODEL_DIR.mkdir(
    parents=True,
    exist_ok=True
)

BEST_MODEL_PATH = (
    MODEL_DIR
    / "resnet18_occupancy_best.pt"
)

METRICS_PATH = (
    MODEL_DIR
    / "training_info.json"
)


# ============================================================
# CLASSES
# ============================================================

CLASS_NAMES = [
    "empty",
    "occupied"
]

CLASS_TO_IDX = {
    "empty": 0,
    "occupied": 1
}


# ============================================================
# DEVICE
# ============================================================

DEVICE = torch.device(
    "cuda"
    if torch.cuda.is_available()
    else "cpu"
)


# ============================================================
# REPRODUCIBILITY
# ============================================================

def set_seed():

    random.seed(SEED)

    torch.manual_seed(SEED)

    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(SEED)


# ============================================================
# BOARD ID FROM FILE NAME
# ============================================================
#
# Example:
#
# 20260910_232320_899_e4.png
#
# Board/sample ID:
#
# 20260910_232320_899
#
# Square:
#
# e4
#
# This is CRITICAL:
#
# train/val split is done by BOARD,
# not by individual square crops.
#
# ============================================================

def get_board_id(path):

    match = re.match(
        r"(.+)_([a-h][1-8])\.png$",
        path.name
    )

    if match is None:

        raise ValueError(
            f"Unexpected filename: {path.name}"
        )

    return match.group(1)


# ============================================================
# COLLECT DATA
# ============================================================

def collect_records():

    records = []

    for class_name in CLASS_NAMES:

        class_dir = (
            DATA_ROOT
            / class_name
        )

        if not class_dir.exists():

            raise FileNotFoundError(
                f"Missing folder: {class_dir}"
            )

        label = CLASS_TO_IDX[
            class_name
        ]

        for path in sorted(
            class_dir.glob("*.png")
        ):

            board_id = get_board_id(
                path
            )

            records.append(
                {
                    "path": path,
                    "label": label,
                    "class_name": class_name,
                    "board_id": board_id
                }
            )

    if len(records) == 0:

        raise RuntimeError(
            "No occupancy images found."
        )

    return records


# ============================================================
# SPLIT BY BOARD
# ============================================================

def split_by_board(records):

    board_ids = sorted(
        set(
            record["board_id"]
            for record in records
        )
    )

    if len(board_ids) < 3:

        raise RuntimeError(
            "Need at least 3 board positions "
            "before training."
        )

    rng = random.Random(
        SEED
    )

    rng.shuffle(
        board_ids
    )

    val_count = max(
        1,
        round(
            len(board_ids)
            * VAL_RATIO
        )
    )

    # Never allow validation to consume all boards
    val_count = min(
        val_count,
        len(board_ids) - 1
    )

    val_board_ids = set(
        board_ids[:val_count]
    )

    train_board_ids = set(
        board_ids[val_count:]
    )


    train_records = [
        record
        for record in records
        if record["board_id"]
        in train_board_ids
    ]

    val_records = [
        record
        for record in records
        if record["board_id"]
        in val_board_ids
    ]


    return (
        train_records,
        val_records,
        sorted(train_board_ids),
        sorted(val_board_ids)
    )


# ============================================================
# TRANSFORMS
# ============================================================
#
# We use ImageNet normalization because ResNet-18
# starts from ImageNet pretrained weights.
#
# Augmentation is deliberately mild.
#
# We do NOT vertically flip pieces because that would create
# unrealistic camera views.
#
# ============================================================

IMAGENET_MEAN = [
    0.485,
    0.456,
    0.406
]

IMAGENET_STD = [
    0.229,
    0.224,
    0.225
]


TRAIN_TRANSFORM = transforms.Compose(
    [
        transforms.Resize(
            (
                IMAGE_SIZE,
                IMAGE_SIZE
            )
        ),

        transforms.ColorJitter(
            brightness=0.20,
            contrast=0.20,
            saturation=0.10,
            hue=0.02
        ),

        transforms.RandomAffine(
            degrees=3,
            translate=(
                0.03,
                0.03
            ),
            scale=(
                0.95,
                1.05
            )
        ),

        transforms.ToTensor(),

        transforms.Normalize(
            IMAGENET_MEAN,
            IMAGENET_STD
        ),
    ]
)


VAL_TRANSFORM = transforms.Compose(
    [
        transforms.Resize(
            (
                IMAGE_SIZE,
                IMAGE_SIZE
            )
        ),

        transforms.ToTensor(),

        transforms.Normalize(
            IMAGENET_MEAN,
            IMAGENET_STD
        ),
    ]
)


# ============================================================
# DATASET
# ============================================================

class OccupancyDataset(Dataset):

    def __init__(
        self,
        records,
        transform
    ):

        self.records = records
        self.transform = transform


    def __len__(self):

        return len(
            self.records
        )


    def __getitem__(
        self,
        index
    ):

        record = (
            self.records[index]
        )

        image = Image.open(
            record["path"]
        ).convert(
            "RGB"
        )

        image = self.transform(
            image
        )

        label = record[
            "label"
        ]

        return (
            image,
            label
        )


# ============================================================
# CLASS WEIGHTS
# ============================================================

def build_class_weights(
    train_records
):

    counts = Counter(
        record["label"]
        for record in train_records
    )

    total = len(
        train_records
    )

    weights = []

    for class_index in range(
        len(CLASS_NAMES)
    ):

        count = counts[
            class_index
        ]

        if count == 0:

            raise RuntimeError(
                f"No training samples for "
                f"class {CLASS_NAMES[class_index]}"
            )

        weight = (
            total
            /
            (
                len(CLASS_NAMES)
                * count
            )
        )

        weights.append(
            weight
        )


    return torch.tensor(
        weights,
        dtype=torch.float32,
        device=DEVICE
    )


# ============================================================
# TRAIN ONE EPOCH
# ============================================================

def train_one_epoch(
    model,
    loader,
    criterion,
    optimizer
):

    model.train()

    total_loss = 0.0

    correct = 0
    total = 0


    for images, labels in loader:

        images = images.to(
            DEVICE
        )

        labels = labels.to(
            DEVICE
        )


        optimizer.zero_grad()


        logits = model(
            images
        )


        loss = criterion(
            logits,
            labels
        )


        loss.backward()

        optimizer.step()


        total_loss += (
            loss.item()
            * images.size(0)
        )


        predictions = (
            logits.argmax(
                dim=1
            )
        )


        correct += (
            predictions
            ==
            labels
        ).sum().item()


        total += (
            labels.size(0)
        )


    average_loss = (
        total_loss
        / total
    )


    accuracy = (
        correct
        / total
    )


    return (
        average_loss,
        accuracy
    )


# ============================================================
# EVALUATE
# ============================================================

@torch.no_grad()
def evaluate(
    model,
    loader,
    criterion
):

    model.eval()

    total_loss = 0.0

    correct = 0
    total = 0


    confusion = torch.zeros(
        (
            2,
            2
        ),
        dtype=torch.int64
    )


    for images, labels in loader:

        images = images.to(
            DEVICE
        )

        labels = labels.to(
            DEVICE
        )


        logits = model(
            images
        )


        loss = criterion(
            logits,
            labels
        )


        total_loss += (
            loss.item()
            * images.size(0)
        )


        predictions = (
            logits.argmax(
                dim=1
            )
        )


        correct += (
            predictions
            ==
            labels
        ).sum().item()


        total += (
            labels.size(0)
        )


        labels_cpu = (
            labels.cpu()
        )

        predictions_cpu = (
            predictions.cpu()
        )


        for true_label, predicted_label in zip(
            labels_cpu,
            predictions_cpu
        ):

            confusion[
                true_label.item(),
                predicted_label.item()
            ] += 1


    average_loss = (
        total_loss
        / total
    )


    accuracy = (
        correct
        / total
    )


    return (
        average_loss,
        accuracy,
        confusion
    )


# ============================================================
# FREEZE / UNFREEZE
# ============================================================

def freeze_backbone(
    model
):

    for parameter in (
        model.parameters()
    ):

        parameter.requires_grad = False


    for parameter in (
        model.fc.parameters()
    ):

        parameter.requires_grad = True


def unfreeze_all(
    model
):

    for parameter in (
        model.parameters()
    ):

        parameter.requires_grad = True


# ============================================================
# SAVE MODEL
# ============================================================

def save_checkpoint(
    model,
    train_board_ids,
    val_board_ids,
    best_val_accuracy
):

    checkpoint = {

        "model_name":
            "resnet18",

        "task":
            "occupancy",

        "model_state_dict":
            model.state_dict(),

        "class_names":
            CLASS_NAMES,

        "class_to_idx":
            CLASS_TO_IDX,

        "image_size":
            IMAGE_SIZE,

        "imagenet_mean":
            IMAGENET_MEAN,

        "imagenet_std":
            IMAGENET_STD,

        "best_val_accuracy":
            best_val_accuracy,

        "train_board_ids":
            train_board_ids,

        "val_board_ids":
            val_board_ids
    }


    torch.save(
        checkpoint,
        BEST_MODEL_PATH
    )


# ============================================================
# MAIN
# ============================================================

def main():

    set_seed()


    print()
    print(
        "=========================================="
    )

    print(
        "PBL4 - OCCUPANCY TRAINING"
    )

    print(
        "=========================================="
    )

    print(
        f"Device : {DEVICE}"
    )


    if torch.cuda.is_available():

        print(
            "GPU    : "
            f"{torch.cuda.get_device_name(0)}"
        )


    print()


    # ========================================================
    # DATA
    # ========================================================

    records = (
        collect_records()
    )


    (
        train_records,
        val_records,
        train_board_ids,
        val_board_ids
    ) = split_by_board(
        records
    )


    print(
        f"Boards total : "
        f"{len(train_board_ids) + len(val_board_ids)}"
    )

    print(
        f"Train boards : "
        f"{len(train_board_ids)}"
    )

    print(
        f"Val boards   : "
        f"{len(val_board_ids)}"
    )

    print()

    print(
        f"Images total : "
        f"{len(records)}"
    )

    print(
        f"Train images : "
        f"{len(train_records)}"
    )

    print(
        f"Val images   : "
        f"{len(val_records)}"
    )

    print()


    train_counts = Counter(
        record["class_name"]
        for record in train_records
    )


    val_counts = Counter(
        record["class_name"]
        for record in val_records
    )


    print(
        "Train classes:"
    )

    for name in CLASS_NAMES:

        print(
            f"  {name:<10}: "
            f"{train_counts[name]}"
        )


    print()

    print(
        "Validation classes:"
    )

    for name in CLASS_NAMES:

        print(
            f"  {name:<10}: "
            f"{val_counts[name]}"
        )


    print()


    # ========================================================
    # DATA LOADERS
    # ========================================================

    train_dataset = (
        OccupancyDataset(
            train_records,
            TRAIN_TRANSFORM
        )
    )


    val_dataset = (
        OccupancyDataset(
            val_records,
            VAL_TRANSFORM
        )
    )


    train_loader = DataLoader(
        train_dataset,

        batch_size=
            BATCH_SIZE,

        shuffle=True,

        num_workers=0,

        pin_memory=
            torch.cuda.is_available()
    )


    val_loader = DataLoader(
        val_dataset,

        batch_size=
            BATCH_SIZE,

        shuffle=False,

        num_workers=0,

        pin_memory=
            torch.cuda.is_available()
    )


    # ========================================================
    # MODEL
    # ========================================================

    print(
        "Loading ImageNet pretrained ResNet-18..."
    )


    weights = (
        ResNet18_Weights.DEFAULT
    )


    model = resnet18(
        weights=weights
    )


    input_features = (
        model.fc.in_features
    )


    model.fc = nn.Linear(
        input_features,
        2
    )


    model = model.to(
        DEVICE
    )


    # ========================================================
    # LOSS
    # ========================================================

    class_weights = (
        build_class_weights(
            train_records
        )
    )


    print()

    print(
        "Class weights:"
    )

    print(
        f"  empty    : "
        f"{class_weights[0].item():.3f}"
    )

    print(
        f"  occupied : "
        f"{class_weights[1].item():.3f}"
    )

    print()


    criterion = (
        nn.CrossEntropyLoss(
            weight=
                class_weights
        )
    )


    best_val_accuracy = -1.0

    global_epoch = 0


    # ========================================================
    # PHASE 1
    #
    # TRAIN HEAD ONLY
    # ========================================================

    freeze_backbone(
        model
    )


    optimizer = (
        torch.optim.AdamW(

            model.fc.parameters(),

            lr=
                HEAD_LR,

            weight_decay=
                WEIGHT_DECAY
        )
    )


    print(
        "=========================================="
    )

    print(
        "PHASE 1 - TRAIN CLASSIFICATION HEAD"
    )

    print(
        "=========================================="
    )

    print()


    for phase_epoch in range(
        1,
        HEAD_EPOCHS + 1
    ):

        global_epoch += 1


        (
            train_loss,
            train_accuracy
        ) = train_one_epoch(
            model,
            train_loader,
            criterion,
            optimizer
        )


        (
            val_loss,
            val_accuracy,
            confusion
        ) = evaluate(
            model,
            val_loader,
            criterion
        )


        print(
            f"Epoch "
            f"{global_epoch:02d} | "
            f"train loss "
            f"{train_loss:.4f} | "
            f"train acc "
            f"{train_accuracy:.4f} | "
            f"val loss "
            f"{val_loss:.4f} | "
            f"val acc "
            f"{val_accuracy:.4f}"
        )


        if (
            val_accuracy
            >
            best_val_accuracy
        ):

            best_val_accuracy = (
                val_accuracy
            )

            save_checkpoint(
                model,
                train_board_ids,
                val_board_ids,
                best_val_accuracy
            )


    # ========================================================
    # PHASE 2
    #
    # FINE-TUNE ENTIRE RESNET
    # ========================================================

    unfreeze_all(
        model
    )


    optimizer = (
        torch.optim.AdamW(

            model.parameters(),

            lr=
                FULL_LR,

            weight_decay=
                WEIGHT_DECAY
        )
    )


    print()
    print(
        "=========================================="
    )

    print(
        "PHASE 2 - FINE-TUNE FULL RESNET"
    )

    print(
        "=========================================="
    )

    print()


    for phase_epoch in range(
        1,
        FULL_EPOCHS + 1
    ):

        global_epoch += 1


        (
            train_loss,
            train_accuracy
        ) = train_one_epoch(
            model,
            train_loader,
            criterion,
            optimizer
        )


        (
            val_loss,
            val_accuracy,
            confusion
        ) = evaluate(
            model,
            val_loader,
            criterion
        )


        print(
            f"Epoch "
            f"{global_epoch:02d} | "
            f"train loss "
            f"{train_loss:.4f} | "
            f"train acc "
            f"{train_accuracy:.4f} | "
            f"val loss "
            f"{val_loss:.4f} | "
            f"val acc "
            f"{val_accuracy:.4f}"
        )


        if (
            val_accuracy
            >
            best_val_accuracy
        ):

            best_val_accuracy = (
                val_accuracy
            )

            save_checkpoint(
                model,
                train_board_ids,
                val_board_ids,
                best_val_accuracy
            )


    # ========================================================
    # LOAD BEST MODEL
    # ========================================================

    checkpoint = torch.load(
        BEST_MODEL_PATH,
        map_location=DEVICE,
        weights_only=False
    )


    model.load_state_dict(
        checkpoint[
            "model_state_dict"
        ]
    )


    # ========================================================
    # FINAL VALIDATION
    # ========================================================

    (
        final_loss,
        final_accuracy,
        confusion
    ) = evaluate(
        model,
        val_loader,
        criterion
    )


    print()
    print(
        "=========================================="
    )

    print(
        "TRAINING FINISHED"
    )

    print(
        "=========================================="
    )

    print(
        f"Best validation accuracy: "
        f"{best_val_accuracy:.4f}"
    )

    print()

    print(
        "Confusion matrix"
    )

    print(
        "rows = true"
    )

    print(
        "cols = predicted"
    )

    print()

    print(
        "           empty occupied"
    )

    print(
        f"empty      "
        f"{confusion[0, 0].item():5d} "
        f"{confusion[0, 1].item():8d}"
    )

    print(
        f"occupied   "
        f"{confusion[1, 0].item():5d} "
        f"{confusion[1, 1].item():8d}"
    )


    # ========================================================
    # SAVE TRAINING INFO
    # ========================================================

    info = {

        "model":
            "ResNet-18",

        "task":
            "empty_vs_occupied",

        "total_boards":
            (
                len(train_board_ids)
                +
                len(val_board_ids)
            ),

        "train_boards":
            train_board_ids,

        "val_boards":
            val_board_ids,

        "total_images":
            len(records),

        "train_images":
            len(train_records),

        "val_images":
            len(val_records),

        "best_val_accuracy":
            best_val_accuracy,

        "head_epochs":
            HEAD_EPOCHS,

        "full_epochs":
            FULL_EPOCHS,

        "image_size":
            IMAGE_SIZE,

        "batch_size":
            BATCH_SIZE
    }


    with open(
        METRICS_PATH,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            info,
            file,
            indent=4
        )


    print()

    print(
        "Model saved:"
    )

    print(
        BEST_MODEL_PATH
    )

    print()

    print(
        "Training info:"
    )

    print(
        METRICS_PATH
    )

    print(
        "=========================================="
    )


# ============================================================
# ENTRY
# ============================================================

if __name__ == "__main__":

    main()
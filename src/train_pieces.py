import json
import random
import re
from collections import Counter, defaultdict
from pathlib import Path

from PIL import Image

import torch
from torch import nn
from torch.utils.data import Dataset, DataLoader

from torchvision import transforms
from torchvision.models import (
    convnext_tiny,
    ConvNeXt_Tiny_Weights,
)


# ============================================================
# CONFIG
# ============================================================

SEED = 42

IMAGE_SIZE = 224

# RTX 2050 4GB:
# batch 8 + AMP should be safe.
BATCH_SIZE = 8

VAL_RATIO = 0.20

HEAD_EPOCHS = 5
FULL_EPOCHS = 15

HEAD_LR = 1e-3
FULL_LR = 5e-5

WEIGHT_DECAY = 1e-4

EXPECTED_SCALES = {
    140,
    180,
    220
}


# ============================================================
# PATHS
# ============================================================

PROJECT_ROOT = (
    Path(__file__)
    .resolve()
    .parent
    .parent
)

PIECES_ROOT = (
    PROJECT_ROOT
    / "data"
    / "pieces"
)

MODEL_DIR = (
    PROJECT_ROOT
    / "models"
    / "pieces"
)

MODEL_DIR.mkdir(
    parents=True,
    exist_ok=True
)

BEST_MODEL_PATH = (
    MODEL_DIR
    / "convnext_tiny_pieces_best.pt"
)

TRAINING_INFO_PATH = (
    MODEL_DIR
    / "training_info.json"
)


# ============================================================
# CLASSES
# ============================================================

CLASS_NAMES = [
    "black_bishop",
    "black_king",
    "black_knight",
    "black_pawn",
    "black_queen",
    "black_rook",

    "white_bishop",
    "white_king",
    "white_knight",
    "white_pawn",
    "white_queen",
    "white_rook",
]

CLASS_TO_IDX = {
    name: index
    for index, name in enumerate(CLASS_NAMES)
}


# ============================================================
# DEVICE
# ============================================================

DEVICE = torch.device(
    "cuda"
    if torch.cuda.is_available()
    else "cpu"
)

USE_AMP = (
    DEVICE.type == "cuda"
)


# ============================================================
# SEED
# ============================================================

def set_seed():

    random.seed(SEED)

    torch.manual_seed(SEED)

    if torch.cuda.is_available():

        torch.cuda.manual_seed_all(
            SEED
        )


# ============================================================
# PARSE FILE NAME
# ============================================================
#
# Expected:
#
# 20260911_001234_567_e4_s140.png
#
# board_id:
# 20260911_001234_567
#
# square:
# e4
#
# scale:
# 140
#
# ============================================================

FILE_PATTERN = re.compile(
    r"(.+)_([a-h][1-8])_s(\d+)\.png$"
)


def parse_piece_filename(path):

    match = FILE_PATTERN.match(
        path.name
    )

    if match is None:

        return None

    board_id = match.group(1)

    square_name = match.group(2)

    scale = int(
        match.group(3)
    )

    return {
        "board_id": board_id,
        "square": square_name,
        "scale": scale
    }


# ============================================================
# COLLECT DATA
# ============================================================

def collect_records():

    records = []

    ignored_files = []


    for class_name in CLASS_NAMES:

        class_dir = (
            PIECES_ROOT
            / class_name
        )

        if not class_dir.exists():

            raise FileNotFoundError(
                f"Missing class folder: {class_dir}"
            )


        class_index = (
            CLASS_TO_IDX[
                class_name
            ]
        )


        for path in sorted(
            class_dir.glob("*.png")
        ):

            parsed = (
                parse_piece_filename(
                    path
                )
            )


            if parsed is None:

                ignored_files.append(
                    path
                )

                continue


            if (
                parsed["scale"]
                not in EXPECTED_SCALES
            ):

                ignored_files.append(
                    path
                )

                continue


            records.append(
                {
                    "path": path,

                    "class_name":
                        class_name,

                    "label":
                        class_index,

                    "board_id":
                        parsed[
                            "board_id"
                        ],

                    "square":
                        parsed[
                            "square"
                        ],

                    "scale":
                        parsed[
                            "scale"
                        ],
                }
            )


    if len(records) == 0:

        raise RuntimeError(
            "No valid multi-scale piece images found."
        )


    if ignored_files:

        print()
        print(
            f"Ignored {len(ignored_files)} "
            f"old/invalid piece files."
        )


    return records


# ============================================================
# DATASET AUDIT
# ============================================================

def audit_multiscale(records):

    instances = defaultdict(
        set
    )


    for record in records:

        key = (
            record["board_id"],
            record["square"],
            record["class_name"]
        )

        instances[key].add(
            record["scale"]
        )


    incomplete = []


    for key, scales in instances.items():

        if scales != EXPECTED_SCALES:

            incomplete.append(
                (
                    key,
                    scales
                )
            )


    print()
    print(
        "=========================================="
    )

    print(
        "PIECE DATASET AUDIT"
    )

    print(
        "=========================================="
    )


    print(
        f"Actual piece instances : "
        f"{len(instances)}"
    )


    print(
        f"Multi-scale image files: "
        f"{len(records)}"
    )


    print(
        f"Expected scales         : "
        f"{sorted(EXPECTED_SCALES)}"
    )


    if incomplete:

        print()

        print(
            f"WARNING: "
            f"{len(incomplete)} piece instances "
            f"do not contain all 3 scales."
        )


        for key, scales in incomplete[:10]:

            print(
                f"  {key} -> "
                f"{sorted(scales)}"
            )

    else:

        print(
            "All piece instances have "
            "140/180/220 crops."
        )


    print(
        "=========================================="
    )

    print()


# ============================================================
# BOARD SPLIT
# ============================================================
#
# Critical:
#
# ALL piece crops belonging to one board stay together.
#
# If board A goes to train:
#
# every:
#   rook
#   queen
#   pawn
#   s140
#   s180
#   s220
#
# from board A stays in train.
#
# ============================================================

def split_by_board(records):

    board_ids = sorted(
        {
            record["board_id"]
            for record in records
        }
    )


    if len(board_ids) < 5:

        raise RuntimeError(
            "Need at least 5 board positions."
        )


    val_count = max(
        1,
        round(
            len(board_ids)
            * VAL_RATIO
        )
    )


    val_count = min(
        val_count,
        len(board_ids) - 1
    )


    # --------------------------------------------------------
    # Search for a deterministic split where training
    # contains all 12 classes.
    # --------------------------------------------------------

    best_split = None


    for attempt in range(1000):

        rng = random.Random(
            SEED + attempt
        )

        shuffled = (
            board_ids.copy()
        )

        rng.shuffle(
            shuffled
        )


        val_ids = set(
            shuffled[:val_count]
        )

        train_ids = set(
            shuffled[val_count:]
        )


        train_records = [
            record
            for record in records
            if record["board_id"]
            in train_ids
        ]


        train_classes = {
            record["class_name"]
            for record in train_records
        }


        if (
            train_classes
            ==
            set(CLASS_NAMES)
        ):

            best_split = (
                train_ids,
                val_ids
            )

            break


    if best_split is None:

        raise RuntimeError(
            "Could not create a train split "
            "containing all 12 piece classes.\n"
            "You probably need more board positions."
        )


    train_ids, val_ids = (
        best_split
    )


    train_records = [
        record
        for record in records
        if record["board_id"]
        in train_ids
    ]


    val_records = [
        record
        for record in records
        if record["board_id"]
        in val_ids
    ]


    return (
        train_records,
        val_records,
        sorted(train_ids),
        sorted(val_ids)
    )


# ============================================================
# TRANSFORMS
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
            brightness=0.15,
            contrast=0.15,
            saturation=0.10,
            hue=0.02
        ),

        transforms.RandomAffine(
            degrees=3,

            translate=(
                0.025,
                0.025
            ),

            scale=(
                0.96,
                1.04
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

class PieceDataset(Dataset):

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


        label = (
            record["label"]
        )


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
                "Training set has no samples for "
                f"{CLASS_NAMES[class_index]}"
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
# AMP
# ============================================================

def make_grad_scaler():

    if USE_AMP:

        return torch.amp.GradScaler(
            "cuda"
        )

    return None


# ============================================================
# TRAIN ONE EPOCH
# ============================================================

def train_one_epoch(
    model,
    loader,
    criterion,
    optimizer,
    scaler
):

    model.train()


    total_loss = 0.0

    correct = 0
    total = 0


    for images, labels in loader:


        images = images.to(
            DEVICE,
            non_blocking=True
        )


        labels = labels.to(
            DEVICE,
            non_blocking=True
        )


        optimizer.zero_grad(
            set_to_none=True
        )


        # ====================================================
        # CUDA AMP
        # ====================================================

        if USE_AMP:

            with torch.amp.autocast(
                device_type="cuda",
                dtype=torch.float16
            ):

                logits = model(
                    images
                )

                loss = criterion(
                    logits,
                    labels
                )


            scaler.scale(
                loss
            ).backward()


            scaler.step(
                optimizer
            )


            scaler.update()


        # ====================================================
        # CPU
        # ====================================================

        else:

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
            *
            images.size(0)
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


    return (
        total_loss / total,
        correct / total
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


    num_classes = len(
        CLASS_NAMES
    )


    confusion = torch.zeros(
        (
            num_classes,
            num_classes
        ),
        dtype=torch.int64
    )


    for images, labels in loader:


        images = images.to(
            DEVICE,
            non_blocking=True
        )


        labels = labels.to(
            DEVICE,
            non_blocking=True
        )


        if USE_AMP:

            with torch.amp.autocast(
                device_type="cuda",
                dtype=torch.float16
            ):

                logits = model(
                    images
                )

                loss = criterion(
                    logits,
                    labels
                )

        else:

            logits = model(
                images
            )

            loss = criterion(
                logits,
                labels
            )


        total_loss += (
            loss.item()
            *
            images.size(0)
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


        labels_cpu = labels.cpu()

        predictions_cpu = (
            predictions.cpu()
        )


        for true_class, pred_class in zip(
            labels_cpu,
            predictions_cpu
        ):

            confusion[
                true_class.item(),
                pred_class.item()
            ] += 1


    return (
        total_loss / total,
        correct / total,
        confusion
    )


# ============================================================
# FREEZE BACKBONE
# ============================================================

def freeze_backbone(
    model
):

    for parameter in (
        model.parameters()
    ):

        parameter.requires_grad = False


    # ConvNeXt classifier:
    #
    # classifier[0] = LayerNorm
    # classifier[1] = Flatten
    # classifier[2] = Linear
    #
    for parameter in (
        model.classifier.parameters()
    ):

        parameter.requires_grad = True


# ============================================================
# UNFREEZE ALL
# ============================================================

def unfreeze_all(
    model
):

    for parameter in (
        model.parameters()
    ):

        parameter.requires_grad = True


# ============================================================
# SAVE CHECKPOINT
# ============================================================

def save_checkpoint(
    model,
    train_board_ids,
    val_board_ids,
    best_val_accuracy
):

    checkpoint = {

        "model_name":
            "convnext_tiny",

        "task":
            "piece_classification",

        "model_state_dict":
            model.state_dict(),

        "class_names":
            CLASS_NAMES,

        "class_to_idx":
            CLASS_TO_IDX,

        "image_size":
            IMAGE_SIZE,

        "piece_crop_sizes":
            sorted(
                EXPECTED_SCALES
            ),

        "imagenet_mean":
            IMAGENET_MEAN,

        "imagenet_std":
            IMAGENET_STD,

        "best_val_accuracy":
            best_val_accuracy,

        "train_board_ids":
            train_board_ids,

        "val_board_ids":
            val_board_ids,
    }


    torch.save(
        checkpoint,
        BEST_MODEL_PATH
    )


# ============================================================
# PRINT CONFUSION MATRIX
# ============================================================

def print_confusion_matrix(
    confusion
):

    print()
    print(
        "Confusion matrix:"
    )

    print(
        "rows = true, cols = predicted"
    )

    print()


    abbreviations = [
        "bB",
        "bK",
        "bN",
        "bP",
        "bQ",
        "bR",

        "wB",
        "wK",
        "wN",
        "wP",
        "wQ",
        "wR",
    ]


    print(
        "      "
        +
        " ".join(
            f"{name:>4}"
            for name in abbreviations
        )
    )


    for row_index, row_name in enumerate(
        abbreviations
    ):

        values = " ".join(
            f"{confusion[row_index, col].item():4d}"
            for col in range(
                len(abbreviations)
            )
        )

        print(
            f"{row_name:>4}  {values}"
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
        "PBL4 - CONVNEXT PIECE TRAINING"
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


    print(
        f"AMP    : {USE_AMP}"
    )

    print()


    # ========================================================
    # DATA
    # ========================================================

    records = collect_records()


    audit_multiscale(
        records
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
        f"Piece images total : "
        f"{len(records)}"
    )

    print(
        f"Train images       : "
        f"{len(train_records)}"
    )

    print(
        f"Val images         : "
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
        "Train class counts:"
    )


    for class_name in CLASS_NAMES:

        print(
            f"  {class_name:<15}: "
            f"{train_counts[class_name]}"
        )


    print()

    print(
        "Validation class counts:"
    )


    for class_name in CLASS_NAMES:

        print(
            f"  {class_name:<15}: "
            f"{val_counts[class_name]}"
        )


    print()


    missing_val_classes = [

        class_name

        for class_name in CLASS_NAMES

        if val_counts[
            class_name
        ] == 0
    ]


    if missing_val_classes:

        print(
            "WARNING:"
        )

        print(
            "Validation has no samples for:"
        )

        print(
            missing_val_classes
        )

        print()


    # ========================================================
    # DATASETS
    # ========================================================

    train_dataset = PieceDataset(
        train_records,
        TRAIN_TRANSFORM
    )


    val_dataset = PieceDataset(
        val_records,
        VAL_TRANSFORM
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
        "Loading ImageNet pretrained ConvNeXt-Tiny..."
    )


    model = convnext_tiny(
        weights=
            ConvNeXt_Tiny_Weights.DEFAULT
    )


    in_features = (
        model.classifier[2]
        .in_features
    )


    model.classifier[2] = (
        nn.Linear(
            in_features,
            len(CLASS_NAMES)
        )
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


    for index, class_name in enumerate(
        CLASS_NAMES
    ):

        print(
            f"  {class_name:<15}: "
            f"{class_weights[index].item():.3f}"
        )


    criterion = (
        nn.CrossEntropyLoss(
            weight=
                class_weights
        )
    )


    scaler = (
        make_grad_scaler()
    )


    best_val_accuracy = -1.0

    global_epoch = 0


    # ========================================================
    # PHASE 1
    # ========================================================

    freeze_backbone(
        model
    )


    optimizer = (
        torch.optim.AdamW(

            model.classifier.parameters(),

            lr=
                HEAD_LR,

            weight_decay=
                WEIGHT_DECAY
        )
    )


    print()
    print(
        "=========================================="
    )

    print(
        "PHASE 1 - TRAIN CONVNEXT HEAD"
    )

    print(
        "=========================================="
    )


    for _ in range(
        HEAD_EPOCHS
    ):

        global_epoch += 1


        (
            train_loss,
            train_accuracy
        ) = train_one_epoch(
            model,
            train_loader,
            criterion,
            optimizer,
            scaler
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
        "PHASE 2 - FINE-TUNE FULL CONVNEXT"
    )

    print(
        "=========================================="
    )


    for _ in range(
        FULL_EPOCHS
    ):

        global_epoch += 1


        (
            train_loss,
            train_accuracy
        ) = train_one_epoch(
            model,
            train_loader,
            criterion,
            optimizer,
            scaler
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
    # LOAD BEST
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


    print_confusion_matrix(
        confusion
    )


    # ========================================================
    # SAVE INFO
    # ========================================================

    info = {

        "model":
            "ConvNeXt-Tiny",

        "task":
            "12_class_piece_classification",

        "classes":
            CLASS_NAMES,

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

        "crop_scales":
            sorted(
                EXPECTED_SCALES
            ),

        "best_val_accuracy":
            best_val_accuracy,

        "head_epochs":
            HEAD_EPOCHS,

        "full_epochs":
            FULL_EPOCHS,

        "batch_size":
            BATCH_SIZE,

        "image_size":
            IMAGE_SIZE,
    }


    with open(
        TRAINING_INFO_PATH,
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
        TRAINING_INFO_PATH
    )


    print()
    print(
        "=========================================="
    )


# ============================================================
# ENTRY
# ============================================================

if __name__ == "__main__":

    main()
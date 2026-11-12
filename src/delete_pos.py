import json
import re
from pathlib import Path


# ============================================================
# SAMPLE ID
# ============================================================

SAMPLE_ID_PATTERN = re.compile(
    r"^\d{8}_\d{6}_\d{3}$"
)


# ============================================================
# FIND PROJECT ROOT
# ============================================================

def find_project_root():
    """
    Tìm thư mục project chứa:
        data/
            raw/
            context/
            boards/
            occupancy/
            pieces/

    Có thể đặt file này ở project root hoặc trong thư mục con.
    """

    current = Path(__file__).resolve().parent

    candidates = [
        current,
        current.parent,
        current.parent.parent,
        current.parent.parent.parent,
    ]

    for candidate in candidates:

        data_dir = candidate / "data"

        if (
            data_dir.exists()
            and
            (data_dir / "raw").exists()
            and
            (data_dir / "boards").exists()
        ):
            return candidate

    raise RuntimeError(
        "Cannot find project root.\n"
        "Expected a data/ folder containing raw/, boards/, etc."
    )


# ============================================================
# PATHS
# ============================================================

PROJECT_ROOT = find_project_root()

DATA_ROOT = PROJECT_ROOT / "data"

RAW_DIR = DATA_ROOT / "raw"
CONTEXT_DIR = DATA_ROOT / "context"
BOARDS_DIR = DATA_ROOT / "boards"

OCCUPANCY_DIR = DATA_ROOT / "occupancy"
EMPTY_DIR = OCCUPANCY_DIR / "empty"
OCCUPIED_DIR = OCCUPANCY_DIR / "occupied"

PIECES_DIR = DATA_ROOT / "pieces"


# ============================================================
# VALIDATE SAMPLE ID
# ============================================================

def validate_sample_id(sample_id):

    if not SAMPLE_ID_PATTERN.fullmatch(sample_id):

        print()
        print("INVALID POSITION ID.")
        print()
        print(
            "Required format:"
            " YYYYMMDD_HHMMSS_mmm"
        )
        print()
        print(
            "Example:"
            " 20261020_172034_298"
        )
        print()

        return False

    return True


# ============================================================
# VERIFY METADATA
# ============================================================

def verify_metadata(sample_id):

    metadata_path = (
        BOARDS_DIR /
        f"{sample_id}.json"
    )

    if not metadata_path.exists():
        return True

    try:

        with open(
            metadata_path,
            "r",
            encoding="utf-8"
        ) as file:

            metadata = json.load(file)

    except Exception as error:

        print()
        print("ERROR:")
        print(
            "Metadata JSON exists but cannot be read."
        )
        print(metadata_path)
        print(error)
        print()
        print(
            "For safety, NOTHING was deleted."
        )

        return False

    metadata_sample_id = metadata.get(
        "sample_id"
    )

    if metadata_sample_id != sample_id:

        print()
        print("DANGER:")
        print(
            "Filename sample ID and JSON sample ID "
            "do not match."
        )
        print()
        print(
            f"Requested : {sample_id}"
        )
        print(
            f"JSON ID   : {metadata_sample_id}"
        )
        print()
        print(
            "For safety, NOTHING was deleted."
        )

        return False

    return True


# ============================================================
# EXACT FILE PATTERNS
# ============================================================

def is_exact_occupancy_file(
    filename,
    sample_id
):

    pattern = re.compile(
        rf"^{re.escape(sample_id)}_"
        rf"[a-h][1-8]\.png$"
    )

    return bool(
        pattern.fullmatch(filename)
    )


def is_exact_piece_file(
    filename,
    sample_id
):

    pattern = re.compile(
        rf"^{re.escape(sample_id)}_"
        rf"[a-h][1-8]_"
        rf"s\d+\.png$"
    )

    return bool(
        pattern.fullmatch(filename)
    )


# ============================================================
# FIND FILES BELONGING TO ONE POSITION
# ============================================================

def find_position_files(sample_id):

    files_to_delete = []


    # ========================================================
    # RAW
    # ========================================================

    raw_file = (
        RAW_DIR /
        f"{sample_id}.png"
    )

    if raw_file.is_file():
        files_to_delete.append(
            raw_file
        )


    # ========================================================
    # CONTEXT
    # ========================================================

    context_file = (
        CONTEXT_DIR /
        f"{sample_id}.png"
    )

    if context_file.is_file():
        files_to_delete.append(
            context_file
        )


    # ========================================================
    # BOARD IMAGE
    # ========================================================

    board_image = (
        BOARDS_DIR /
        f"{sample_id}.png"
    )

    if board_image.is_file():
        files_to_delete.append(
            board_image
        )


    # ========================================================
    # BOARD JSON
    # ========================================================

    board_json = (
        BOARDS_DIR /
        f"{sample_id}.json"
    )

    if board_json.is_file():
        files_to_delete.append(
            board_json
        )


    # ========================================================
    # OCCUPANCY
    # ========================================================

    occupancy_folders = [
        EMPTY_DIR,
        OCCUPIED_DIR,
    ]

    for folder in occupancy_folders:

        if not folder.exists():
            continue

        for path in folder.glob(
            f"{sample_id}_*.png"
        ):

            if (
                path.is_file()
                and
                is_exact_occupancy_file(
                    path.name,
                    sample_id
                )
            ):

                files_to_delete.append(
                    path
                )


    # ========================================================
    # PIECE CROPS
    # ========================================================

    if PIECES_DIR.exists():

        for class_folder in PIECES_DIR.iterdir():

            if not class_folder.is_dir():
                continue

            for path in class_folder.glob(
                f"{sample_id}_*.png"
            ):

                if (
                    path.is_file()
                    and
                    is_exact_piece_file(
                        path.name,
                        sample_id
                    )
                ):

                    files_to_delete.append(
                        path
                    )


    # ========================================================
    # REMOVE DUPLICATES
    # ========================================================

    unique_files = sorted(
        set(files_to_delete),
        key=lambda path: str(path)
    )

    return unique_files


# ============================================================
# SHOW FILES
# ============================================================

def show_files(
    sample_id,
    files
):

    print()
    print(
        "=========================================="
    )
    print(
        "POSITION DELETE PREVIEW"
    )
    print(
        "=========================================="
    )

    print()
    print(
        f"Position ID:"
        f" {sample_id}"
    )

    print()
    print(
        f"Files found:"
        f" {len(files)}"
    )

    print()

    for index, path in enumerate(
        files,
        start=1
    ):

        try:

            relative_path = (
                path.relative_to(
                    PROJECT_ROOT
                )
            )

        except ValueError:

            relative_path = path

        print(
            f"{index:03d}. "
            f"{relative_path}"
        )

    print()
    print(
        "=========================================="
    )


# ============================================================
# DELETE POSITION
# ============================================================

def delete_position(sample_id):

    # --------------------------------------------------------
    # Validate ID
    # --------------------------------------------------------

    if not validate_sample_id(
        sample_id
    ):
        return


    # --------------------------------------------------------
    # Verify metadata
    # --------------------------------------------------------

    if not verify_metadata(
        sample_id
    ):
        return


    # --------------------------------------------------------
    # Find exact files
    # --------------------------------------------------------

    files = find_position_files(
        sample_id
    )


    if not files:

        print()
        print(
            "POSITION NOT FOUND."
        )
        print()
        print(
            "No file matching this exact "
            "position ID was found."
        )
        print()
        print(
            "Nothing was deleted."
        )

        return


    # --------------------------------------------------------
    # Preview
    # --------------------------------------------------------

    show_files(
        sample_id,
        files
    )


    # --------------------------------------------------------
    # Confirmation
    # --------------------------------------------------------

    print()
    print(
        "WARNING:"
    )
    print(
        "The files above will be "
        "PERMANENTLY deleted."
    )

    print()
    print(
        "To confirm, type the EXACT "
        "position ID again."
    )

    print()
    print(
        "Press ENTER without typing "
        "anything to cancel."
    )
    print()


    confirmation = input(
        "CONFIRM ID > "
    ).strip()


    if confirmation != sample_id:

        print()
        print(
            "Confirmation does not match."
        )
        print(
            "DELETE CANCELLED."
        )
        print()
        print(
            "Nothing was deleted."
        )

        return


    # --------------------------------------------------------
    # Delete
    # --------------------------------------------------------

    deleted_files = []

    failed_files = []


    for path in files:

        try:

            path.unlink()

            deleted_files.append(
                path
            )

        except Exception as error:

            failed_files.append(
                (
                    path,
                    error
                )
            )


    # --------------------------------------------------------
    # Result
    # --------------------------------------------------------

    print()
    print(
        "=========================================="
    )
    print(
        "DELETE RESULT"
    )
    print(
        "=========================================="
    )

    print()
    print(
        f"Position ID:"
        f" {sample_id}"
    )

    print(
        f"Deleted files:"
        f" {len(deleted_files)}"
    )

    print(
        f"Failed files :"
        f" {len(failed_files)}"
    )


    if failed_files:

        print()
        print(
            "FAILED TO DELETE:"
        )

        for path, error in failed_files:

            print()
            print(path)
            print(
                f"  Error: {error}"
            )

        print()
        print(
            "WARNING:"
        )
        print(
            "The position was only "
            "partially deleted."
        )

    else:

        print()
        print(
            "SUCCESS."
        )
        print(
            "Only the requested position "
            "was deleted."
        )

    print()
    print(
        "=========================================="
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print(
        "=========================================="
    )
    print(
        "PBL4 DATASET POSITION DELETER"
    )
    print(
        "=========================================="
    )

    print()
    print(
        f"Project root:"
        f" {PROJECT_ROOT}"
    )

    print()
    print(
        "Enter the position/sample ID."
    )

    print(
        "Example:"
        " 20261020_172034_298"
    )

    print()

    sample_id = input(
        "POSITION ID > "
    ).strip()


    if sample_id == "":

        print()
        print(
            "Cancelled."
        )

        return


    delete_position(
        sample_id
    )


if __name__ == "__main__":
    main()
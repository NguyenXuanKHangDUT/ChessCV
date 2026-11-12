import chess
import chess.pgn

import logging
import random

from collections import Counter
from pathlib import Path


# ============================================================
# SILENCE EXPECTED PGN PARSER ERRORS
# ============================================================
#
# Lichess Broadcast can contain:
# - Chess960 / variants
# - games started from a custom FEN
# - malformed PGN records
#
# python-chess normally prints parser errors to stderr while
# reading those games. We filter them out below anyway, so
# suppress those messages to keep the terminal clean.
#
# ============================================================

logging.getLogger("chess.pgn").setLevel(
    logging.CRITICAL
)


# ============================================================
# CONFIG
# ============================================================

SEED = 42

TARGET_TOTAL = 100

QUOTAS = {
    "opening": 20,
    "middlegame": 55,
    "endgame": 25,
}

# Number of VALID STANDARD games to use as the candidate pool.
MAX_GAMES = 10000

# Do not take positions too close to the initial position.
MIN_PLY = 8


PROJECT_ROOT = (
    Path(__file__)
    .resolve()
    .parent
    .parent
)

PGN_PATH = (
    PROJECT_ROOT
    / "data"
    / "source_games.pgn"
)

OUTPUT_PATH = (
    PROJECT_ROOT
    / "data"
    / "selected_100_fens.txt"
)

REPORT_PATH = (
    PROJECT_ROOT
    / "data"
    / "selected_100_fens_report.txt"
)


# ============================================================
# PIECE CLASS
# ============================================================

def piece_class(piece):

    color = (
        "white"
        if piece.color == chess.WHITE
        else "black"
    )

    names = {
        chess.PAWN: "pawn",
        chess.KNIGHT: "knight",
        chess.BISHOP: "bishop",
        chess.ROOK: "rook",
        chess.QUEEN: "queen",
        chess.KING: "king",
    }

    return (
        f"{color}_"
        f"{names[piece.piece_type]}"
    )


# ============================================================
# PHASE
# ============================================================
#
# Phase is intentionally based on number of pieces remaining.
# For this CV dataset, this gives useful visual diversity and
# avoids depending only on move number.
#
# ============================================================

def get_phase(board):

    pieces = len(
        board.piece_map()
    )

    if pieces >= 27:
        return "opening"

    if pieces >= 17:
        return "middlegame"

    return "endgame"


# ============================================================
# STANDARD-CHESS FILTER
# ============================================================
#
# We only want normal chess games that:
#
# 1. parsed without errors
# 2. are Standard Chess
# 3. are NOT Chess960
# 4. begin from the normal starting position
#
# This removes the strange back-rank positions such as:
#
#   qrbbnknr
#   brqknbrn
#   bbnqrnkr
#
# ============================================================

def validate_standard_game(game):

    # --------------------------------------------------------
    # Broken / partially parsed PGN
    # --------------------------------------------------------

    if game.errors:

        return (
            False,
            "parse_error"
        )


    # --------------------------------------------------------
    # Variant header
    # --------------------------------------------------------

    variant = (
        game.headers
        .get(
            "Variant",
            "Standard"
        )
        .strip()
        .lower()
    )

    if variant not in {
        "standard",
        "chess",
    }:

        return (
            False,
            "variant"
        )


    # --------------------------------------------------------
    # Starting board
    # --------------------------------------------------------

    try:

        initial_board = (
            game.board()
        )

    except Exception:

        return (
            False,
            "invalid_start"
        )


    # --------------------------------------------------------
    # Explicit Chess960
    # --------------------------------------------------------

    if initial_board.chess960:

        return (
            False,
            "chess960"
        )


    # --------------------------------------------------------
    # Must start from the NORMAL chess starting position.
    #
    # Exact FEN comparison also rejects games that start from
    # a custom SetUp/FEN position.
    # --------------------------------------------------------

    if (
        initial_board.fen()
        !=
        chess.STARTING_FEN
    ):

        return (
            False,
            "nonstandard_start"
        )


    return (
        True,
        None
    )


# ============================================================
# POSITION FEATURES
# ============================================================

def get_features(board):

    features = set()


    for square in chess.SQUARES:

        piece = board.piece_at(
            square
        )

        square_name = (
            chess.square_name(
                square
            )
        )


        # ====================================================
        # EMPTY
        # ====================================================

        if piece is None:

            features.add(
                (
                    "empty",
                    square_name
                )
            )


        # ====================================================
        # OCCUPIED
        # ====================================================

        else:

            features.add(
                (
                    "occupied",
                    square_name
                )
            )

            features.add(
                (
                    "piece_square",
                    piece_class(piece),
                    square_name
                )
            )


    return features


# ============================================================
# SCORE
# ============================================================
#
# Rare pieces receive more weight because Pawn naturally gets
# many more observations than King / Queen / Rook.
#
# ============================================================

RARE_WEIGHT = {
    "king": 4.0,
    "queen": 4.0,
    "rook": 3.0,
    "bishop": 2.0,
    "knight": 2.0,
    "pawn": 1.0,
}


def score_candidate(
    candidate,
    feature_counts
):

    score = 0.0

    board = candidate[
        "board"
    ]


    for square in chess.SQUARES:

        square_name = (
            chess.square_name(
                square
            )
        )

        piece = board.piece_at(
            square
        )


        # ====================================================
        # EMPTY COVERAGE
        # ====================================================

        if piece is None:

            key = (
                "empty",
                square_name
            )

            count = feature_counts[
                key
            ]

            # Never-seen empty square
            if count == 0:

                score += 1.5

            # Still underrepresented
            elif count < 5:

                score += 0.3


        # ====================================================
        # OCCUPIED COVERAGE
        # ====================================================

        else:

            occupied_key = (
                "occupied",
                square_name
            )

            occupied_count = (
                feature_counts[
                    occupied_key
                ]
            )

            # Strongly reward a square that has never been
            # occupied in the selected dataset.
            if occupied_count == 0:

                score += 4.0

            elif occupied_count < 5:

                score += 1.0


            # ================================================
            # PIECE + SQUARE COVERAGE
            # ================================================

            cls = piece_class(
                piece
            )

            piece_name = (
                cls.split(
                    "_",
                    1
                )[1]
            )

            key = (
                "piece_square",
                cls,
                square_name
            )

            count = feature_counts[
                key
            ]

            rarity = (
                RARE_WEIGHT[
                    piece_name
                ]
            )


            # First time this exact colored piece class has
            # appeared on this exact square.
            if count == 0:

                score += (
                    6.0
                    *
                    rarity
                )


            # Second observation is still valuable.
            elif count == 1:

                score += (
                    1.5
                    *
                    rarity
                )


    return score


# ============================================================
# EXTRACT CANDIDATES
# ============================================================

def load_candidates():

    random.seed(
        SEED
    )

    candidates = []

    scanned_games = 0
    valid_standard_games = 0

    skip_counts = Counter()

    # --------------------------------------------------------
    # Prevent duplicate VISUAL board layouts.
    #
    # board_fen() ignores side-to-move, castling rights,
    # en-passant and clocks because those are invisible to
    # the camera.
    # --------------------------------------------------------

    seen_visual_positions = set()


    with open(
        PGN_PATH,
        "r",
        encoding="utf-8",
        errors="replace"
    ) as pgn:


        while (
            valid_standard_games
            <
            MAX_GAMES
        ):

            try:

                game = chess.pgn.read_game(
                    pgn
                )

            except Exception:

                # Extremely malformed record.
                skip_counts[
                    "read_exception"
                ] += 1

                continue


            if game is None:

                break


            scanned_games += 1


            # =================================================
            # STANDARD-CHESS FILTER
            # =================================================

            valid, reason = (
                validate_standard_game(
                    game
                )
            )


            if not valid:

                skip_counts[
                    reason
                ] += 1

                continue


            valid_standard_games += 1

            game_id = (
                valid_standard_games
            )


            # =================================================
            # START NORMAL GAME
            # =================================================

            board = game.board()


            positions_by_phase = {
                "opening": [],
                "middlegame": [],
                "endgame": [],
            }


            ply = 0


            # =================================================
            # READ MAIN LINE
            # =================================================

            try:

                for move in (
                    game.mainline_moves()
                ):

                    board.push(
                        move
                    )

                    ply += 1


                    # -----------------------------------------
                    # Skip extremely early positions.
                    # -----------------------------------------

                    if ply < MIN_PLY:

                        continue


                    # -----------------------------------------
                    # Extra safety check.
                    # -----------------------------------------

                    if not board.is_valid():

                        continue


                    phase = get_phase(
                        board
                    )


                    positions_by_phase[
                        phase
                    ].append(
                        board.copy(
                            stack=False
                        )
                    )


            except Exception:

                # This should be rare because game.errors has
                # already been checked, but do not let one bad
                # game stop the whole dataset build.
                skip_counts[
                    "move_iteration_error"
                ] += 1

                continue


            # =================================================
            # AT MOST ONE CANDIDATE PER PHASE PER GAME
            # =================================================
            #
            # A game can contribute:
            #
            #   0 or 1 opening candidate
            #   0 or 1 middlegame candidate
            #   0 or 1 endgame candidate
            #
            # Later selection still allows at most ONE final
            # selected position per game.
            #
            # =================================================

            for phase, positions in (
                positions_by_phase.items()
            ):

                if not positions:

                    continue


                # Deterministic because random.seed(SEED)
                chosen = random.choice(
                    positions
                )


                # =============================================
                # VISUAL DEDUPLICATION
                # =============================================

                visual_key = (
                    chosen.board_fen()
                )


                if (
                    visual_key
                    in
                    seen_visual_positions
                ):

                    skip_counts[
                        "duplicate_visual_position"
                    ] += 1

                    continue


                seen_visual_positions.add(
                    visual_key
                )


                # =============================================
                # SOURCE METADATA
                # =============================================

                candidates.append(
                    {
                        "game_id":
                            game_id,

                        "phase":
                            phase,

                        "board":
                            chosen,

                        "fen":
                            chosen.fen(),

                        "event":
                            game.headers.get(
                                "Event",
                                "?"
                            ),

                        "white":
                            game.headers.get(
                                "White",
                                "?"
                            ),

                        "black":
                            game.headers.get(
                                "Black",
                                "?"
                            ),

                        "date":
                            game.headers.get(
                                "Date",
                                "?"
                            ),
                    }
                )


    # ========================================================
    # SUMMARY
    # ========================================================

    print()

    print(
        "=========================================="
    )

    print(
        "PGN FILTER SUMMARY"
    )

    print(
        "=========================================="
    )


    print(
        f"Scanned PGN games       : "
        f"{scanned_games}"
    )

    print(
        f"Valid Standard games    : "
        f"{valid_standard_games}"
    )

    print(
        f"Unique candidate boards : "
        f"{len(candidates)}"
    )


    if skip_counts:

        print()

        print(
            "Skipped:"
        )

        for reason, count in sorted(
            skip_counts.items()
        ):

            print(
                f"  {reason:<28}: "
                f"{count}"
            )


    print(
        "=========================================="
    )

    print()


    return candidates


# ============================================================
# GREEDY SELECTION
# ============================================================

def select_positions(
    candidates
):

    selected = []

    feature_counts = Counter()

    phase_counts = Counter()

    used_games = set()


    while (
        len(selected)
        <
        TARGET_TOTAL
    ):


        best = None
        best_score = -1.0


        for candidate in candidates:


            # =================================================
            # ONLY ONE FINAL POSITION PER GAME
            # =================================================

            if (
                candidate["game_id"]
                in used_games
            ):

                continue


            phase = candidate[
                "phase"
            ]


            # =================================================
            # PHASE QUOTA
            # =================================================

            if (
                phase_counts[
                    phase
                ]
                >=
                QUOTAS[
                    phase
                ]
            ):

                continue


            score = score_candidate(
                candidate,
                feature_counts
            )


            if score > best_score:

                best_score = score
                best = candidate


        # ====================================================
        # NO MORE VALID CANDIDATES
        # ====================================================

        if best is None:

            print()

            print(
                "Could not satisfy all quotas."
            )

            print(
                "Try increasing MAX_GAMES."
            )

            print()

            break


        # ====================================================
        # SELECT
        # ====================================================

        selected.append(
            best
        )


        used_games.add(
            best["game_id"]
        )


        phase_counts[
            best["phase"]
        ] += 1


        for feature in get_features(
            best["board"]
        ):

            feature_counts[
                feature
            ] += 1


        print(
            f"{len(selected):3d}/"
            f"{TARGET_TOTAL} "
            f"{best['phase']:<10} "
            f"score={best_score:.1f}"
        )


    return (
        selected,
        feature_counts,
        phase_counts
    )


# ============================================================
# COVERAGE HELPERS
# ============================================================

def get_square_counts(
    feature_counts,
    feature_type
):

    result = {}


    for square in chess.SQUARES:

        name = (
            chess.square_name(
                square
            )
        )

        result[
            name
        ] = feature_counts[
            (
                feature_type,
                name
            )
        ]


    return result


def write_square_grid(
    file,
    title,
    counts
):

    file.write(
        f"\n{title}\n"
    )


    for rank in range(
        8,
        0,
        -1
    ):

        for file_name in (
            "abcdefgh"
        ):

            square = (
                file_name
                +
                str(rank)
            )

            file.write(
                f"{square}:"
                f"{counts[square]:3d} "
            )

        file.write(
            "\n"
        )


# ============================================================
# REPORT
# ============================================================

def write_results(
    selected,
    feature_counts,
    phase_counts
):


    # ========================================================
    # FEN LIST
    # ========================================================

    with open(
        OUTPUT_PATH,
        "w",
        encoding="utf-8"
    ) as f:


        for index, item in enumerate(
            selected,
            start=1
        ):

            f.write(
                f"{index:03d}\t"
                f"{item['phase']}\t"
                f"{item['fen']}\n"
            )


    # ========================================================
    # SQUARE COVERAGE
    # ========================================================

    occupied_counts = (
        get_square_counts(
            feature_counts,
            "occupied"
        )
    )

    empty_counts = (
        get_square_counts(
            feature_counts,
            "empty"
        )
    )


    # ========================================================
    # DISTINCT SQUARES PER PIECE CLASS
    # ========================================================

    piece_distinct_squares = (
        Counter()
    )


    for key, count in (
        feature_counts.items()
    ):

        if (
            len(key) == 3
            and
            key[0] == "piece_square"
            and
            count > 0
        ):

            cls = key[
                1
            ]

            piece_distinct_squares[
                cls
            ] += 1


    # ========================================================
    # TOTAL PIECE OBSERVATIONS PER CLASS
    # ========================================================

    piece_observations = Counter()


    for item in selected:

        for piece in (
            item["board"]
            .piece_map()
            .values()
        ):

            piece_observations[
                piece_class(
                    piece
                )
            ] += 1


    # ========================================================
    # TOTAL OCCUPIED / EMPTY SAMPLES
    # ========================================================

    total_occupied = sum(
        occupied_counts.values()
    )

    total_empty = sum(
        empty_counts.values()
    )


    min_occupied_square = min(
        occupied_counts,
        key=occupied_counts.get
    )

    max_occupied_square = max(
        occupied_counts,
        key=occupied_counts.get
    )

    min_empty_square = min(
        empty_counts,
        key=empty_counts.get
    )

    max_empty_square = max(
        empty_counts,
        key=empty_counts.get
    )


    # ========================================================
    # REPORT FILE
    # ========================================================

    with open(
        REPORT_PATH,
        "w",
        encoding="utf-8"
    ) as f:


        f.write(
            "SELECTED FEN DATASET REPORT\n"
        )

        f.write(
            "=" * 60
            +
            "\n\n"
        )


        f.write(
            "Dataset policy:\n"
        )

        f.write(
            "- Standard Chess only\n"
        )

        f.write(
            "- Normal starting position only\n"
        )

        f.write(
            "- Broken PGN games excluded\n"
        )

        f.write(
            "- Chess960 / variants excluded\n"
        )

        f.write(
            "- Visual duplicate board layouts excluded\n"
        )

        f.write(
            "- Maximum one selected position per source game\n\n"
        )


        f.write(
            f"Total positions: "
            f"{len(selected)}\n\n"
        )


        # ====================================================
        # PHASE
        # ====================================================

        f.write(
            "Phase distribution:\n"
        )


        for phase in [
            "opening",
            "middlegame",
            "endgame",
        ]:

            f.write(
                f"  {phase:<12}: "
                f"{phase_counts[phase]}\n"
            )


        # ====================================================
        # SAMPLE TOTALS
        # ====================================================

        f.write(
            "\nSquare sample totals:\n"
        )

        f.write(
            f"  occupied: "
            f"{total_occupied}\n"
        )

        f.write(
            f"  empty   : "
            f"{total_empty}\n"
        )

        f.write(
            f"  total   : "
            f"{total_occupied + total_empty}\n"
        )


        f.write(
            "\nOccupied coverage range:\n"
        )

        f.write(
            f"  minimum: "
            f"{min_occupied_square} = "
            f"{occupied_counts[min_occupied_square]}\n"
        )

        f.write(
            f"  maximum: "
            f"{max_occupied_square} = "
            f"{occupied_counts[max_occupied_square]}\n"
        )


        f.write(
            "\nEmpty coverage range:\n"
        )

        f.write(
            f"  minimum: "
            f"{min_empty_square} = "
            f"{empty_counts[min_empty_square]}\n"
        )

        f.write(
            f"  maximum: "
            f"{max_empty_square} = "
            f"{empty_counts[max_empty_square]}\n"
        )


        # ====================================================
        # BOARD GRIDS
        # ====================================================

        write_square_grid(
            f,
            "Occupied count per square:",
            occupied_counts
        )

        write_square_grid(
            f,
            "Empty count per square:",
            empty_counts
        )


        # ====================================================
        # PIECE DISTINCT SQUARE COVERAGE
        # ====================================================

        f.write(
            "\nDistinct squares per piece class:\n"
        )


        for cls in sorted(
            piece_distinct_squares
        ):

            f.write(
                f"  {cls:<16}: "
                f"{piece_distinct_squares[cls]}\n"
            )


        # ====================================================
        # PIECE INSTANCE COUNTS
        # ====================================================

        f.write(
            "\nTotal piece observations:\n"
        )


        for cls in sorted(
            piece_observations
        ):

            f.write(
                f"  {cls:<16}: "
                f"{piece_observations[cls]}\n"
            )


        # ====================================================
        # SOURCE TRACE
        # ====================================================

        f.write(
            "\nSelected source games:\n"
        )


        for index, item in enumerate(
            selected,
            start=1
        ):

            f.write(
                f"{index:03d} | "
                f"{item['phase']:<10} | "
                f"{item['date']} | "
                f"{item['white']} vs "
                f"{item['black']} | "
                f"{item['event']}\n"
            )


    # ========================================================
    # TERMINAL SUMMARY
    # ========================================================

    print()

    print(
        "=========================================="
    )

    print(
        "FINAL DATASET SUMMARY"
    )

    print(
        "=========================================="
    )


    print(
        f"Positions : "
        f"{len(selected)}"
    )

    print(
        f"Opening   : "
        f"{phase_counts['opening']}"
    )

    print(
        f"Middlegame: "
        f"{phase_counts['middlegame']}"
    )

    print(
        f"Endgame   : "
        f"{phase_counts['endgame']}"
    )


    print()

    print(
        f"Occupied samples: "
        f"{total_occupied}"
    )

    print(
        f"Empty samples   : "
        f"{total_empty}"
    )


    print()

    print(
        "Occupied per-square range:"
    )

    print(
        f"  min "
        f"{min_occupied_square} = "
        f"{occupied_counts[min_occupied_square]}"
    )

    print(
        f"  max "
        f"{max_occupied_square} = "
        f"{occupied_counts[max_occupied_square]}"
    )


    print()

    print(
        "Distinct squares per piece class:"
    )


    for cls in sorted(
        piece_distinct_squares
    ):

        print(
            f"  {cls:<16}: "
            f"{piece_distinct_squares[cls]}"
        )


    print()

    print(
        "Saved:"
    )

    print(
        OUTPUT_PATH
    )

    print(
        REPORT_PATH
    )

    print(
        "=========================================="
    )


# ============================================================
# MAIN
# ============================================================

def main():

    if not PGN_PATH.exists():

        raise FileNotFoundError(
            "\nPGN not found:\n"
            f"{PGN_PATH}\n\n"
            "Rename your downloaded PGN to:\n"
            "data/source_games.pgn"
        )


    # ========================================================
    # CANDIDATE POOL
    # ========================================================

    candidates = (
        load_candidates()
    )


    if not candidates:

        raise RuntimeError(
            "No valid Standard Chess candidates found."
        )


    # ========================================================
    # SELECT 100
    # ========================================================

    (
        selected,
        feature_counts,
        phase_counts
    ) = select_positions(
        candidates
    )


    # ========================================================
    # VERIFY QUOTAS
    # ========================================================

    if len(selected) != TARGET_TOTAL:

        raise RuntimeError(
            f"Only selected "
            f"{len(selected)}/"
            f"{TARGET_TOTAL} positions.\n"
            "Increase MAX_GAMES."
        )


    for phase, required in (
        QUOTAS.items()
    ):

        actual = phase_counts[
            phase
        ]

        if actual != required:

            raise RuntimeError(
                f"Phase quota mismatch: "
                f"{phase} "
                f"{actual}/{required}"
            )


    # ========================================================
    # WRITE
    # ========================================================

    write_results(
        selected,
        feature_counts,
        phase_counts
    )


# ============================================================
# ENTRY
# ============================================================

if __name__ == "__main__":

    main()

    
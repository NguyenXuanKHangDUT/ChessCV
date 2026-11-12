"""ChessCV Game Review: Stockfish + public expected-points classification.

Based on Chess.com's published Classification V2 cutoffs, and Lichess's
published win-percentage / move-accuracy / game-accuracy mathematics.

This is NOT Chess.com's proprietary rating-dependent model or CAPS2.

A separate UCI engine is used.
Saved games and live bots are never modified.
"""

from __future__ import annotations

import math
import statistics
from pathlib import Path

import chess
import chess.engine

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.database.db import get_db
from backend.app.database.models.game import Game
from backend.app.database.models.move import Move


router = APIRouter(
    prefix="/games",
    tags=["Game Analysis"],
)


# ============================================================
# ANALYSIS CONFIGURATION
# ============================================================

MAX_ANALYSIS_PLIES = 400

BASE_SEARCH_SECONDS = 0.45

CRITICAL_SEARCH_SECONDS = 1.25


CATEGORIES = (
    "book",
    "brilliant",
    "great",
    "best",
    "excellent",
    "good",
    "inaccuracy",
    "mistake",
    "miss",
    "blunder",
)


PIECE_VALUES = {
    chess.PAWN: 100,
    chess.KNIGHT: 320,
    chess.BISHOP: 330,
    chess.ROOK: 500,
    chess.QUEEN: 900,
}


# ============================================================
# OPENING BOOK
# ============================================================

FALLBACK_BOOK_LINES = (
    "e4 e5 Nf3 Nc6 Bb5 a6 Ba4 Nf6 O-O Be7 Re1 b5 Bb3 O-O h3 Na5",
    "d4 Nf6 Nf3 d5 g3 e6 Bg2 Be7 O-O O-O b3 c5 dxc5 Bxc5",
    "e4 c5 Nf3 d6 d4 cxd4 Nxd4 Nf6 Nc3 a6",
    "e4 c6 d4 d5 Nc3 dxe4 Nxe4 Bf5",
    "e4 e6 d4 d5 Nc3 Nf6",
    "d4 d5 c4 e6 Nc3 Nf6 Bg5 Be7",
    "d4 Nf6 c4 g6 Nc3 Bg7 e4 d6",
    "e4 e5 Nf3 Nc6 Bc4 Bc5 c3 Nf6",
)


def _book_prefixes() -> set[tuple[str, ...]]:
    lines = [
        tuple(line.split())
        for line in FALLBACK_BOOK_LINES
    ]

    try:
        from Openix import ChessOpeningsLibrary

        library = ChessOpeningsLibrary()
        library.load_builtin_openings()

        lines.extend(
            tuple(
                str(move).replace("0-0", "O-O")
                for move in entry.moves_list
            )
            for entry in library.get_all_openings()
        )

    except Exception:
        # Optional library.
        # Unknown opening lines are not automatically Book.
        pass

    return {
        line[:count]
        for line in lines
        if line
        for count in range(
            1,
            min(len(line), 30) + 1,
        )
    }


# ============================================================
# MATHEMATICAL HELPERS
# ============================================================

def _clamp(
    value: float,
    lower: float,
    upper: float,
) -> float:
    return max(
        lower,
        min(upper, value),
    )


def _score_cp(
    score: chess.engine.PovScore,
    perspective: chess.Color,
) -> int:
    return int(
        score.pov(perspective).score(
            mate_score=100000
        ) or 0
    )


# ============================================================
# EXPECTED POINTS
#
# Public Lichess winning-percentage curve.
#
# Used here as a proxy for Chess.com's rating-dependent
# Expected Points model, whose parameters are not public.
#
# ============================================================

def _expected_points(
    score: chess.engine.PovScore,
    perspective: chess.Color,
) -> float:

    cp = _score_cp(
        score,
        perspective,
    )

    return 1.0 / (
        1.0
        +
        math.exp(
            -0.00368208
            *
            _clamp(cp, -3000, 3000)
        )
    )


# ============================================================
# MOVE ACCURACY
#
# Published Lichess exponential formula.
# Replaces the old 100 * exp(-3 * loss).
#
# ============================================================

def _move_accuracy(
    expected_loss: float,
) -> float:

    delta_percent = (
        100.0
        *
        _clamp(
            expected_loss,
            0.0,
            1.0,
        )
    )

    return _clamp(
        103.1668
        *
        math.exp(
            -0.04354 * delta_percent
        )
        -
        3.1669,
        0.0,
        100.0,
    )


def _display_evaluation(
    score: chess.engine.PovScore,
) -> tuple[int, int | None]:

    white = score.white()

    return (
        int(
            white.score(
                mate_score=100000
            ) or 0
        ),
        white.mate(),
    )


# ============================================================
# TERMINAL POSITIONS
# ============================================================

def _terminal_info(
    board: chess.Board,
) -> dict | None:

    outcome = board.outcome(
        claim_draw=False
    )

    if outcome is None:
        return None

    if outcome.winner is None:
        value = chess.engine.Cp(0)

    elif outcome.winner == chess.WHITE:
        value = chess.engine.Mate(1)

    else:
        value = chess.engine.Mate(-1)

    return {
        "score": chess.engine.PovScore(
            value,
            chess.WHITE,
        ),
        "pv": [],
    }


# ============================================================
# ROOT ENGINE ANALYSIS
#
# MultiPV=2 compares the best and second-best moves.
# ============================================================

def _root_lines(
    engine: chess.engine.SimpleEngine,
    board: chess.Board,
    seconds: float,
) -> list[dict]:

    terminal = _terminal_info(board)

    if terminal is not None:
        return [terminal]

    infos = engine.analyse(
        board,
        chess.engine.Limit(
            time=seconds
        ),
        multipv=min(
            2,
            board.legal_moves.count(),
        ),
    )

    return (
        infos
        if isinstance(infos, list)
        else [infos]
    )


# ============================================================
# EVALUATE THE ACTUAL PLAYED MOVE
#
# A move outside Stockfish's top two choices must still
# receive its own evaluation from the SAME root position.
#
# This avoids relying only on two shallow evaluations of
# different positions, which can produce misleading losses.
# ============================================================

def _played_line(
    engine: chess.engine.SimpleEngine,
    board: chess.Board,
    played: chess.Move,
    root_lines: list[dict],
    seconds: float,
) -> dict:

    for info in root_lines:
        pv = info.get("pv", [])

        if pv and pv[0] == played:
            return info

    return engine.analyse(
        board,
        chess.engine.Limit(
            time=seconds
        ),
        root_moves=[played],
    )


# ============================================================
# MATERIAL BALANCE
#
# Relative to the player who made the move.
# ============================================================

def _material_balance(
    board: chess.Board,
    perspective: chess.Color,
) -> int:

    balance = 0

    for piece in board.piece_map().values():

        amount = PIECE_VALUES.get(
            piece.piece_type,
            0,
        )

        balance += (
            amount
            if piece.color == perspective
            else -amount
        )

    return balance


# ============================================================
# REAL SACRIFICE DETECTION
#
# Important:
#
# - Capturing a free piece is NOT a sacrifice.
# - Equal trades are NOT sacrifices.
# - Merely placing a piece on an attacked square is NOT enough.
# - The opponent must accept the material offer in the PV.
# - The material investment must persist for several plies.
#
# Conservative false negatives are preferable to
# incorrectly awarding Brilliant moves.
# ============================================================

def _persistent_sacrifice(
    before: chess.Board,
    played: chess.Move,
    pv: list[chess.Move],
) -> bool:

    piece = before.piece_at(
        played.from_square
    )

    if (
        piece is None
        or piece.piece_type not in (
            chess.KNIGHT,
            chess.BISHOP,
            chess.ROOK,
            chess.QUEEN,
        )
    ):
        return False

    # Do not mistake escaping an already attacked piece
    # or responding to check for a voluntary sacrifice.

    if (
        before.is_check()
        or before.is_attacked_by(
            not before.turn,
            played.from_square,
        )
    ):
        return False

    if (
        len(pv) < 4
        or pv[0] != played
    ):
        return False

    perspective = before.turn

    initial = _material_balance(
        before,
        perspective,
    )

    continuation = before.copy(
        stack=False
    )

    differences: list[int] = []

    for reply in pv[:6]:

        if reply not in continuation.legal_moves:
            return False

        continuation.push(reply)

        differences.append(
            _material_balance(
                continuation,
                perspective,
            )
            -
            initial
        )

    # Material loss must exist after the opponent's reply,
    # and remain after the next continuation.
    #
    # 150cp includes a rook-for-minor exchange sacrifice,
    # but rules out most routine equal exchanges.

    return (
        len(differences) >= 4
        and differences[1] <= -150
        and differences[3] <= -150
    )


# ============================================================
# MOVE CLASSIFICATION
#
# Chess.com Classification V2 published thresholds:
#
# Excellent: loss < 0.02
# Good:      loss < 0.05
# Inaccuracy:loss < 0.10
# Mistake:   loss < 0.20
# Blunder:   loss >= 0.20
#
# Brilliant / Great / Miss require additional conditions.
# ============================================================

def _classify(
    *,
    is_book: bool,
    best_move: bool,
    loss: float,
    best_expected: float,
    actual_expected: float,
    second_expected: float | None,
    previous_loss: float,
    sacrifice: bool,
    endgame: bool,
) -> tuple[str, str]:

    if is_book:
        return (
            "book",
            "A move from a recognized opening-book sequence.",
        )

    second_gap = (
        best_expected - second_expected
        if second_expected is not None
        else 0.0
    )

    nearly_best = (
        best_move
        or loss <= 0.012
    )

    # ========================================================
    # BRILLIANT
    #
    # Must involve an actual persistent sacrifice.
    # Must be best or nearly best.
    # Position must remain competitive.
    # In the endgame, require extra uniqueness.
    # ========================================================

    if (
        sacrifice
        and nearly_best
        and actual_expected >= 0.28
        and best_expected <= 0.88
        and (
            not endgame
            or second_gap >= 0.05
        )
    ):
        return (
            "brilliant",
            "A strong, voluntary piece/exchange sacrifice: "
            "the engine's best defense accepts it and the "
            "material is not immediately recovered.",
        )

    # ========================================================
    # GREAT
    #
    # Find the critical engine-best move when the second-best
    # choice would lose substantial winning chances.
    # ========================================================

    if (
        best_move
        and second_expected is not None
        and second_gap >= 0.12
        and 0.26 <= best_expected <= 0.88
    ):
        return (
            "great",
            "A critical engine-best move; the second-best "
            "alternative would lose at least 12 percentage "
            "points of expected result.",
        )

    # ========================================================
    # MISS
    #
    # The opponent made a meaningful mistake.
    # You had a winning opportunity.
    # The played move allowed the position to return toward
    # equality or worse.
    # ========================================================

    if (
        not nearly_best
        and previous_loss >= 0.08
        and best_expected >= 0.75
        and actual_expected <= 0.55
        and loss >= 0.18
    ):
        return (
            "miss",
            "Missed a chance to punish the opponent's previous "
            "mistake and convert a winning position.",
        )

    # ========================================================
    # ORDINARY MOVE CLASSIFICATIONS
    # ========================================================

    if best_move:
        return (
            "best",
            "Stockfish's first choice from the analyzed position.",
        )

    if loss < 0.02:
        return (
            "excellent",
            "Loses less than 2 percentage points of expected result.",
        )

    if loss < 0.05:
        return (
            "good",
            "Loses 2–5 percentage points of expected result.",
        )

    if loss < 0.10:
        return (
            "inaccuracy",
            "Loses 5–10 percentage points of expected result.",
        )

    if loss < 0.20:
        return (
            "mistake",
            "Loses 10–20 percentage points of expected result.",
        )

    return (
        "blunder",
        "Loses at least 20 percentage points of expected result.",
    )


# ============================================================
# WHOLE-GAME ACCURACY
#
# Inspired by Lichess's published game accuracy methodology:
#
# 1. Calculate per-move accuracy.
# 2. Calculate position volatility using sliding windows.
# 3. Calculate volatility-weighted accuracy.
# 4. Calculate harmonic mean accuracy.
# 5. Average those two metrics.
#
# This replaces the previous arithmetic mean, which gave
# excessive weight to easy moves in long, decided positions.
# ============================================================

def _game_accuracy(
    reviewed: list[dict],
    win_percentages: list[float],
) -> dict[str, float | None]:

    n = len(reviewed)

    if n == 0:
        return {
            "white": None,
            "black": None,
        }

    size = max(
        2,
        min(8, n // 10),
    )

    values = win_percentages

    first_window = values[:size]

    windows = (
        [first_window] * (size - 2)
    )

    windows.extend(
        values[i:i + size]
        for i in range(
            len(values) - size + 1
        )
    )

    weights = [
        _clamp(
            statistics.pstdev(window),
            0.5,
            12.0,
        )
        for window in windows[:n]
    ]

    by_color: dict[str, float | None] = {}

    for color in ("white", "black"):

        pairs = [
            (
                float(move["accuracy"]),
                weights[i],
            )
            for i, move in enumerate(reviewed)
            if move["color"] == color
        ]

        if not pairs:
            by_color[color] = None
            continue

        weighted = (
            sum(
                accuracy * weight
                for accuracy, weight in pairs
            )
            /
            sum(
                weight
                for _, weight in pairs
            )
        )

        # Avoid division by zero for moves with 0% accuracy.
        # A catastrophic move still receives a heavy penalty.

        harmonic = (
            len(pairs)
            /
            sum(
                1.0 / max(1.0, acc)
                for acc, _ in pairs
            )
        )

        by_color[color] = round(
            _clamp(
                (weighted + harmonic) / 2.0,
                0.0,
                100.0,
            ),
            1,
        )

    return by_color


# ============================================================
# ADAPTIVE DEEP ANALYSIS
#
# Review critical positions at greater search time.
#
# Deeper search is triggered by:
# - Significant expected-points loss
# - Potential only-good-move decisions
# - Potential piece sacrifices
# - Engine mate sequences
# ============================================================

def _should_deepen(
    board: chess.Board,
    played: chess.Move,
    root_lines: list[dict],
    best_expected: float,
    played_expected: float,
) -> bool:

    best_info = root_lines[0]

    pv = best_info.get(
        "pv",
        [],
    )

    best = (
        pv[0]
        if pv
        else None
    )

    if (
        best_info["score"].white().mate()
        is not None
    ):
        return True

    if (
        best_expected - played_expected
        >= 0.045
    ):
        return True

    if len(root_lines) > 1:

        gap = (
            best_expected
            -
            _expected_points(
                root_lines[1]["score"],
                board.turn,
            )
        )

        if (
            0.27 <= best_expected <= 0.92
            and gap >= 0.07
        ):
            return True

    if best == played:

        piece = board.piece_at(
            played.from_square
        )

        if (
            piece
            and piece.piece_type in (
                chess.KNIGHT,
                chess.BISHOP,
                chess.ROOK,
                chess.QUEEN,
            )
        ):

            after = board.copy(
                stack=False
            )

            after.push(played)

            if after.is_attacked_by(
                not board.turn,
                played.to_square,
            ):
                return True

    return False


# ============================================================
# ANALYZE SAVED GAME
# ============================================================

@router.post("/{game_id}/analyze")
def analyze_saved_game(
    game_id: int,
    db: Session = Depends(get_db),
) -> dict:

    game = db.get(
        Game,
        game_id,
    )

    if game is None:
        raise HTTPException(
            status_code=404,
            detail="Game not found.",
        )

    saved_moves = db.scalars(
        select(Move)
        .where(Move.game_id == game_id)
        .order_by(Move.ply.asc())
    ).all()

    if not saved_moves:
        raise HTTPException(
            status_code=422,
            detail="This game has no saved moves to analyze.",
        )

    if len(saved_moves) > MAX_ANALYSIS_PLIES:
        raise HTTPException(
            status_code=422,
            detail=(
                "Game Review supports at most "
                f"{MAX_ANALYSIS_PLIES} half-moves."
            ),
        )

    # ========================================================
    # VALIDATE SAVED MOVES BEFORE ENGINE ANALYSIS
    # ========================================================

    try:

        verify = chess.Board(
            game.initial_fen
        )

        if not verify.is_valid():
            raise ValueError(
                "The saved initial FEN is invalid."
            )

        for index, item in enumerate(
            saved_moves,
            start=1,
        ):

            move = chess.Move.from_uci(
                item.uci
            )

            if move not in verify.legal_moves:
                raise ValueError(
                    f"Saved move {index} ({item.uci}) is illegal."
                )

            verify.push(move)

    except (
        ValueError,
        AssertionError,
    ) as error:

        raise HTTPException(
            status_code=422,
            detail=(
                "Saved game cannot be replayed: "
                f"{error}"
            ),
        ) from error

    # ========================================================
    # CHECK STOCKFISH
    # ========================================================

    engine_path = (
        Path(settings.STOCKFISH_PATH)
        .expanduser()
        .resolve()
    )

    if not engine_path.is_file():
        raise HTTPException(
            status_code=503,
            detail=(
                "Stockfish executable not found. "
                "Check STOCKFISH_PATH."
            ),
        )

    engine = None

    try:

        # Separate engine process.
        # Live bots 1800 and 2800 are unaffected.

        engine = (
            chess.engine.SimpleEngine.popen_uci(
                str(engine_path),
                timeout=20.0,
            )
        )

        options = {}

        if "Threads" in engine.options:
            options["Threads"] = 2

        if "Hash" in engine.options:
            options["Hash"] = 128

        if "UCI_LimitStrength" in engine.options:
            options["UCI_LimitStrength"] = False

        if options:
            engine.configure(options)

        # ====================================================
        # PREPARE GAME
        # ====================================================

        board = chess.Board(
            game.initial_fen
        )

        book = (
            _book_prefixes()
            if board.fen() == chess.STARTING_FEN
            else set()
        )

        san_prefix: list[str] = []

        reviewed: list[dict] = []

        counts = {
            color: {
                label: 0
                for label in CATEGORIES
            }
            for color in (
                "white",
                "black",
            )
        }

        # ====================================================
        # INITIAL EVALUATION
        # ====================================================

        initial_lines = _root_lines(
            engine,
            board,
            BASE_SEARCH_SECONDS,
        )

        initial_cp, initial_mate = (
            _display_evaluation(
                initial_lines[0]["score"]
            )
        )

        win_values = [
            _expected_points(
                initial_lines[0]["score"],
                chess.WHITE,
            ) * 100
        ]

        previous_loss = 0.0

        # ====================================================
        # ANALYZE EACH PLAYED MOVE
        # ====================================================

        for index, item in enumerate(
            saved_moves
        ):

            played = chess.Move.from_uci(
                item.uci
            )

            mover = (
                "white"
                if board.turn == chess.WHITE
                else "black"
            )

            perspective = board.turn

            played_san = board.san(
                played
            )

            san_prefix.append(
                played_san.replace(
                    "0-0",
                    "O-O",
                )
            )

            is_book = (
                tuple(san_prefix) in book
            )

            # =================================================
            # FIRST PASS: BEST / SECOND-BEST / PLAYED
            # =================================================

            root_lines = (
                initial_lines
                if index == 0
                else _root_lines(
                    engine,
                    board,
                    BASE_SEARCH_SECONDS,
                )
            )

            actual_line = _played_line(
                engine,
                board,
                played,
                root_lines,
                BASE_SEARCH_SECONDS,
            )

            best_expected = (
                _expected_points(
                    root_lines[0]["score"],
                    perspective,
                )
            )

            played_expected = (
                _expected_points(
                    actual_line["score"],
                    perspective,
                )
            )

            # =================================================
            # DEEPER PASS FOR CRITICAL POSITIONS
            # =================================================

            if (
                not is_book
                and _should_deepen(
                    board,
                    played,
                    root_lines,
                    best_expected,
                    played_expected,
                )
            ):

                root_lines = _root_lines(
                    engine,
                    board,
                    CRITICAL_SEARCH_SECONDS,
                )

                actual_line = _played_line(
                    engine,
                    board,
                    played,
                    root_lines,
                    CRITICAL_SEARCH_SECONDS,
                )

                best_expected = (
                    _expected_points(
                        root_lines[0]["score"],
                        perspective,
                    )
                )

                played_expected = (
                    _expected_points(
                        actual_line["score"],
                        perspective,
                    )
                )

            # =================================================
            # BEST MOVE / SECOND-BEST MOVE
            # =================================================

            pv = root_lines[0].get(
                "pv",
                [],
            )

            best_move = (
                pv[0]
                if (
                    pv
                    and pv[0] in board.legal_moves
                )
                else None
            )

            best_uci = (
                best_move.uci()
                if best_move
                else None
            )

            best_san = (
                board.san(best_move)
                if best_move
                else None
            )

            best_move_played = (
                best_move == played
            )

            loss = max(
                0.0,
                best_expected - played_expected,
            )

            # A restricted search can occasionally return a
            # higher evaluation than the initial MultiPV search.
            #
            # Do not treat such an evaluation difference as
            # a gain beyond the engine's first choice.

            played_expected = min(
                best_expected,
                played_expected,
            )

            second_expected = (
                _expected_points(
                    root_lines[1]["score"],
                    perspective,
                )
                if len(root_lines) > 1
                else None
            )

            # =================================================
            # ENDGAME DETECTION
            # =================================================

            nonpawn_pieces = sum(
                1
                for piece in board.piece_map().values()
                if piece.piece_type in (
                    chess.KNIGHT,
                    chess.BISHOP,
                    chess.ROOK,
                    chess.QUEEN,
                )
            )

            endgame = (
                nonpawn_pieces <= 6
            )

            # =================================================
            # VERIFY A TRUE, PERSISTENT SACRIFICE
            # =================================================

            sacrificed = (
                best_move_played
                and played_expected >= 0.28
                and best_expected <= 0.88
                and _persistent_sacrifice(
                    board,
                    played,
                    actual_line.get(
                        "pv",
                        [],
                    ),
                )
            )

            # =================================================
            # CLASSIFY
            # =================================================

            classification, reason = (
                _classify(
                    is_book=is_book,
                    best_move=best_move_played,
                    loss=loss,
                    best_expected=best_expected,
                    actual_expected=played_expected,
                    second_expected=second_expected,
                    previous_loss=previous_loss,
                    sacrifice=sacrificed,
                    endgame=endgame,
                )
            )

            # =================================================
            # EVALUATION / ACCURACY
            # =================================================

            cp, mate = (
                _display_evaluation(
                    actual_line["score"]
                )
            )

            accuracy = round(
                _move_accuracy(loss),
                1,
            )

            # =================================================
            # COMMIT TO LOCAL ANALYSIS BOARD ONLY
            #
            # This does not modify MySQL.
            # =================================================

            board.push(played)

            win_values.append(
                _expected_points(
                    actual_line["score"],
                    chess.WHITE,
                ) * 100
            )

            counts[mover][classification] += 1

            reviewed.append({
                "ply": item.ply,
                "move_number": item.move_number,
                "color": mover,
                "uci": item.uci,
                "san": item.san,
                "fen_after": board.fen(),
                "best_uci": best_uci,
                "best_san": best_san,
                "evaluation_cp": cp,
                "evaluation_mate": mate,
                "win_chance_loss": round(
                    loss,
                    4,
                ),
                "accuracy": accuracy,
                "classification": classification,
                "classification_reason": reason,
            })

            previous_loss = loss

        # ====================================================
        # WHOLE-GAME ACCURACY
        # ====================================================

        overall = _game_accuracy(
            reviewed,
            win_values,
        )

        return {
            "game_id": game_id,

            "engine": (
                "Stockfish "
                "(full strength, adaptive analysis)"
            ),

            "seconds_per_position": BASE_SEARCH_SECONDS,

            "method": (
                "Chess.com Classification V2 public "
                "expected-points thresholds; Lichess public "
                "win-probability and volatility/harmonic "
                "accuracy formula. Deep-checks critical moves "
                "and persistent sacrifices. Chess.com's "
                "private rating model and CAPS2 are not reproduced."
            ),

            "initial_evaluation_cp": initial_cp,

            "initial_evaluation_mate": initial_mate,

            "moves": reviewed,

            "summary": {
                color: {
                    "accuracy": overall[color],
                    "counts": counts[color],
                }
                for color in (
                    "white",
                    "black",
                )
            },
        }

    except (
        chess.engine.EngineError,
        OSError,
        TimeoutError,
        ValueError,
    ) as error:

        raise HTTPException(
            status_code=503,
            detail=(
                f"Stockfish analysis failed: {error}"
            ),
        ) from error

    finally:
        if engine is not None:
            try:
                engine.quit()
            except Exception:
                pass
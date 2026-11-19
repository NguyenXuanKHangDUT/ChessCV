from __future__ import annotations

from datetime import date

import chess
import chess.pgn


# ============================================================
# CONFIG
# ============================================================

MIN_EMPTY_PROBABILITY = 0.55
MIN_OCCUPIED_PROBABILITY = 0.55
MIN_PIECE_CONFIDENCE = 0.40
MAX_UNRELATED_MISMATCHES = 6

MIN_CASTLING_SQUARE_PROBABILITY = 0.60
MIN_CASTLING_AVERAGE_PROBABILITY = 0.70

MIN_ILLEGAL_SOURCE_EMPTY_PROBABILITY = 0.65
MIN_ILLEGAL_DEST_OCCUPIED_PROBABILITY = 0.65
MIN_ILLEGAL_PIECE_CONFIDENCE = 0.55
MAX_ILLEGAL_UNRELATED_MISMATCHES = 2
MIN_ILLEGAL_SCORE_GAP = 0.08


# ============================================================
# PIECE MAP
# ============================================================

PIECE_NAME_MAP = {
    chess.PAWN: "pawn",
    chess.KNIGHT: "knight",
    chess.BISHOP: "bishop",
    chess.ROOK: "rook",
    chess.QUEEN: "queen",
    chess.KING: "king",
}


# ============================================================
# HELPERS
# ============================================================

def chess_piece_to_class(piece: chess.Piece) -> str:
    color = "white" if piece.color == chess.WHITE else "black"
    name = PIECE_NAME_MAP[piece.piece_type]
    return f"{color}_{name}"


# ============================================================
# GAME TRACKER
# ============================================================

class GameTracker:

    def __init__(self):
        self.initialized = False
        self.board = chess.Board(None)
        self.game = chess.pgn.Game()
        self.node = self.game
        self.moves: list[dict] = []
        self.initial_fen: str | None = None

        self.reset_uninitialized()

    # ========================================================
    # BUILD BASIC PGN
    # ========================================================

    def _create_game(self):
        self.game = chess.pgn.Game()

        self.game.headers["Event"] = "PBL4 ChessCV Live"
        self.game.headers["Date"] = date.today().strftime("%Y.%m.%d")
        self.game.headers["Round"] = "?"
        self.game.headers["White"] = "White"
        self.game.headers["Black"] = "Black"
        self.game.headers["Result"] = "*"

        self.node = self.game

    # ========================================================
    # RESET - NO DEFAULT START POSITION
    # ========================================================

    def reset_uninitialized(self):
        self.initialized = False
        self.board = chess.Board(None)
        self._create_game()
        self.moves = []
        self.initial_fen = None

    # ========================================================
    # INITIALIZE FROM RECOGNIZED PHYSICAL BOARD
    # ========================================================

    def initialize_from_board_fen(
        self,
        board_fen: str,
        turn: str,
    ) -> dict:

        turn = turn.lower().strip()

        if turn not in ("w", "b"):
            return {
                "ok": False,
                "reason": "turn must be w or b",
            }

        try:
            standard = chess.Board()

            if board_fen == standard.board_fen():
                board = chess.Board()
                board.turn = (
                    chess.WHITE if turn == "w" else chess.BLACK
                )
            else:
                full_fen = f"{board_fen} {turn} - - 0 1"
                board = chess.Board(full_fen)

        except ValueError as error:
            return {
                "ok": False,
                "reason": str(error),
            }

        if not board.is_valid():
            return {
                "ok": False,
                "reason": (
                    "recognized board is not a valid chess position"
                ),
                "board_status": int(board.status()),
            }

        self.board = board
        self.initialized = True
        self.initial_fen = board.fen()
        self.moves = []

        self._create_game()

        if board.fen() != chess.STARTING_FEN:
            self.game.headers["SetUp"] = "1"
            self.game.headers["FEN"] = board.fen()

        print()
        print("==========================================")
        print("LIVE INITIAL POSITION ACCEPTED")
        print("==========================================")
        print(f"FEN: {board.fen()}")
        print("==========================================")
        print()

        return {
            "ok": True,
            "fen": board.fen(),
            "board_fen": board.board_fen(),
        }

    # ========================================================
    # CURRENT POSITION CHECK
    # ========================================================

    def evaluate_current_position_from_vision(
        self,
        square_predictions: dict[str, dict],
    ) -> dict:

        if not self.initialized:
            return {
                "matches_current": False,
                "occupancy_mismatches": [],
                "piece_mismatches": [],
                "occupancy_mismatch_count": 0,
                "piece_mismatch_count": 0,
            }

        occupancy_mismatches = []
        piece_mismatches = []

        for square in chess.SQUARES:
            square_name = chess.square_name(square)
            prediction = square_predictions.get(square_name)

            if prediction is None:
                continue

            expected_piece = self.board.piece_at(square)
            occupied = bool(prediction["occupied"])

            if expected_piece is None:
                if occupied:
                    occupancy_mismatches.append(square_name)
                continue

            if not occupied:
                occupancy_mismatches.append(square_name)
                continue

            predicted_class = prediction.get("piece")
            confidence = float(
                prediction.get("piece_confidence") or 0.0
            )

            expected_class = chess_piece_to_class(
                expected_piece
            )

            if (
                predicted_class is not None
                and predicted_class != expected_class
                and confidence >= 0.80
            ):
                piece_mismatches.append({
                    "square": square_name,
                    "expected": expected_class,
                    "predicted": predicted_class,
                    "confidence": confidence,
                })

        return {
            "matches_current": len(occupancy_mismatches) == 0,
            "occupancy_mismatches": occupancy_mismatches,
            "piece_mismatches": piece_mismatches,
            "occupancy_mismatch_count": len(
                occupancy_mismatches
            ),
            "piece_mismatch_count": len(
                piece_mismatches
            ),
        }

    # ========================================================
    # CHANGED SQUARES
    # ========================================================

    def _get_changed_squares(
        self,
        before: chess.Board,
        after: chess.Board,
    ) -> set[chess.Square]:

        changed = set()

        for square in chess.SQUARES:
            if (
                before.piece_at(square)
                != after.piece_at(square)
            ):
                changed.add(square)

        return changed

    # ========================================================
    # SCORE ONE SQUARE
    # ========================================================

    def _score_square(
        self,
        prediction: dict,
        expected_piece: chess.Piece | None,
    ) -> tuple[float, bool]:

        if expected_piece is None:
            probability = float(
                prediction["empty_probability"]
            )

            return (
                probability,
                probability >= MIN_EMPTY_PROBABILITY,
            )

        occupied_probability = float(
            prediction["occupied_probability"]
        )

        if occupied_probability < MIN_OCCUPIED_PROBABILITY:
            return occupied_probability, False

        expected_class = chess_piece_to_class(
            expected_piece
        )

        predicted_class = prediction.get("piece")

        confidence = float(
            prediction.get("piece_confidence") or 0.0
        )

        correct = predicted_class == expected_class

        if correct:
            score = occupied_probability * confidence
        else:
            score = (
                occupied_probability
                * max(0.0, 1.0 - confidence)
                * 0.10
            )

        return (
            score,
            correct and confidence >= MIN_PIECE_CONFIDENCE,
        )

    # ========================================================
    # STRONG UNRELATED ERROR
    # ========================================================

    def _strong_mismatch(
        self,
        prediction: dict,
        expected_piece: chess.Piece | None,
    ) -> bool:

        if expected_piece is None:
            return (
                float(prediction["occupied_probability"])
                >= 0.92
            )

        if float(prediction["empty_probability"]) >= 0.92:
            return True

        predicted_class = prediction.get("piece")

        confidence = float(
            prediction.get("piece_confidence") or 0.0
        )

        expected_class = chess_piece_to_class(
            expected_piece
        )

        return (
            predicted_class is not None
            and predicted_class != expected_class
            and confidence >= 0.94
        )

    # ========================================================
    # SCORE LEGAL MOVE
    # ========================================================

    def _score_move(
        self,
        move: chess.Move,
        square_predictions: dict[str, dict],
    ) -> dict:

        after = self.board.copy(stack=False)
        after.push(move)

        changed = self._get_changed_squares(
            self.board,
            after,
        )

        scores = []
        changed_valid = True

        for square in changed:
            name = chess.square_name(square)
            prediction = square_predictions.get(name)

            if prediction is None:
                changed_valid = False
                scores.append(0.0)
                continue

            score, valid = self._score_square(
                prediction,
                after.piece_at(square),
            )

            scores.append(score)

            if not valid:
                changed_valid = False

        unrelated = 0

        for square in chess.SQUARES:
            if square in changed:
                continue

            name = chess.square_name(square)
            prediction = square_predictions.get(name)

            if prediction is None:
                continue

            if self._strong_mismatch(
                prediction,
                after.piece_at(square),
            ):
                unrelated += 1

        score = (
            sum(scores) / len(scores)
            if scores else 0.0
        )

        return {
            "move": move,
            "uci": move.uci(),
            "score": float(score),
            "valid": (
                changed_valid
                and unrelated <= MAX_UNRELATED_MISMATCHES
            ),
            "changed_squares": [
                chess.square_name(square)
                for square in changed
            ],
            "unrelated_mismatches": unrelated,
        }

    # ========================================================
    # SCORE CASTLING FROM OCCUPANCY
    # ========================================================

    def _score_castling_move(
        self,
        move: chess.Move,
        square_predictions: dict[str, dict],
    ) -> dict:

        after = self.board.copy(stack=False)
        after.push(move)

        changed = self._get_changed_squares(
            self.board,
            after,
        )

        changed_names = [
            chess.square_name(square)
            for square in sorted(changed)
        ]

        if len(changed) != 4:
            return {
                "move": move,
                "uci": move.uci(),
                "score": 0.0,
                "valid": False,
                "changed_squares": changed_names,
                "unrelated_mismatches": 0,
            }

        probabilities = []
        empty_count = 0
        occupied_count = 0

        for square in changed:
            name = chess.square_name(square)

            prediction = square_predictions.get(name)

            if prediction is None:
                break

            expected_piece = after.piece_at(square)

            if expected_piece is None:
                empty_count += 1

                probability = float(
                    prediction.get(
                        "empty_probability",
                        0.0,
                    )
                )

            else:
                occupied_count += 1

                probability = float(
                    prediction.get(
                        "occupied_probability",
                        0.0,
                    )
                )

            probabilities.append(probability)

        else:
            if empty_count == 2 and occupied_count == 2:
                minimum = min(probabilities)

                average = (
                    sum(probabilities)
                    / len(probabilities)
                )

                if (
                    minimum >= MIN_CASTLING_SQUARE_PROBABILITY
                    and average >= MIN_CASTLING_AVERAGE_PROBABILITY
                ):
                    unrelated = 0

                    for square in chess.SQUARES:
                        if square in changed:
                            continue

                        prediction = square_predictions.get(
                            chess.square_name(square)
                        )

                        if prediction is None:
                            continue

                        if self._strong_mismatch(
                            prediction,
                            after.piece_at(square),
                        ):
                            unrelated += 1

                    return {
                        "move": move,
                        "uci": move.uci(),
                        "score": float(average),
                        "valid": (
                            unrelated
                            <= MAX_UNRELATED_MISMATCHES
                        ),
                        "changed_squares": changed_names,
                        "unrelated_mismatches": unrelated,
                    }

        return {
            "move": move,
            "uci": move.uci(),
            "score": (
                sum(probabilities) / len(probabilities)
                if probabilities else 0.0
            ),
            "valid": False,
            "changed_squares": changed_names,
            "unrelated_mismatches": 0,
        }

    # ========================================================
    # SCORE ILLEGAL PHYSICAL MOVE
    # ========================================================

    def _score_illegal_move_candidate(
        self,
        move: chess.Move,
        square_predictions: dict[str, dict],
    ) -> dict | None:

        source_piece = self.board.piece_at(move.from_square)

        if source_piece is None:
            return None

        if move in self.board.legal_moves:
            return None

        source_name = chess.square_name(move.from_square)
        destination_name = chess.square_name(move.to_square)

        source_prediction = square_predictions.get(source_name)
        destination_prediction = square_predictions.get(destination_name)
        is_castling = self.board.is_castling(move)

        if (
            source_prediction is None
            or destination_prediction is None
        ):
            return None

        source_empty_probability = float(
            source_prediction.get("empty_probability", 0.0)
        )

        destination_occupied_probability = float(
            destination_prediction.get("occupied_probability", 0.0)
        )

        destination_piece_confidence = float(
            destination_prediction.get("piece_confidence") or 0.0
        )

        if (
            source_empty_probability
            < MIN_ILLEGAL_SOURCE_EMPTY_PROBABILITY
        ):
            return None

        if (
            destination_occupied_probability
            < MIN_ILLEGAL_DEST_OCCUPIED_PROBABILITY
        ):
            return None

        if (
            not is_castling
            and destination_piece_confidence < MIN_ILLEGAL_PIECE_CONFIDENCE
        ):
            return None

        after = self.board.copy(stack=False)
        en_passant_attempt = False

        try:
            after.push(move)
        except (ValueError, AssertionError):
            return None

        # Handle a physically attempted en-passant capture even
        # when the game state does not contain an en-passant right.

        if (
            source_piece.piece_type == chess.PAWN
            and self.board.piece_at(move.to_square) is None
            and chess.square_file(move.from_square)
            != chess.square_file(move.to_square)
        ):
            captured_square = (
                move.to_square - 8
                if source_piece.color == chess.WHITE
                else move.to_square + 8
            )

            if 0 <= captured_square < 64:
                captured_piece = self.board.piece_at(captured_square)
                captured_prediction = square_predictions.get(
                    chess.square_name(captured_square)
                )

                if (
                    captured_piece is not None
                    and captured_piece.color != source_piece.color
                    and captured_prediction is not None
                    and float(
                        captured_prediction.get("empty_probability", 0.0)
                    ) >= MIN_ILLEGAL_SOURCE_EMPTY_PROBABILITY
                ):
                    after.remove_piece_at(captured_square)
                    en_passant_attempt = not self.board.is_en_passant(move)

        expected_destination_piece = after.piece_at(move.to_square)

        if expected_destination_piece is None:
            return None

        expected_destination_class = chess_piece_to_class(
            expected_destination_piece
        )

        if (
            not is_castling
            and destination_prediction.get("piece")
            != expected_destination_class
        ):
            return None

        changed = self._get_changed_squares(
            self.board,
            after,
        )

        if (
            move.from_square not in changed
            or move.to_square not in changed
            or len(changed) not in (2, 3, 4)
        ):
            return None

        scores = []

        for square in changed:
            prediction = square_predictions.get(
                chess.square_name(square)
            )

            if prediction is None:
                return None

            expected_piece = after.piece_at(square)

            if is_castling:
                if expected_piece is None:
                    score = float(
                        prediction.get("empty_probability", 0.0)
                    )
                else:
                    score = float(
                        prediction.get("occupied_probability", 0.0)
                    )

                valid = score >= MIN_CASTLING_SQUARE_PROBABILITY

            else:
                score, valid = self._score_square(
                    prediction,
                    expected_piece,
                )

            if not valid:
                return None

            scores.append(score)

        unrelated = 0

        for square in chess.SQUARES:
            if square in changed:
                continue

            prediction = square_predictions.get(
                chess.square_name(square)
            )

            if prediction is None:
                continue

            if self._strong_mismatch(
                prediction,
                after.piece_at(square),
            ):
                unrelated += 1

        if unrelated > MAX_ILLEGAL_UNRELATED_MISMATCHES:
            return None

        move_kind = "move"
        promotion_piece = None

        if move.promotion is not None:
            move_kind = "promotion"
            promotion_piece = chess.piece_name(move.promotion)

        elif self.board.is_castling(move):
            move_kind = "castling"

        elif self.board.is_en_passant(move):
            move_kind = "en_passant"

        elif en_passant_attempt:
            move_kind = "en_passant_attempt"

        elif (
            source_piece.piece_type == chess.PAWN
            and chess.square_rank(move.to_square)
            in (0, 7)
        ):
            move_kind = "promotion_required"

        elif self.board.piece_at(move.to_square) is not None:
            move_kind = "capture"

        score = (
            sum(scores) / len(scores)
            if scores
            else 0.0
        )

        return {
            "move": move,
            "uci": move.uci(),
            "from_square": source_name,
            "to_square": destination_name,
            "color": (
                "white"
                if source_piece.color == chess.WHITE
                else "black"
            ),
            "piece_type": chess.piece_name(source_piece.piece_type),
            "move_kind": move_kind,
            "promotion_piece": promotion_piece,
            "score": float(score),
            "changed_squares": [
                chess.square_name(square)
                for square in sorted(changed)
            ],
            "unrelated_mismatches": unrelated,
        }

    # ========================================================
    # RESOLVE ILLEGAL MOVE FROM VISION
    # ========================================================

    def resolve_illegal_move_from_vision(
        self,
        square_predictions: dict[str, dict],
    ) -> dict:

        if not self.initialized:
            return {
                "reason": "game_not_initialized",
                "illegal_move": None,
            }

        candidates = []
        legal_moves = set(self.board.legal_moves)

        for from_square in chess.SQUARES:
            source_piece = self.board.piece_at(from_square)

            if source_piece is None:
                continue

            source_prediction = square_predictions.get(
                chess.square_name(from_square)
            )

            if source_prediction is None:
                continue

            if float(
                source_prediction.get("empty_probability", 0.0)
            ) < MIN_ILLEGAL_SOURCE_EMPTY_PROBABILITY:
                continue

            expected_class = chess_piece_to_class(source_piece)

            for to_square in chess.SQUARES:
                if to_square == from_square:
                    continue

                destination_prediction = square_predictions.get(
                    chess.square_name(to_square)
                )

                if destination_prediction is None:
                    continue

                if float(
                    destination_prediction.get(
                        "occupied_probability",
                        0.0,
                    )
                ) < MIN_ILLEGAL_DEST_OCCUPIED_PROBABILITY:
                    continue

                predicted_class = destination_prediction.get("piece")
                promotion = None

                is_castling_candidate = (
                    source_piece.piece_type == chess.KING
                    and chess.square_rank(from_square)
                    == chess.square_rank(to_square)
                    and abs(
                        chess.square_file(from_square)
                        - chess.square_file(to_square)
                    ) == 2
                )

                if (
                    predicted_class != expected_class
                    and not is_castling_candidate
                ):
                    is_promotion_square = (
                        source_piece.piece_type == chess.PAWN
                        and chess.square_rank(to_square)
                        in (0, 7)
                    )

                    if not is_promotion_square:
                        continue

                    promoted_piece = None

                    for piece_type, piece_name in PIECE_NAME_MAP.items():
                        if piece_type in (
                            chess.QUEEN,
                            chess.ROOK,
                            chess.BISHOP,
                            chess.KNIGHT,
                        ) and predicted_class == (
                            "white_" if source_piece.color == chess.WHITE else "black_"
                        ) + piece_name:
                            promoted_piece = piece_type
                            break

                    if promoted_piece is None:
                        continue

                    promotion = promoted_piece

                move = chess.Move(
                    from_square,
                    to_square,
                    promotion=promotion,
                )

                if move in legal_moves:
                    continue

                result = self._score_illegal_move_candidate(
                    move,
                    square_predictions,
                )

                if result is not None:
                    candidates.append(result)

                elif (
                    source_piece.piece_type == chess.PAWN
                    and chess.square_rank(to_square) in (0, 7)
                    and predicted_class == expected_class
                ):
                    pending_promotion = chess.Move(
                        from_square,
                        to_square,
                    )

                    if pending_promotion not in legal_moves:
                        pending_result = self._score_illegal_move_candidate(
                            pending_promotion,
                            square_predictions,
                        )

                        if pending_result is not None:
                            candidates.append(pending_result)

        if not candidates:
            return {
                "reason": "no_illegal_candidate",
                "illegal_move": None,
                "candidate_count": 0,
            }

        candidates.sort(
            key=lambda item: item["score"],
            reverse=True,
        )

        best = candidates[0]
        second_score = (
            candidates[1]["score"]
            if len(candidates) > 1
            else None
        )

        if (
            second_score is not None
            and best["score"] - second_score < MIN_ILLEGAL_SCORE_GAP
        ):
            return {
                "reason": "ambiguous_illegal_move",
                "illegal_move": None,
                "candidate_count": len(candidates),
                "best_score": best["score"],
                "second_score": second_score,
            }

        illegal_move = {
            key: value
            for key, value in best.items()
            if key != "move"
        }

        return {
            "reason": "illegal_move_detected",
            "illegal_move": illegal_move,
            "candidate_count": len(candidates),
            "best_score": best["score"],
            "second_score": second_score,
        }

    # ========================================================
    # RESOLVE LEGAL MOVE
    # ========================================================

    def resolve_move_from_vision(
        self,
        square_predictions: dict[str, dict],
    ) -> dict:

        if not self.initialized:
            return {
                "move": None,
                "reason": "game_not_initialized",
            }

        # ====================================================
        # RESOLVE CASTLING FIRST
        # ====================================================

        for move in self.board.legal_moves:
            if not self.board.is_castling(move):
                continue

            castling = self._score_castling_move(
                move,
                square_predictions,
            )

            if castling["valid"]:
                return {
                    "move": move,
                    "reason": "matched",
                    "candidate_count": 1,
                    "best_score": castling["score"],
                    "second_score": None,
                    "changed_squares": castling[
                        "changed_squares"
                    ],
                    "unrelated_mismatches": castling[
                        "unrelated_mismatches"
                    ],
                }

        candidates = []

        for move in self.board.legal_moves:
            result = self._score_move(
                move,
                square_predictions,
            )

            if result["valid"]:
                candidates.append(result)

        if not candidates:
            illegal_resolution = self.resolve_illegal_move_from_vision(
                square_predictions
            )

            if illegal_resolution.get("illegal_move") is not None:
                return {
                    "move": None,
                    "reason": "illegal_move_detected",
                    "candidate_count": 0,
                    "illegal_move": illegal_resolution["illegal_move"],
                    "illegal_candidate_count": illegal_resolution.get(
                        "candidate_count",
                        0,
                    ),
                    "best_score": illegal_resolution.get("best_score"),
                    "second_score": illegal_resolution.get("second_score"),
                }

            return {
                "move": None,
                "reason": illegal_resolution.get(
                    "reason",
                    "no_legal_candidate",
                ),
                "candidate_count": 0,
                "illegal_candidate_count": illegal_resolution.get(
                    "candidate_count",
                    0,
                ),
            }

        candidates.sort(
            key=lambda item: item["score"],
            reverse=True,
        )

        best = candidates[0]

        second_score = (
            candidates[1]["score"]
            if len(candidates) > 1
            else None
        )

        if (
            second_score is not None
            and (
                best["score"] - second_score
            ) < 0.06
        ):
            return {
                "move": None,
                "reason": "ambiguous",
                "candidate_count": len(candidates),
                "best_uci": best["uci"],
                "best_score": best["score"],
                "second_score": second_score,
            }

        return {
            "move": best["move"],
            "reason": "matched",
            "candidate_count": len(candidates),
            "best_score": best["score"],
            "second_score": second_score,
            "changed_squares": best["changed_squares"],
            "unrelated_mismatches": best[
                "unrelated_mismatches"
            ],
        }

    # ========================================================
    # COMMIT
    # ========================================================

    def commit_move(
        self,
        move: chess.Move,
    ) -> dict:

        fen_before = self.board.fen()

        san = self.board.san(move)
        uci = move.uci()

        color = (
            "white"
            if self.board.turn
            else "black"
        )

        move_number = self.board.fullmove_number

        self.node = self.node.add_variation(move)
        self.board.push(move)

        record = {
            "ply": len(self.moves) + 1,
            "move_number": move_number,
            "color": color,
            "uci": uci,
            "san": san,
            "fen_before": fen_before,
            "fen_after": self.board.fen(),
        }

        self.moves.append(record)

        if self.board.is_game_over(claim_draw=True):
            self.game.headers["Result"] = (
                self.board.result(claim_draw=True)
            )

        print()
        print("==========================================")
        print("LIVE MOVE COMMITTED")
        print("==========================================")
        print(f"SAN: {san}")
        print(f"UCI: {uci}")
        print(f"FEN: {self.board.fen()}")
        print("==========================================")
        print()

        return record

    # ========================================================
    # PGN
    # ========================================================

    def get_pgn(self) -> str:
        exporter = chess.pgn.StringExporter(
            headers=True,
            variations=False,
            comments=False,
        )

        return self.game.accept(exporter)

    # ========================================================
    # STATE
    # ========================================================

    def get_state(self) -> dict:
        game_over = (
            self.initialized
            and self.board.is_game_over(
                claim_draw=True
            )
        )

        return {
            "initialized": self.initialized,
            "initial_fen": self.initial_fen,
            "board_fen": self.board.board_fen(),
            "fen": self.board.fen(),
            "turn": (
                "white"
                if self.board.turn
                else "black"
            ),
            "last_move": (
                self.moves[-1]
                if self.moves
                else None
            ),
            "moves": list(self.moves),
            "pgn": self.get_pgn(),
            "game_over": bool(game_over),
            "result": (
                self.board.result(claim_draw=True)
                if game_over
                else "*"
            ),
        }
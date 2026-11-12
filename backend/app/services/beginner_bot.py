from __future__ import annotations

import math
import random

import chess


PIECE_VALUES = {
    chess.PAWN: 100,
    chess.KNIGHT: 320,
    chess.BISHOP: 330,
    chess.ROOK: 500,
    chess.QUEEN: 900,
    chess.KING: 0,
}


CENTER_SQUARES = {
    chess.D4,
    chess.E4,
    chess.D5,
    chess.E5,
}


EXTENDED_CENTER = {
    chess.C3,
    chess.D3,
    chess.E3,
    chess.F3,
    chess.C4,
    chess.F4,
    chess.C5,
    chess.F5,
    chess.C6,
    chess.D6,
    chess.E6,
    chess.F6,
}


class BeginnerBot:

    def __init__(
        self,
        estimated_rating: int = 800,
        random_seed: int | None = None,
    ):

        self.estimated_rating = (
            estimated_rating
        )

        self.random = (
            random.Random(
                random_seed
            )
        )


    # ========================================================
    # MATERIAL
    # ========================================================

    def _material_score(
        self,
        board: chess.Board,
        perspective: chess.Color,
    ) -> float:

        score = 0.0


        for (
            piece_type,
            value,
        ) in PIECE_VALUES.items():

            own_count = len(
                board.pieces(
                    piece_type,
                    perspective,
                )
            )


            enemy_count = len(
                board.pieces(
                    piece_type,
                    not perspective,
                )
            )


            score += (
                own_count
                -
                enemy_count
            ) * value


        return score


    # ========================================================
    # POSITIONAL
    # ========================================================

    def _positional_score(
        self,
        board: chess.Board,
        perspective: chess.Color,
    ) -> float:

        score = 0.0


        # ====================================================
        # CENTER
        # ====================================================

        for square in CENTER_SQUARES:

            piece = (
                board.piece_at(
                    square
                )
            )


            if piece is None:
                continue


            if (
                piece.color
                ==
                perspective
            ):

                score += 18.0

            else:

                score -= 18.0


        # ====================================================
        # EXTENDED CENTER
        # ====================================================

        for square in EXTENDED_CENTER:

            piece = (
                board.piece_at(
                    square
                )
            )


            if piece is None:
                continue


            if (
                piece.color
                ==
                perspective
            ):

                score += 5.0

            else:

                score -= 5.0


        # ====================================================
        # MOBILITY
        # ====================================================

        own_board = (
            board.copy(
                stack=False
            )
        )


        own_board.turn = (
            perspective
        )


        own_mobility = (
            own_board
            .legal_moves
            .count()
        )


        enemy_board = (
            board.copy(
                stack=False
            )
        )


        enemy_board.turn = (
            not perspective
        )


        enemy_mobility = (
            enemy_board
            .legal_moves
            .count()
        )


        score += (
            own_mobility
            -
            enemy_mobility
        ) * 1.5


        return score


    # ========================================================
    # BOARD EVALUATION
    # ========================================================

    def _evaluate_board(
        self,
        board: chess.Board,
        perspective: chess.Color,
    ) -> float:

        if board.is_checkmate():

            if (
                board.turn
                ==
                perspective
            ):

                return -100000.0


            return 100000.0


        if (
            board.is_stalemate()
            or
            board.is_insufficient_material()
        ):

            return 0.0


        score = (
            self._material_score(
                board,
                perspective,
            )
        )


        score += (
            self._positional_score(
                board,
                perspective,
            )
        )


        return score


    # ========================================================
    # SCORE MOVE
    # ========================================================

    def _score_move(
        self,
        board: chess.Board,
        move: chess.Move,
    ) -> float:

        perspective = (
            board.turn
        )


        moving_piece = (
            board.piece_at(
                move.from_square
            )
        )


        captured_piece = (
            board.piece_at(
                move.to_square
            )
        )


        score = 0.0


        # ====================================================
        # CAPTURE
        # ====================================================

        if captured_piece is not None:

            score += (
                PIECE_VALUES[
                    captured_piece.piece_type
                ]
                *
                0.90
            )


            if moving_piece is not None:

                score -= (
                    PIECE_VALUES[
                        moving_piece.piece_type
                    ]
                    *
                    0.10
                )


        # ====================================================
        # PROMOTION
        # ====================================================

        if (
            move.promotion
            is not None
        ):

            score += (
                PIECE_VALUES.get(
                    move.promotion,
                    0,
                )
                *
                0.80
            )


        # ====================================================
        # DEVELOPMENT
        # ====================================================

        if moving_piece is not None:

            if (
                moving_piece.piece_type
                in (
                    chess.KNIGHT,
                    chess.BISHOP,
                )
            ):

                if (
                    move.from_square
                    in (
                        chess.B1,
                        chess.G1,
                        chess.C1,
                        chess.F1,

                        chess.B8,
                        chess.G8,
                        chess.C8,
                        chess.F8,
                    )
                ):

                    score += 24.0


            if (
                move.to_square
                in
                CENTER_SQUARES
            ):

                score += 20.0


            elif (
                move.to_square
                in
                EXTENDED_CENTER
            ):

                score += 7.0


        # ====================================================
        # CASTLING
        # ====================================================

        if board.is_castling(
            move
        ):

            score += 35.0


        # ====================================================
        # PLAY MOVE
        # ====================================================

        next_board = (
            board.copy(
                stack=False
            )
        )


        next_board.push(
            move
        )


        # ====================================================
        # CHECKMATE
        # ====================================================

        if next_board.is_checkmate():

            return 100000.0


        # ====================================================
        # CHECK
        # ====================================================

        if next_board.is_check():

            score += 35.0


        # ====================================================
        # STATIC POSITION
        # ====================================================

        score += (
            self._evaluate_board(
                next_board,
                perspective,
            )
        )


        # ====================================================
        # SIMPLE HANGING PIECE AWARENESS
        # ====================================================

        moved_piece_after = (
            next_board.piece_at(
                move.to_square
            )
        )


        if (
            moved_piece_after
            is not None
        ):

            attacked = (
                next_board.is_attacked_by(
                    not perspective,
                    move.to_square,
                )
            )


            defended = (
                next_board.is_attacked_by(
                    perspective,
                    move.to_square,
                )
            )


            if attacked:

                value = (
                    PIECE_VALUES[
                        moved_piece_after
                        .piece_type
                    ]
                )


                if defended:

                    score -= (
                        value
                        *
                        0.30
                    )

                else:

                    score -= (
                        value
                        *
                        0.55
                    )


        return score


    # ========================================================
    # WEAK MOVE SELECTION
    # ========================================================

    def _weighted_choice(
        self,
        scored_moves: list[
            tuple[
                chess.Move,
                float,
            ]
        ],
    ) -> chess.Move:

        scored_moves.sort(
            key=lambda item:
                item[1],

            reverse=True,
        )


        legal_count = len(
            scored_moves
        )


        if legal_count == 1:

            return (
                scored_moves[
                    0
                ][
                    0
                ]
            )


        # ====================================================
        # BEGINNER BLUNDER
        # ====================================================
        #
        # Roughly 12%:
        #
        # play any legal move.
        #
        # ====================================================

        if (
            self.random.random()
            <
            0.12
        ):

            return (
                self.random
                .choice(
                    scored_moves
                )[
                    0
                ]
            )


        # ====================================================
        # DELIBERATELY AVOID BEST MOVE
        # ====================================================

        if (
            self.random.random()
            <
            0.28
        ):

            pool = (
                scored_moves[
                    1:
                    min(
                        8,
                        legal_count,
                    )
                ]
            )


            if pool:

                return (
                    self.random
                    .choice(
                        pool
                    )[
                        0
                    ]
                )


        # ====================================================
        # NORMAL BEGINNER CHOICE
        # ====================================================

        top_moves = (
            scored_moves[
                :
                min(
                    5,
                    legal_count,
                )
            ]
        )


        best_score = (
            top_moves[
                0
            ][
                1
            ]
        )


        weights = []


        for (
            _,
            score,
        ) in top_moves:

            loss = max(
                0.0,
                best_score
                -
                score,
            )


            weight = math.exp(
                -loss
                /
                150.0
            )


            weights.append(
                max(
                    0.05,
                    weight,
                )
            )


        selected = (
            self.random.choices(
                population=[
                    move

                    for (
                        move,
                        _,
                    )
                    in top_moves
                ],

                weights=
                    weights,

                k=
                    1,
            )[
                0
            ]
        )


        return selected


    # ========================================================
    # PUBLIC
    # ========================================================

    def choose_move(
        self,
        board: chess.Board,
    ) -> dict:

        if board.is_game_over(
            claim_draw=True
        ):

            raise ValueError(
                "Cannot choose a bot move: "
                "game is already over."
            )


        legal_moves = list(
            board.legal_moves
        )


        if not legal_moves:

            raise ValueError(
                "No legal moves available."
            )


        scored_moves = [
            (
                move,
                self._score_move(
                    board,
                    move,
                ),
            )

            for move
            in legal_moves
        ]


        selected_move = (
            self._weighted_choice(
                scored_moves
            )
        )


        # ====================================================
        # SAN BEFORE PUSH
        # ====================================================

        san = (
            board.san(
                selected_move
            )
        )


        return {
            "move":
                selected_move,

            "uci":
                selected_move.uci(),

            "san":
                san,

            "estimated_rating":
                self.estimated_rating,

            "name":
                "Beginner Bot",
        }


# ============================================================
# SINGLETON
# ============================================================

beginner_bot = (
    BeginnerBot()
)
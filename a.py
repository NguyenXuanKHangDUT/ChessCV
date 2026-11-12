"""Import two FIDE World Championship 2021 PGNs into ChessCV MySQL.

Run from the project root with the same Python environment as the backend:
    python import_wcc2021_games.py

Preserves only ChessCV's six PGN tags. ECO and opening name are stored
in Game columns, and each legal half-move receives its SAN/UCI/FEN data.
Re-running the script does not duplicate an identical saved game.
"""

from __future__ import annotations

import io
from datetime import datetime

import chess
import chess.pgn
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.database.db import SessionLocal
from backend.app.database.models.game import Game
from backend.app.database.models.move import Move
from backend.app.database.models.player import Player


# ============================================================
# CHESSCV PGN HEADERS
# ============================================================

PGN_HEADERS = (
    "Event",
    "Date",
    "Round",
    "White",
    "Black",
    "Result",
)


# ============================================================
# TWO WORLD CHAMPIONSHIP GAMES
#
# Only the six ChessCV PGN headers are retained.
#
# ECO and Opening are stored separately in MySQL.
# ============================================================

GAMES_TO_IMPORT = [
    {
        "eco": "C88",
        "opening": "Ruy Lopez: Closed",
        "expected_plies": 89,
        "pgn": """[Event "FIDE World Championship 2021"]
[Date "2021.11.26"]
[Round "1"]
[White "Nepomniachtchi, Ian"]
[Black "Carlsen, Magnus"]
[Result "1/2-1/2"]

1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 4. Ba4 Nf6
5. O-O Be7 6. Re1 b5 7. Bb3 O-O 8. h3 Na5
9. Nxe5 Nxb3 10. axb3 Bb7 11. d3 d5
12. exd5 Qxd5 13. Qf3 Bd6 14. Kf1 Rfb8
15. Qxd5 Nxd5 16. Bd2 c5 17. Nf3 Rd8
18. Nc3 Nb4 19. Rec1 Rac8 20. Ne2 Nc6
21. Be3 Ne7 22. Bf4 Bxf3 23. gxf3 Bxf4
24. Nxf4 Rc6 25. Re1 Nf5 26. c3 Nh4
27. Re3 Kf8 28. Ng2 Nf5 29. Re5 g6
30. Ne1 Ng7 31. Re4 f5 32. Re3 Ne6
33. Ng2 b4 34. Ke2 Rb8 35. Kd2 bxc3+
36. bxc3 Rxb3 37. Kc2 Rb7 38. h4 Kf7
39. Ree1 Kf6 40. Ne3 Rd7 41. Nc4 Re7
42. Ne5 Rd6 43. Nc4 Rc6 44. Ne5 Rd6
45. Nc4 1/2-1/2""",
    },
    {
        "eco": "D02",
        "opening": "Queen's Pawn Game: Pseudo-Catalan",
        "expected_plies": 271,
        "pgn": """[Event "FIDE World Championship 2021"]
[Date "2021.12.03"]
[Round "6"]
[White "Carlsen, Magnus"]
[Black "Nepomniachtchi, Ian"]
[Result "1-0"]

1. d4 Nf6 2. Nf3 d5 3. g3 e6 4. Bg2 Be7
5. O-O O-O 6. b3 c5 7. dxc5 Bxc5
8. c4 dxc4 9. Qc2 Qe7 10. Nbd2 Nc6
11. Nxc4 b5 12. Nce5 Nb4 13. Qb2 Bb7
14. a3 Nc6 15. Nd3 Bb6 16. Bg5 Rfd8
17. Bxf6 gxf6 18. Rac1 Nd4 19. Nxd4 Bxd4
20. Qa2 Bxg2 21. Kxg2 Qb7+ 22. Kg1 Qe4
23. Qc2 a5 24. Rfd1 Kg7 25. Rd2 Rac8
26. Qxc8 Rxc8 27. Rxc8 Qd5 28. b4 a4
29. e3 Be5 30. h4 h5 31. Kh2 Bb2
32. Rc5 Qd6 33. Rd1 Bxa3 34. Rxb5 Qd7
35. Rc5 e5 36. Rc2 Qd5 37. Rdd2 Qb3
38. Ra2 e4 39. Nc5 Qxb4 40. Nxe4 Qb3
41. Rac2 Bf8 42. Nc5 Qb5 43. Nd3 a3
44. Nf4 Qa5 45. Ra2 Bb4 46. Rd3 Kh6
47. Rd1 Qa4 48. Rda1 Bd6 49. Kg1 Qb3
50. Ne2 Qd3 51. Nd4 Kh7 52. Kh2 Qe4
53. Rxa3 Qxh4+ 54. Kg1 Qe4 55. Ra4 Be5
56. Ne2 Qc2 57. R1a2 Qb3 58. Kg2 Qd5+
59. f3 Qd1 60. f4 Bc7 61. Kf2 Bb6
62. Ra1 Qb3 63. Re4 Kg7 64. Re8 f5
65. Raa8 Qb4 66. Rac8 Ba5 67. Rc1 Bb6
68. Re5 Qb3 69. Re8 Qd5 70. Rcc8 Qh1
71. Rc1 Qd5 72. Rb1 Ba7 73. Re7 Bc5
74. Re5 Qd3 75. Rb7 Qc2 76. Rb5 Ba7
77. Ra5 Bb6 78. Rab5 Ba7 79. Rxf5 Qd3
80. Rxf7+ Kxf7 81. Rb7+ Kg6 82. Rxa7 Qd5
83. Ra6+ Kh7 84. Ra1 Kg6 85. Nd4 Qb7
86. Ra2 Qh1 87. Ra6+ Kf7 88. Nf3 Qb1
89. Rd6 Kg7 90. Rd5 Qa2+ 91. Rd2 Qb1
92. Re2 Qb6 93. Rc2 Qb1 94. Nd4 Qh1
95. Rc7+ Kf6 96. Rc6+ Kf7 97. Nf3 Qb1
98. Ng5+ Kg7 99. Ne6+ Kf7 100. Nd4 Qh1
101. Rc7+ Kf6 102. Nf3 Qb1 103. Rd7 Qb2+
104. Rd2 Qb1 105. Ng1 Qb4 106. Rd1 Qb3
107. Rd6+ Kg7 108. Rd4 Qb2+ 109. Ne2 Qb1
110. e4 Qh1 111. Rd7+ Kg8 112. Rd4 Qh2+
113. Ke3 h4 114. gxh4 Qh3+ 115. Kd2 Qxh4
116. Rd3 Kf8 117. Rf3 Qd8+ 118. Ke3 Qa5
119. Kf2 Qa7+ 120. Re3 Qd7 121. Ng3 Qd2+
122. Kf3 Qd1+ 123. Re2 Qb3+ 124. Kg2 Qb7
125. Rd2 Qb3 126. Rd5 Ke7 127. Re5+ Kf7
128. Rf5+ Ke8 129. e5 Qa2+ 130. Kh3 Qe6
131. Kh4 Qh6+ 132. Nh5 Qh7 133. e6 Qg6
134. Rf7 Kd8 135. f5 Qg1 136. Ng7 1-0""",
    },
]


# ============================================================
# PARSE AND VALIDATE PGN
# ============================================================

def parse_game(
    data: dict,
) -> tuple[dict, list[dict]]:

    source = io.StringIO(
        data["pgn"]
    )

    parsed = chess.pgn.read_game(
        source
    )

    if parsed is None:
        raise ValueError(
            "PGN is empty."
        )

    if parsed.errors:
        errors = "; ".join(
            str(error)
            for error in parsed.errors
        )

        raise ValueError(
            "Invalid PGN for round "
            f"{parsed.headers.get('Round')}: "
            f"{errors}"
        )

    # ========================================================
    # VALIDATE HEADERS
    # ========================================================

    for key in PGN_HEADERS:
        if not parsed.headers.get(key):
            raise ValueError(
                f"Missing PGN header: {key}"
            )

    if parsed.headers["Result"] not in (
        "1-0",
        "0-1",
        "1/2-1/2",
        "*",
    ):
        raise ValueError(
            "Invalid PGN result."
        )

    if chess.pgn.read_game(source) is not None:
        raise ValueError(
            "A PGN block contains more than one game."
        )

    # ========================================================
    # GENERATE MOVE RECORDS
    #
    # This is the format required by ChessCV's moves table.
    # ========================================================

    board = parsed.board()
    records: list[dict] = []

    for move in parsed.mainline_moves():

        if move not in board.legal_moves:
            raise ValueError(
                f"Illegal move {move.uci()} "
                f"in round {parsed.headers['Round']}."
            )

        records.append({
            "ply": len(records) + 1,

            "move_number": board.fullmove_number,

            "color": (
                "white"
                if board.turn == chess.WHITE
                else "black"
            ),

            "uci": move.uci(),

            "san": board.san(move),

            "fen_before": board.fen(),
        })

        board.push(move)

        records[-1]["fen_after"] = (
            board.fen()
        )

    # ========================================================
    # PREVENT PARTIAL PGN IMPORT
    # ========================================================

    if len(records) != data["expected_plies"]:
        raise ValueError(
            f"Round {parsed.headers['Round']}: "
            f"expected {data['expected_plies']} "
            f"half-moves but parsed {len(records)}. "
            "Nothing will be imported."
        )

    # ========================================================
    # REBUILD PGN USING ONLY CHESSCV HEADERS
    # ========================================================

    headers = "\n".join(
        f'[{key} "{parsed.headers[key]}"]'
        for key in PGN_HEADERS
    )

    movetext = parsed.accept(
        chess.pgn.StringExporter(
            headers=False,
            variations=False,
            comments=False,
        )
    ).strip()

    normalized_pgn = (
        headers
        + "\n\n"
        + movetext
        + "\n"
    )

    # ========================================================
    # GAME INFORMATION
    # ========================================================

    info = {
        "white": parsed.headers["White"],

        "black": parsed.headers["Black"],

        "started_at": datetime.strptime(
            parsed.headers["Date"],
            "%Y.%m.%d",
        ),

        "result": parsed.headers["Result"],

        "initial_fen": parsed.board().fen(),

        "final_fen": board.fen(),

        "pgn": normalized_pgn,

        "opening": data["opening"],

        "eco": data["eco"],

        "total_moves": max(
            record["move_number"]
            for record in records
        ),

        "round": parsed.headers["Round"],
    }

    return info, records


# ============================================================
# GET OR CREATE PLAYER
#
# Same player lookup logic as ChessCV's save_game API.
# ============================================================

def get_or_create_player(
    db: Session,
    name: str,
) -> Player:

    clean = " ".join(
        name.strip().split()
    )

    player = db.scalar(
        select(Player)
        .where(
            func.lower(Player.name)
            == clean.lower()
        )
        .limit(1)
    )

    if player is not None:
        return player

    player = Player(
        name=clean
    )

    db.add(player)
    db.flush()

    return player


# ============================================================
# DUPLICATE DETECTION
#
# Compare the full UCI sequence of any matching saved game.
# Re-running this import must not duplicate existing data.
# ============================================================

def already_imported(
    db: Session,
    info: dict,
    records: list[dict],
    white_id: int,
    black_id: int,
) -> int | None:

    candidates = db.scalars(
        select(Game).where(
            Game.white_player_id == white_id,

            Game.black_player_id == black_id,

            Game.result == info["result"],

            Game.initial_fen == info["initial_fen"],

            Game.total_moves == info["total_moves"],
        )
    ).all()

    expected_uci = [
        record["uci"]
        for record in records
    ]

    for candidate in candidates:

        existing_uci = db.scalars(
            select(Move.uci)
            .where(
                Move.game_id == candidate.id
            )
            .order_by(
                Move.ply.asc()
            )
        ).all()

        if list(existing_uci) == expected_uci:
            return candidate.id

    return None


# ============================================================
# MAIN IMPORT
# ============================================================

def main() -> None:

    # ========================================================
    # VALIDATE BOTH GAMES BEFORE DATABASE WRITES
    # ========================================================

    prepared = [
        parse_game(data)
        for data in GAMES_TO_IMPORT
    ]

    results: list[
        tuple[str, str, int]
    ] = []

    # ========================================================
    # OPEN CHESSCV MYSQL SESSION
    # ========================================================

    with SessionLocal() as db:

        try:

            for info, records in prepared:

                # ============================================
                # PLAYERS
                # ============================================

                white = get_or_create_player(
                    db,
                    info["white"],
                )

                black = get_or_create_player(
                    db,
                    info["black"],
                )

                # ============================================
                # CHECK FOR DUPLICATES
                # ============================================

                existing_id = already_imported(
                    db,
                    info,
                    records,
                    white.id,
                    black.id,
                )

                if existing_id is not None:

                    results.append((
                        info["round"],
                        "already exists",
                        existing_id,
                    ))

                    continue

                # ============================================
                # GAME
                # ============================================

                game = Game(
                    white_player_id=white.id,

                    black_player_id=black.id,

                    initial_fen=info["initial_fen"],

                    final_fen=info["final_fen"],

                    pgn=info["pgn"],

                    result=info["result"],

                    # No termination reason was supplied.
                    termination=None,

                    opening_name=info["opening"],

                    eco_code=info["eco"],

                    total_moves=info["total_moves"],

                    # Only the historical date is known.
                    # Midnight is used as a date placeholder.
                    started_at=info["started_at"],

                    ended_at=None,
                )

                db.add(game)
                db.flush()

                # ============================================
                # MOVES
                #
                # Stores each move's:
                # ply, move_number, color, UCI, SAN,
                # fen_before and fen_after.
                # ============================================

                db.add_all(
                    Move(
                        game_id=game.id,
                        **record,
                    )
                    for record in records
                )

                results.append((
                    info["round"],
                    "inserted",
                    game.id,
                ))

            # ================================================
            # ATOMIC COMMIT
            #
            # Either the complete import succeeds,
            # or the transaction is rolled back.
            # ================================================

            db.commit()

        except Exception:

            db.rollback()
            raise

    # ========================================================
    # RESULT
    # ========================================================

    print()

    print(
        "=========================================="
    )

    print(
        "CHESSCV - PGN IMPORT RESULT"
    )

    print(
        "=========================================="
    )

    for round_number, status, game_id in results:

        print(
            f"Round {round_number}: "
            f"{status} "
            f"(game ID {game_id})"
        )

    print(
        "=========================================="
    )

    print(
        "Done. Open http://localhost:5173/games"
    )


if __name__ == "__main__":
    main()
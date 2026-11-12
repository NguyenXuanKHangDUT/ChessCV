from __future__ import annotations

from dataclasses import (
    dataclass,
)


@dataclass(
    frozen=True
)
class OpeningResult:

    eco_code: (
        str
        |
        None
    )

    opening_name: (
        str
        |
        None
    )

    full_name: (
        str
        |
        None
    )


# ============================================================
# OPENING SERVICE
# ============================================================

class OpeningService:

    def __init__(
        self,
    ):

        self._loaded = (
            False
        )


        self._available = (
            False
        )


        self._line_map: dict[
            tuple[
                str,
                ...
            ],
            tuple[
                str,
                str,
            ],
        ] = {}


        self._load_error: (
            str
            |
            None
        ) = None


    # ========================================================
    # NORMALIZE SAN
    # ========================================================

    def _normalize_san(
        self,
        san: str,
    ) -> str:

        return (
            san
            .strip()
            .replace(
                "0-0-0",
                "O-O-O",
            )
            .replace(
                "0-0",
                "O-O",
            )
        )


    # ========================================================
    # LOAD ECO DATA
    # ========================================================

    def _ensure_loaded(
        self,
    ):

        if self._loaded:

            return


        self._loaded = (
            True
        )


        try:

            from Openix import (
                ChessOpeningsLibrary,
            )


        except ImportError:

            self._load_error = (
                "Openix is not installed; "
                "opening recognition is disabled."
            )


            return


        try:

            library = (
                ChessOpeningsLibrary()
            )


            library.load_builtin_openings()


            line_map: dict[
                tuple[
                    str,
                    ...
                ],
                tuple[
                    str,
                    str,
                ],
            ] = {}


            for opening in (
                library
                .get_all_openings()
            ):

                moves = tuple(
                    self._normalize_san(
                        move
                    )

                    for move
                    in opening.moves_list
                )


                if not moves:

                    continue


                line_map[
                    moves
                ] = (
                    str(
                        opening.eco_code
                    ),

                    str(
                        opening.name
                    ),
                )


            self._line_map = (
                line_map
            )


            self._available = bool(
                line_map
            )


        except Exception as error:

            self._load_error = (
                str(
                    error
                )
            )


            self._available = (
                False
            )


            self._line_map = {}


    # ========================================================
    # MAIN OPENING NAME ONLY
    # ========================================================

    def _main_name(
        self,
        full_name: str,
    ) -> str:

        # ====================================================
        # EXAMPLE
        # ====================================================
        #
        # Ruy Lopez: Berlin Defense
        #
        # ->
        #
        # Ruy Lopez
        #
        #
        # Sicilian Defense: Najdorf Variation
        #
        # ->
        #
        # Sicilian Defense
        #
        # ====================================================

        return (
            full_name
            .split(
                ":",
                1,
            )[
                0
            ]
            .strip()
        )


    # ========================================================
    # RECOGNIZE FROM SAN MOVE LIST
    # ========================================================

    def recognize_from_san_moves(
        self,
        san_moves: list[
            str
        ],
    ) -> OpeningResult:

        self._ensure_loaded()


        if not self._available:

            return OpeningResult(
                eco_code=
                    None,

                opening_name=
                    None,

                full_name=
                    None,
            )


        normalized = [
            self._normalize_san(
                move
            )

            for move
            in san_moves

            if move.strip()
        ]


        # ====================================================
        # SEARCH BACKWARDS
        # ====================================================
        #
        # Most specific/deepest known opening line wins.
        #
        # ====================================================

        for length in range(
            len(
                normalized
            ),
            0,
            -1,
        ):

            key = tuple(
                normalized[
                    :
                    length
                ]
            )


            match = (
                self._line_map.get(
                    key
                )
            )


            if match is None:

                continue


            (
                eco_code,
                full_name,
            ) = match


            return OpeningResult(
                eco_code=
                    eco_code,

                opening_name=
                    self._main_name(
                        full_name
                    ),

                full_name=
                    full_name,
            )


        return OpeningResult(
            eco_code=
                None,

            opening_name=
                None,

            full_name=
                None,
        )


    # ========================================================
    # STATUS
    # ========================================================

    def get_status(
        self,
    ) -> dict:

        self._ensure_loaded()


        return {
            "available":
                self._available,

            "opening_lines":
                len(
                    self._line_map
                ),

            "error":
                self._load_error,
        }


# ============================================================
# SINGLETON
# ============================================================

opening_service = (
    OpeningService()
)
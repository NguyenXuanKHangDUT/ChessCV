from __future__ import annotations

import math

import cv2
import numpy as np

MIN_BOARD_AREA_RATIO = 0.06
MAX_BOARD_AREA_RATIO = 0.80
DEBUG_WARP_SIZE = 400

# Physical board used by this project: green / white.
GREEN_H_MIN = 30
GREEN_H_MAX = 105
GREEN_S_MIN = 45
GREEN_V_MIN = 25
MIN_GREEN_COMPONENT_RATIO = 0.025
MAX_GREEN_COMPONENT_RATIO = 0.70
MIN_CHECKER_SCORE = 0.48


def order_quad_points(points: np.ndarray) -> np.ndarray:
    """Return four points as TL, TR, BR, BL."""
    points = np.asarray(
        points,
        dtype=np.float32,
    ).reshape(
        4,
        2,
    )

    ordered = np.zeros(
        (
            4,
            2,
        ),
        dtype=np.float32,
    )

    sums = points.sum(
        axis=1,
    )

    diffs = np.diff(
        points,
        axis=1,
    ).reshape(
        -1,
    )

    ordered[0] = points[
        np.argmin(
            sums
        )
    ]

    ordered[2] = points[
        np.argmax(
            sums
        )
    ]

    ordered[1] = points[
        np.argmin(
            diffs
        )
    ]

    ordered[3] = points[
        np.argmax(
            diffs
        )
    ]

    return ordered


def quad_score(
    quad: np.ndarray,
    image_width: int,
    image_height: int,
) -> float:

    contour = quad.reshape(
        -1,
        1,
        2,
    ).astype(
        np.float32,
    )

    area = abs(
        cv2.contourArea(
            contour
        )
    )

    image_area = (
        image_width
        *
        image_height
    )

    area_ratio = (
        area
        /
        image_area
    )

    if not (
        MIN_BOARD_AREA_RATIO
        <=
        area_ratio
        <=
        MAX_BOARD_AREA_RATIO
    ):
        return -1.0


    tl, tr, br, bl = (
        quad
    )


    width_top = np.linalg.norm(
        tr
        -
        tl
    )

    width_bottom = np.linalg.norm(
        br
        -
        bl
    )

    height_left = np.linalg.norm(
        bl
        -
        tl
    )

    height_right = np.linalg.norm(
        br
        -
        tr
    )


    avg_width = (
        width_top
        +
        width_bottom
    ) / 2.0

    avg_height = (
        height_left
        +
        height_right
    ) / 2.0


    if (
        avg_width
        <
        1
        or
        avg_height
        <
        1
    ):
        return -1.0


    aspect_ratio = (
        avg_width
        /
        avg_height
    )


    if not (
        0.45
        <=
        aspect_ratio
        <=
        2.2
    ):
        return -1.0


    square_score = (
        min(
            avg_width,
            avg_height,
        )
        /
        max(
            avg_width,
            avg_height,
        )
    )


    center = np.mean(
        quad,
        axis=0,
    )


    image_center = np.array(
        [
            image_width / 2.0,
            image_height / 2.0,
        ],
        dtype=np.float32,
    )


    center_distance = (
        np.linalg.norm(
            center
            -
            image_center
        )
    )


    max_distance = (
        np.linalg.norm(
            image_center
        )
    )


    center_score = (
        1.0
        -
        min(
            1.0,
            center_distance
            /
            max_distance,
        )
    )


    # Large random rectangles must not
    # automatically beat the board.
    area_score = min(
        1.0,
        area_ratio
        /
        0.45,
    )


    return float(
        area_score
        *
        0.35
        +
        square_score
        *
        0.45
        +
        center_score
        *
        0.20
    )


def _warp_quad(
    frame: np.ndarray,
    quad: np.ndarray,
    size: int = DEBUG_WARP_SIZE,
) -> np.ndarray:

    b = (
        size
        -
        1
    )


    dst = np.array(
        [
            [0, 0],
            [b, 0],
            [b, b],
            [0, b],
        ],
        dtype=np.float32,
    )


    h = cv2.getPerspectiveTransform(
        quad.astype(
            np.float32
        ),
        dst,
    )


    return cv2.warpPerspective(
        frame,
        h,
        (
            size,
            size,
        ),
    )


def checkerboard_score(
    frame: np.ndarray,
    quad: np.ndarray,
) -> float:

    """
    Score how strongly a candidate looks
    like our green/white 8x8 board.
    """

    warped = _warp_quad(
        frame,
        quad,
    )


    hsv = cv2.cvtColor(
        warped,
        cv2.COLOR_BGR2HSV,
    )


    hue = (
        hsv[
            :,
            :,
            0,
        ]
        .astype(
            np.float32
        )
    )


    saturation = (
        hsv[
            :,
            :,
            1,
        ]
        .astype(
            np.float32
        )
        /
        255.0
    )


    green_hue = (
        (
            hue
            >=
            GREEN_H_MIN
        )
        &
        (
            hue
            <=
            GREEN_H_MAX
        )
    ).astype(
        np.float32
    )


    green_strength = (
        green_hue
        *
        saturation
    )


    cell = (
        DEBUG_WARP_SIZE
        //
        8
    )


    inset = max(
        4,
        int(
            round(
                cell
                *
                0.16
            )
        ),
    )


    values = np.zeros(
        (
            8,
            8,
        ),
        dtype=np.float32,
    )


    for row in range(
        8
    ):

        for col in range(
            8
        ):

            y1 = (
                row
                *
                cell
                +
                inset
            )

            y2 = (
                (
                    row
                    +
                    1
                )
                *
                cell
                -
                inset
            )

            x1 = (
                col
                *
                cell
                +
                inset
            )

            x2 = (
                (
                    col
                    +
                    1
                )
                *
                cell
                -
                inset
            )


            patch = green_strength[
                y1:y2,
                x1:x2,
            ]


            if patch.size:

                values[
                    row,
                    col,
                ] = float(
                    np.median(
                        patch
                    )
                )


    parity = (
        np.indices(
            (
                8,
                8,
            )
        )
        .sum(
            axis=0
        )
        %
        2
    )


    median_0 = float(
        np.median(
            values[
                parity
                ==
                0
            ]
        )
    )


    median_1 = float(
        np.median(
            values[
                parity
                ==
                1
            ]
        )
    )


    contrast = abs(
        median_0
        -
        median_1
    )


    midpoint = (
        median_0
        +
        median_1
    ) / 2.0


    green_parity = (
        0
        if
        median_0
        >
        median_1
        else
        1
    )


    correct = (
        (
            (
                parity
                ==
                green_parity
            )
            &
            (
                values
                >
                midpoint
            )
        )
        |
        (
            (
                parity
                !=
                green_parity
            )
            &
            (
                values
                <=
                midpoint
            )
        )
    )


    consistency = float(
        np.mean(
            correct
        )
    )


    contrast_score = min(
        1.0,
        contrast
        /
        0.25,
    )


    return float(
        contrast_score
        *
        0.65
        +
        consistency
        *
        0.35
    )


def _temporal_score(
    quad: np.ndarray,
    previous_points:
        list[list[float]]
        |
        np.ndarray
        |
        None,
    image_width: int,
    image_height: int,
) -> float:

    if previous_points is None:
        return 1.0


    previous = (
        order_quad_points(
            np.asarray(
                previous_points,
                dtype=np.float32,
            )
        )
    )


    distance = float(
        np.mean(
            np.linalg.norm(
                quad
                -
                previous,
                axis=1,
            )
        )
    )


    diagonal = math.hypot(
        image_width,
        image_height,
    )


    scale = max(
        1.0,
        diagonal
        *
        0.12,
    )


    return float(
        math.exp(
            -distance
            /
            scale
        )
    )


def _expand_quad(
    quad: np.ndarray,
    scale: float,
    image_width: int,
    image_height: int,
) -> np.ndarray:

    center = np.mean(
        quad,
        axis=0,
    )


    expanded = (
        center
        +
        (
            quad
            -
            center
        )
        *
        scale
    )


    expanded[
        :,
        0,
    ] = np.clip(
        expanded[
            :,
            0,
        ],
        0,
        image_width
        -
        1,
    )


    expanded[
        :,
        1,
    ] = np.clip(
        expanded[
            :,
            1,
        ],
        0,
        image_height
        -
        1,
    )


    return expanded.astype(
        np.float32
    )


def _find_green_board_candidates(
    frame: np.ndarray,
    previous_points:
        list[list[float]]
        |
        np.ndarray
        |
        None
        = None,
) -> list[dict]:

    height, width = (
        frame.shape[:2]
    )


    hsv = cv2.cvtColor(
        frame,
        cv2.COLOR_BGR2HSV,
    )


    mask = cv2.inRange(

        hsv,

        np.array(
            [
                GREEN_H_MIN,
                GREEN_S_MIN,
                GREEN_V_MIN,
            ],
            dtype=np.uint8,
        ),

        np.array(
            [
                GREEN_H_MAX,
                255,
                255,
            ],
            dtype=np.uint8,
        ),
    )


    kernel_size = int(
        round(
            min(
                width,
                height,
            )
            *
            0.04
        )
    )


    kernel_size = max(
        9,
        min(
            41,
            kernel_size,
        ),
    )


    if (
        kernel_size
        %
        2
        ==
        0
    ):
        kernel_size += 1


    kernel = (
        cv2.getStructuringElement(
            cv2.MORPH_RECT,
            (
                kernel_size,
                kernel_size,
            ),
        )
    )


    connected = (
        cv2.morphologyEx(
            mask,
            cv2.MORPH_CLOSE,
            kernel,
            iterations=2,
        )
    )


    contours, _ = (
        cv2.findContours(
            connected,
            cv2.RETR_EXTERNAL,
            cv2.CHAIN_APPROX_SIMPLE,
        )
    )


    candidates: list[
        dict
    ] = []


    image_area = (
        width
        *
        height
    )


    for contour in contours:

        area_ratio = (
            cv2.contourArea(
                contour
            )
            /
            image_area
        )


        if not (
            MIN_GREEN_COMPONENT_RATIO
            <=
            area_ratio
            <=
            MAX_GREEN_COMPONENT_RATIO
        ):
            continue


        hull = cv2.convexHull(
            contour
        )


        perimeter = (
            cv2.arcLength(
                hull,
                True,
            )
        )


        base_quad = None


        for epsilon_factor in (
            0.02,
            0.03,
            0.04,
            0.05,
            0.06,
            0.08,
        ):

            approx = (
                cv2.approxPolyDP(
                    hull,
                    epsilon_factor
                    *
                    perimeter,
                    True,
                )
            )


            if (
                len(
                    approx
                )
                ==
                4
                and
                cv2.isContourConvex(
                    approx
                )
            ):

                base_quad = (
                    order_quad_points(
                        approx.reshape(
                            4,
                            2,
                        )
                    )
                )

                break


        if base_quad is None:
            continue


        # Green regions can end slightly
        # inside the true edge because some
        # edge squares are white.
        for expansion in (
            1.00,
            1.04,
            1.08,
            1.12,
        ):

            quad = _expand_quad(
                base_quad,
                expansion,
                width,
                height,
            )


            geometry = quad_score(
                quad,
                width,
                height,
            )


            if geometry < 0:
                continue


            checker = (
                checkerboard_score(
                    frame,
                    quad,
                )
            )


            temporal = (
                _temporal_score(
                    quad,
                    previous_points,
                    width,
                    height,
                )
            )


            score = (
                checker
                *
                0.72
                +
                geometry
                *
                0.18
                +
                temporal
                *
                0.10
            )


            candidates.append(
                {
                    "score":
                        float(
                            score
                        ),

                    "checker_score":
                        float(
                            checker
                        ),

                    "geometry_score":
                        float(
                            geometry
                        ),

                    "temporal_score":
                        float(
                            temporal
                        ),

                    "quad":
                        quad,

                    "method":
                        "green_checkerboard",
                }
            )


    return candidates


def _find_generic_candidates(
    frame: np.ndarray,
    previous_points:
        list[list[float]]
        |
        np.ndarray
        |
        None
        = None,
) -> list[dict]:

    """
    Fallback if green segmentation
    temporarily fails.
    """

    height, width = (
        frame.shape[:2]
    )


    gray = cv2.cvtColor(
        frame,
        cv2.COLOR_BGR2GRAY,
    )


    clahe = (
        cv2.createCLAHE(
            clipLimit=2.0,
            tileGridSize=(
                8,
                8,
            ),
        )
    )


    enhanced = clahe.apply(
        gray
    )


    blurred = cv2.GaussianBlur(
        enhanced,
        (
            5,
            5,
        ),
        0,
    )


    candidates: list[
        dict
    ] = []


    seen: set[
        tuple[int, ...]
    ] = set()


    for low, high in (
        (
            30,
            100,
        ),
        (
            50,
            150,
        ),
        (
            70,
            200,
        ),
        (
            100,
            250,
        ),
    ):

        edges = cv2.Canny(
            blurred,
            low,
            high,
        )


        kernel = (
            cv2.getStructuringElement(
                cv2.MORPH_RECT,
                (
                    5,
                    5,
                ),
            )
        )


        closed = (
            cv2.morphologyEx(
                edges,
                cv2.MORPH_CLOSE,
                kernel,
                iterations=2,
            )
        )


        contours, _ = (
            cv2.findContours(
                closed,
                cv2.RETR_LIST,
                cv2.CHAIN_APPROX_SIMPLE,
            )
        )


        for contour in contours:

            area = cv2.contourArea(
                contour
            )


            if area <= 0:
                continue


            if (
                area
                /
                (
                    width
                    *
                    height
                )
                <
                MIN_BOARD_AREA_RATIO
            ):
                continue


            perimeter = (
                cv2.arcLength(
                    contour,
                    True,
                )
            )


            for epsilon_factor in (
                0.015,
                0.02,
                0.025,
                0.03,
                0.04,
            ):

                approx = (
                    cv2.approxPolyDP(
                        contour,
                        epsilon_factor
                        *
                        perimeter,
                        True,
                    )
                )


                if (
                    len(
                        approx
                    )
                    !=
                    4
                    or
                    not
                    cv2.isContourConvex(
                        approx
                    )
                ):
                    continue


                quad = (
                    order_quad_points(
                        approx.reshape(
                            4,
                            2,
                        )
                    )
                )


                key = tuple(
                    np.round(
                        quad
                        /
                        5.0
                    )
                    .astype(
                        np.int32
                    )
                    .reshape(
                        -1
                    )
                    .tolist()
                )


                if key in seen:
                    break


                seen.add(
                    key
                )


                geometry = (
                    quad_score(
                        quad,
                        width,
                        height,
                    )
                )


                if geometry < 0:
                    break


                checker = (
                    checkerboard_score(
                        frame,
                        quad,
                    )
                )


                temporal = (
                    _temporal_score(
                        quad,
                        previous_points,
                        width,
                        height,
                    )
                )


                score = (
                    checker
                    *
                    0.55
                    +
                    geometry
                    *
                    0.30
                    +
                    temporal
                    *
                    0.15
                )


                candidates.append(
                    {
                        "score":
                            float(
                                score
                            ),

                        "checker_score":
                            float(
                                checker
                            ),

                        "geometry_score":
                            float(
                                geometry
                            ),

                        "temporal_score":
                            float(
                                temporal
                            ),

                        "quad":
                            quad,

                        "method":
                            "generic_contour",
                    }
                )


                break


    return candidates


def detect_board_corners(
    frame: np.ndarray,
    previous_points:
        list[list[float]]
        |
        np.ndarray
        |
        None
        = None,
) -> dict:

    if frame is None:

        raise ValueError(
            "Frame is None."
        )


    # Primary detector:
    # actual green/white physical board.
    green_candidates = (
        _find_green_board_candidates(
            frame,
            previous_points,
        )
    )


    green_candidates.sort(
        key=lambda item:
            item[
                "score"
            ],
        reverse=True,
    )


    if (
        green_candidates
        and
        green_candidates[0][
            "checker_score"
        ]
        >=
        MIN_CHECKER_SCORE
    ):

        best = (
            green_candidates[0]
        )


        return {
            "board_points":
                best[
                    "quad"
                ].tolist(),

            "score":
                float(
                    best[
                        "score"
                    ]
                ),

            "checker_score":
                float(
                    best[
                        "checker_score"
                    ]
                ),

            "geometry_score":
                float(
                    best[
                        "geometry_score"
                    ]
                ),

            "method":
                best[
                    "method"
                ],
        }


    # Generic fallback.
    generic_candidates = (
        _find_generic_candidates(
            frame,
            previous_points,
        )
    )


    if not generic_candidates:

        raise ValueError(
            "Could not automatically detect "
            "the chessboard boundary."
        )


    generic_candidates.sort(
        key=lambda item:
            item[
                "score"
            ],
        reverse=True,
    )


    best = (
        generic_candidates[0]
    )


    return {
        "board_points":
            best[
                "quad"
            ].tolist(),

        "score":
            float(
                best[
                    "score"
                ]
            ),

        "checker_score":
            float(
                best[
                    "checker_score"
                ]
            ),

        "geometry_score":
            float(
                best[
                    "geometry_score"
                ]
            ),

        "method":
            best[
                "method"
            ],
    }


def create_outer_points_from_board(
    board_points: list[list[float]],
    scale: float = 1.18,
) -> list[list[float]]:

    board = np.asarray(
        board_points,
        dtype=np.float32,
    )


    center = np.mean(
        board,
        axis=0,
    )


    expanded = (
        center
        +
        (
            board
            -
            center
        )
        *
        scale
    )


    return expanded.tolist()
from pydantic import BaseModel


class ScalePrediction(BaseModel):

    crop_size: int

    piece: str

    confidence: float


class SquarePrediction(BaseModel):

    square: str

    occupied: bool

    occupancy_confidence: float

    empty_probability: float

    occupied_probability: float

    piece: str | None

    piece_confidence: float | None

    scale_predictions: list[
        ScalePrediction
    ]


class PositionRecognitionResponse(BaseModel):

    board_fen: str

    squares: dict[
        str,
        SquarePrediction
    ]

    context_margin: int

    detected_board_points: (
        list[list[float]]
        |
        None
    ) = None

    board_detection_score: (
        float
        |
        None
    ) = None
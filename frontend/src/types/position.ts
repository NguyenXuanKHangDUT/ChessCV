export type Point = [
  number,
  number,
];


export interface ScalePrediction {

  crop_size:
    number;

  piece:
    string;

  confidence:
    number;
}


export interface SquarePrediction {

  square:
    string;

  occupied:
    boolean;

  occupancy_confidence:
    number;

  empty_probability:
    number;

  occupied_probability:
    number;

  piece:
    string
    |
    null;

  piece_confidence:
    number
    |
    null;

  scale_predictions:
    ScalePrediction[];
}


export interface PositionRecognitionResponse {

  board_fen:
    string;

  squares:
    Record<
      string,
      SquarePrediction
    >;

  context_margin:
    number;

  detected_board_points?:
    number[][];

  board_detection_score?:
    number;
}
export type GameMode =
  | "human_vs_human"
  | "human_vs_bot";

export type BotType =
  | "beginner"
  | "stockfish_1800"
  | "stockfish_2800";

export type PositionMode =
  | "standard"
  | "detect";

export type CameraOrientation =
  | "white_left"
  | "black_left";

export type HumanColor =
  | "white"
  | "black";

export type SideToMove =
  | "w"
  | "b";


export interface LiveMove {
  ply: number;
  move_number: number;
  color: "white" | "black";

  uci: string;
  san: string;

  fen_before: string;
  fen_after: string;
}


export interface PendingBotMove {
  name: string;
  estimated_rating: number;

  color:
    | "white"
    | "black";

  uci: string;
  san: string;
}


export interface IllegalMoveEvent {
  event_id: number;
  uci: string;
  from_square: string;
  to_square: string;
  color: "white" | "black";
  piece_type: "pawn" | "knight" | "bishop" | "rook" | "queen" | "king";
  move_kind: string;
  promotion_piece: string | null;
}


export interface LiveGameStartRequest {
  white_name: string;
  black_name: string;

  game_mode: GameMode;
  bot_type: BotType;

  human_color:
    | HumanColor
    | null;

  side_to_move: SideToMove;

  camera_orientation: CameraOrientation;

  position_mode: PositionMode;
}


export interface LiveGameState {
  running: boolean;

  status: string;
  status_message: string;

  game_mode: GameMode;
  bot_type: BotType;
  position_mode: PositionMode;
  camera_orientation: CameraOrientation;

  selected_turn: SideToMove;

  white_name: string;
  black_name: string;

  human_color:
    | HumanColor
    | null;

  bot_color:
    | HumanColor
    | null;

  started_at:
    | string
    | null;

  pending_bot_move:
    | PendingBotMove
    | null;

  illegal_move_event:
    | IllegalMoveEvent
    | null;

  tracking_shift_px: number;

  observation_change_count: number;

  observed_board_fen:
    | string
    | null;

  board_detection_score:
    | number
    | null;

  board_checker_score:
    | number
    | null;

  board_detection_method:
    | string
    | null;

  board_points:
    | number[][]
    | null;

  last_error:
    | string
    | null;

  current_position_check:
    | Record<string, unknown>
    | null;

  move_resolution:
    | Record<string, unknown>
    | null;

  initialized: boolean;

  initial_fen:
    | string
    | null;

  board_fen: string;

  fen: string;

  turn:
    | "white"
    | "black";

  last_move:
    | LiveMove
    | null;

  moves: LiveMove[];

  pgn: string;

  game_over: boolean;

  result: string;

  eco_code:
    | string
    | null;

  opening_name:
    | string
    | null;
}
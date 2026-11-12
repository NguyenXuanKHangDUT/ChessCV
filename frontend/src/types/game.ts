export interface SaveGameMove {
  ply: number;
  move_number: number;
  color: "white" | "black";

  uci: string;
  san: string;

  fen_before: string;
  fen_after: string;
}


export interface SaveGameRequest {
  white_name: string;
  black_name: string;

  initial_fen: string;
  final_fen: string;

  pgn: string;
  result: string;

  termination: string | null;
  started_at: string | null;
  ended_at: string | null;

  moves: SaveGameMove[];
}


export interface SaveGameResponse {
  saved: boolean;
  game_id: number;

  opening: string | null;
  eco_code: string | null;
}


export interface GameHistoryItem {
  id: number;
  date: string | null;

  white: string;
  black: string;
  result: string;

  opening: string | null;
  eco_code: string | null;

  moves: number;
}


// ============================================================
// SAVED GAME DETAIL
// ============================================================

export interface SavedGameDetail extends GameHistoryItem {
  initial_fen: string;
  final_fen: string | null;

  pgn: string | null;
  termination: string | null;

  started_at: string | null;
  ended_at: string | null;

  move_list: SaveGameMove[];
}


// ============================================================
// STOCKFISH ANALYSIS
// ============================================================

export type MoveClassification =
  | "best"
  | "excellent"
  | "good"
  | "inaccuracy"
  | "mistake"
  | "blunder";


export interface ReviewedMove {
  ply: number;
  move_number: number;

  color: "white" | "black";

  uci: string;
  san: string;
  fen_after: string;

  best_uci: string | null;
  best_san: string | null;

  evaluation_cp: number;
  evaluation_mate: number | null;

  win_chance_loss: number;
  accuracy: number;

  classification: MoveClassification;
}


export interface PlayerAnalysisSummary {
  accuracy: number | null;

  counts: Record<
    MoveClassification,
    number
  >;
}


export interface GameAnalysis {
  game_id: number;
  engine: string;

  seconds_per_position: number;
  method: string;

  initial_evaluation_cp: number;
  initial_evaluation_mate: number | null;

  moves: ReviewedMove[];

  summary: {
    white: PlayerAnalysisSummary;
    black: PlayerAnalysisSummary;
  };
}
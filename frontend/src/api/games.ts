import type {
  GameAnalysis,
  GameHistoryItem,
  SavedGameDetail,
  SaveGameRequest,
  SaveGameResponse,
} from "../types/game";


const API_BASE_URL =
  "http://127.0.0.1:8000/api";


// ============================================================
// ERROR HANDLING
// ============================================================

async function getErrorMessage(
  response: Response,
  fallback: string,
): Promise<string> {

  try {
    const data: unknown = await response.json();

    if (
      data &&
      typeof data === "object" &&
      "detail" in data
    ) {
      const detail = (
        data as { detail?: unknown }
      ).detail;

      if (typeof detail === "string") {
        return detail;
      }
    }

  } catch {
    // Keep fallback if the response is not JSON.
  }

  return fallback;
}


// ============================================================
// SAVE GAME - EXISTING
// ============================================================

export async function saveGame(
  payload: SaveGameRequest,
): Promise<SaveGameResponse> {

  const response = await fetch(
    `${API_BASE_URL}/games/save`,
    {
      method: "POST",

      headers: {
        "Content-Type": "application/json",
      },

      body: JSON.stringify(payload),
    },
  );

  if (!response.ok) {
    throw new Error(
      await getErrorMessage(
        response,
        `Could not save game: ${response.status}`,
      ),
    );
  }

  return response.json();
}


// ============================================================
// GET SAVED GAMES - EXISTING
// ============================================================

export async function getGames():
  Promise<GameHistoryItem[]> {

  const response = await fetch(
    `${API_BASE_URL}/games`,
    {
      cache: "no-store",
    },
  );

  if (!response.ok) {
    throw new Error(
      await getErrorMessage(
        response,
        `Could not load games: ${response.status}`,
      ),
    );
  }

  return response.json();
}


// ============================================================
// NEW: GET ONE SAVED GAME
// ============================================================

export async function getGame(
  gameId: number,
): Promise<SavedGameDetail> {

  const response = await fetch(
    `${API_BASE_URL}/games/${gameId}`,
    {
      cache: "no-store",
    },
  );

  if (!response.ok) {
    throw new Error(
      await getErrorMessage(
        response,
        `Could not load game: ${response.status}`,
      ),
    );
  }

  return response.json();
}


// ============================================================
// NEW: ANALYZE SAVED GAME WITH STOCKFISH
// ============================================================

export async function analyzeGame(
  gameId: number,
): Promise<GameAnalysis> {

  const response = await fetch(
    `${API_BASE_URL}/games/${gameId}/analyze`,
    {
      method: "POST",
    },
  );

  if (!response.ok) {
    throw new Error(
      await getErrorMessage(
        response,
        `Could not analyze game: ${response.status}`,
      ),
    );
  }

  return response.json();
}
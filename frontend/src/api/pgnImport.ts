// PGN preview/import is separate from the existing Games save/review API.
// No changes to the Live Game save flow are required.

const API_BASE_URL = "http://127.0.0.1:8000/api";

export interface PgnPreview {
  white: string;
  black: string;
  result: string;
  total_plies: number;
  total_moves: number;
  opening: string | null;
  eco_code: string | null;
  initial_fen: string;
  headers_kept: Record<string, string>;
  headers_database: Record<string, string>;
  headers_removed: string[];
  normalized_pgn: string;
  analysis_supported: boolean;
}

export interface PgnImportResult extends PgnPreview {
  saved: boolean;
  duplicate: boolean;
  game_id: number;
}

async function postPgn<T>(path: string, pgn: string): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/pgn/${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pgn }),
    });
  } catch {
    throw new Error("Cannot connect to ChessCV backend at 127.0.0.1:8000.");
  }

  if (!response.ok) {
    let message = `PGN ${path} failed (${response.status}).`;
    try {
      const data: unknown = await response.json();
      if (data && typeof data === "object" && "detail" in data) {
        const detail = data.detail;
        if (typeof detail === "string") message = detail;
        else if (Array.isArray(detail)) {
          message = detail.map((item) => {
            if (item && typeof item === "object" && "msg" in item) {
              return String(item.msg);
            }
            return String(item);
          }).join("; ");
        }
      }
    } catch {
      // Use the HTTP status if the response is not JSON.
    }
    throw new Error(message);
  }

  return response.json() as Promise<T>;
}

export function previewPgn(pgn: string): Promise<PgnPreview> {
  return postPgn<PgnPreview>("preview", pgn);
}

export function importPgn(pgn: string): Promise<PgnImportResult> {
  return postPgn<PgnImportResult>("import", pgn);
}
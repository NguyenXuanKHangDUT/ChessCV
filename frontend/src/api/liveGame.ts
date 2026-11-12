import type {
  LiveGameStartRequest,
  LiveGameState,
} from "../types/liveGame";


const API_BASE_URL =
  "http://127.0.0.1:8000/api";


export const LIVE_GAME_WS_URL =
  "ws://127.0.0.1:8000/api/live/ws";


export const LIVE_GAME_DEBUG_STREAM_URL =
  `${API_BASE_URL}/live/debug-stream`;


async function readLiveResponse(
  response: Response,
): Promise<LiveGameState> {

  if (!response.ok) {

    let message =
      `Live game request failed: ${response.status}`;


    try {

      const data =
        await response.json();


      if (
        data
        &&
        typeof data.detail
        ===
        "string"
      ) {

        message =
          data.detail;
      }

    } catch {

      // Keep fallback error.

    }


    throw new Error(
      message,
    );
  }


  return response.json();
}


export async function getLiveGameState():
  Promise<LiveGameState> {

  const response =
    await fetch(
      `${API_BASE_URL}/live/state`,
      {
        cache:
          "no-store",
      },
    );


  return readLiveResponse(
    response,
  );
}


export async function startLiveGame(
  setup: LiveGameStartRequest,
): Promise<LiveGameState> {

  const response =
    await fetch(
      `${API_BASE_URL}/live/start`,
      {
        method:
          "POST",

        headers: {
          "Content-Type":
            "application/json",
        },

        body:
          JSON.stringify(
            setup,
          ),
      },
    );


  return readLiveResponse(
    response,
  );
}


export async function stopLiveGame():
  Promise<LiveGameState> {

  const response =
    await fetch(
      `${API_BASE_URL}/live/stop`,
      {
        method:
          "POST",
      },
    );


  return readLiveResponse(
    response,
  );
}
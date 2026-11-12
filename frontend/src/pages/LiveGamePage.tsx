import { useEffect, useMemo, useRef, useState } from "react";
import type { ChangeEvent } from "react";
import { useNavigate } from "react-router-dom";

import {
  LIVE_GAME_DEBUG_STREAM_URL,
  LIVE_GAME_WS_URL,
  getLiveGameState,
  startLiveGame,
  stopLiveGame,
} from "../api/liveGame";

import { saveGame } from "../api/games";
import LiveChessBoard from "../components/chess/LiveChessBoard";

import type {
  BotType,
  CameraOrientation,
  GameMode,
  HumanColor,
  LiveGameStartRequest,
  LiveGameState,
  LiveMove,
  PositionMode,
  SideToMove,
} from "../types/liveGame";

import "./LiveGamePage.css";

// ============================================================
// UI BOT CATALOG
// All three bots are supported by the backend.
// ============================================================

type BotSelection = BotType;

type SpeechLanguage = "en" | "vi";

const BOT_OPTIONS: ReadonlyArray<{
  id: BotSelection;
  name: string;
  rating: number;
  description: string;
  available: boolean;
}> = [
  {
    id: "beginner",
    name: "Beginner Bot",
    rating: 800,
    description: "For relaxed games and new players",
    available: true,
  },
  {
    id: "stockfish_1800",
    name: "Stockfish Bot",
    rating: 1800,
    description: "A stronger tactical opponent",
    available: true,
  },
  {
    id: "stockfish_2800",
    name: "Grandmaster Bot",
    rating: 2800,
    description: "Strong Stockfish opponent (approximately 2800 Elo)",
    available: true,
  },
];

const PREVIEW_START_FEN =
  "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";

// ============================================================
// MOVE ROW / PGN RESULT
// ============================================================

interface MoveRow {
  moveNumber: number;
  white: LiveMove | null;
  black: LiveMove | null;
}

function buildMoveRows(moves: LiveMove[]): MoveRow[] {
  const rows = new Map<number, MoveRow>();

  for (const move of moves) {
    let row = rows.get(move.move_number);

    if (!row) {
      row = {
        moveNumber: move.move_number,
        white: null,
        black: null,
      };
      rows.set(move.move_number, row);
    }

    if (move.color === "white") {
      row.white = move;
    } else {
      row.black = move;
    }
  }

  return Array.from(rows.values());
}

function applyResultToPgn(pgn: string, result: string): string {
  if (!pgn || result === "*") {
    return pgn;
  }

  let updated = pgn.replace(
    /\[Result "[^"]*"\]/,
    `[Result "${result}"]`,
  );

  updated = updated.replace(
    /(?:1-0|0-1|1\/2-1\/2|\*)\s*$/,
    result,
  );

  return updated;
}

// ============================================================
// CHESS MOVE VOICE: ENGLISH + VIETNAMESE
// Only spoken move language changes; website text is unchanged.
// ============================================================

const PIECE_SPEECH_NAMES: Record<SpeechLanguage, Record<string, string>> = {
  en: {
    K: "King",
    Q: "Queen",
    R: "Rook",
    B: "Bishop",
    N: "Knight",
    P: "pawn",
  },
  vi: {
    K: "Vua",
    Q: "Hậu",
    R: "Xe",
    B: "Tượng",
    N: "Mã",
    P: "Tốt",
  },
};

const RANK_SPEECH_NAMES: Record<SpeechLanguage, Record<string, string>> = {
  en: {
    "1": "one", "2": "two", "3": "three", "4": "four",
    "5": "five", "6": "six", "7": "seven", "8": "eight",
  },
  vi: {
    "1": "một", "2": "hai", "3": "ba", "4": "bốn",
    "5": "năm", "6": "sáu", "7": "bảy", "8": "tám",
  },
};

// Vietnamese names of the files a-h, so f3 is read "ép ba".
const VI_FILE_SPEECH_NAMES: Record<string, string> = {
  a: "a",
  b: "bê",
  c: "xê",
  d: "đê",
  e: "e",
  f: "ép",
  g: "giê",
  h: "hát",
};

function squarePartToSpeech(value: string, language: SpeechLanguage): string {
  return value
    .split("")
    .map((character) => {
      const rank = RANK_SPEECH_NAMES[language][character];
      if (rank) return rank;
      if (language === "vi") {
        return VI_FILE_SPEECH_NAMES[character.toLowerCase()]
          ?? character.toLowerCase();
      }
      return character.toLowerCase();
    })
    .join(" ");
}

// SAN -> announcement. Handles ordinary moves, disambiguation,
// captures, castling, promotions, check and checkmate.
function chessMoveToSpeech(
  san: string,
  color: "white" | "black",
  language: SpeechLanguage,
): string {
  const isVietnamese = language === "vi";
  const player = isVietnamese
    ? (color === "white" ? "Trắng" : "Đen")
    : (color === "white" ? "White" : "Black");

  const cleaned = san.trim().replace(/[!?]+$/g, "");
  if (!cleaned) return "";

  const isCheckmate = cleaned.includes("#");
  const isCheck = cleaned.includes("+") && !isCheckmate;
  const move = cleaned.replace(/[+#]+$/g, "");

  let spokenMove = "";

  if (move === "O-O" || move === "0-0") {
    spokenMove = isVietnamese
      ? `${player} nhập thành cánh vua`
      : `${player} castles kingside`;
  } else if (move === "O-O-O" || move === "0-0-0") {
    spokenMove = isVietnamese
      ? `${player} nhập thành cánh hậu`
      : `${player} castles queenside`;
  } else {
    const firstCharacter = move.charAt(0);
    const isNamedPiece = Object.prototype.hasOwnProperty.call(
      PIECE_SPEECH_NAMES[language],
      firstCharacter,
    ) && firstCharacter !== "P";

    const pieceName = isNamedPiece
      ? PIECE_SPEECH_NAMES[language][firstCharacter]
      : PIECE_SPEECH_NAMES[language].P;

    const destinationMatch = move.match(/([a-h])([1-8])(?:=([QRBN]))?$/);
    if (!destinationMatch) return `${player} ${move}`;

    const destinationText = squarePartToSpeech(
      destinationMatch[1] + destinationMatch[2],
      language,
    );
    const promotedPiece = destinationMatch[3];
    const prefix = move.slice(
      isNamedPiece ? 1 : 0,
      move.length - destinationMatch[0].length,
    );
    const isCapture = prefix.includes("x");
    const fromHint = prefix.replace(/x/g, "");

    spokenMove = `${player} ${pieceName}`;

    if (fromHint) {
      spokenMove += ` ${isVietnamese ? "từ" : "from"} ${
        squarePartToSpeech(fromHint, language)
      }`;
    }

    if (isCapture) {
      spokenMove += ` ${isVietnamese ? "ăn" : "takes"} ${destinationText}`;
    } else {
      spokenMove += ` ${destinationText}`;
    }

    if (promotedPiece) {
      const promotedName = PIECE_SPEECH_NAMES[language][promotedPiece];
      spokenMove += isVietnamese
        ? ` phong thành ${promotedName}`
        : ` promotes to ${promotedName}`;
    }
  }

  if (isCheckmate) {
    spokenMove += isVietnamese ? ", chiếu hết" : ", checkmate";
  } else if (isCheck) {
    spokenMove += isVietnamese ? ", chiếu" : ", check";
  }

  return spokenMove;
}

// ============================================================
// MOVE AUDIO QUEUE
//
// EN: native browser speechSynthesis.
// VI: backend edge-tts returns a Vietnamese neural MP3.
// All announcements are played in order, and can be cancelled.
// ============================================================

const NEURAL_VOICE_URL = "http://127.0.0.1:8000/api/voice/speak";

let speechQueue: Promise<void> = Promise.resolve();
let speechController = new AbortController();

function cancelChessSpeech(): void {
  speechController.abort();
  speechController = new AbortController();
  speechQueue = Promise.resolve();

  if ("speechSynthesis" in window) {
    window.speechSynthesis.cancel();
  }
}

function playEnglishMove(text: string, signal: AbortSignal): Promise<void> {
  if (
    !("speechSynthesis" in window) ||
    !("SpeechSynthesisUtterance" in window) ||
    signal.aborted
  ) {
    return Promise.resolve();
  }

  return new Promise<void>((resolve, reject) => {
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = "en-US";
    utterance.rate = 0.92;
    utterance.pitch = 1;
    utterance.volume = 1;

    const voices = window.speechSynthesis.getVoices();
    const voice = voices.find((item) => item.lang.toLowerCase() === "en-us")
      ?? voices.find((item) => item.lang.toLowerCase().startsWith("en"));
    if (voice) utterance.voice = voice;

    let completed = false;
    const timer = window.setTimeout(() => {
      window.speechSynthesis.cancel();
      finish(new Error("English speech timed out."));
    }, 30000);

    function finish(error?: Error): void {
      if (completed) return;
      completed = true;
      window.clearTimeout(timer);
      signal.removeEventListener("abort", onAbort);
      utterance.onend = null;
      utterance.onerror = null;
      if (error) reject(error);
      else resolve();
    }

    function onAbort(): void {
      window.speechSynthesis.cancel();
      finish();
    }

    utterance.onend = () => finish();
    utterance.onerror = (event) => {
      if (signal.aborted || event.error === "canceled" || event.error === "interrupted") {
        finish();
      } else {
        finish(new Error(`English voice error: ${event.error}`));
      }
    };

    signal.addEventListener("abort", onAbort, { once: true });
    if (signal.aborted) {
      onAbort();
      return;
    }

    try {
      window.speechSynthesis.speak(utterance);
    } catch (error) {
      finish(error instanceof Error ? error : new Error("English voice failed."));
    }
  });
}

async function playVietnameseMove(text: string, signal: AbortSignal): Promise<void> {
  const response = await fetch(NEURAL_VOICE_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, voice: "vi-VN-HoaiMyNeural" }),
    signal,
  });

  if (!response.ok) {
    let message = `Vietnamese voice request failed (${response.status}).`;
    try {
      const result: unknown = await response.json();
      if (
        result && typeof result === "object" &&
        "detail" in result && typeof result.detail === "string"
      ) {
        message = result.detail;
      }
    } catch {
      // Keep the HTTP status if backend did not return JSON.
    }
    throw new Error(message);
  }

  const blob = await response.blob();
  if (signal.aborted) return;
  if (!blob.size) throw new Error("Vietnamese voice returned empty audio.");

  const objectUrl = URL.createObjectURL(blob);
  const audio = new Audio(objectUrl);
  audio.preload = "auto";

  try {
    await new Promise<void>((resolve, reject) => {
      let completed = false;

      function finish(error?: Error): void {
        if (completed) return;
        completed = true;
        audio.pause();
        audio.removeEventListener("ended", onEnded);
        audio.removeEventListener("error", onError);
        signal.removeEventListener("abort", onAbort);
        if (error) reject(error);
        else resolve();
      }

      function onEnded(): void { finish(); }
      function onError(): void { finish(new Error("MP3 playback failed.")); }
      function onAbort(): void { finish(); }

      audio.addEventListener("ended", onEnded);
      audio.addEventListener("error", onError);
      signal.addEventListener("abort", onAbort, { once: true });

      if (signal.aborted) {
        onAbort();
        return;
      }

      void audio.play().catch((error: unknown) => {
        if (signal.aborted) finish();
        else finish(
          error instanceof Error ? error : new Error("Could not play Vietnamese voice."),
        );
      });
    });
  } finally {
    audio.pause();
    audio.removeAttribute("src");
    audio.load();
    URL.revokeObjectURL(objectUrl);
  }
}

function speakChessMove(
  text: string,
  language: SpeechLanguage,
  onError: (message: string) => void,
): void {
  if (!text) return;
  const signal = speechController.signal;

  // The promise chain preserves human move -> bot suggestion order.
  speechQueue = speechQueue.then(async () => {
    if (signal.aborted) return;
    try {
      if (language === "vi") {
        await playVietnameseMove(text, signal);
      } else {
        await playEnglishMove(text, signal);
      }
    } catch (error) {
      if (signal.aborted) return;
      const message = error instanceof Error ? error.message : "Move voice failed.";
      console.warn("Chess voice unavailable:", error);
      onError(message);
    }
  });
}

// ============================================================
// SPEECH TRACKING: prevent duplicate WebSocket announcements
// ============================================================

interface SpeechTrackingState {
  initialized: boolean;
  sessionKey: string | null;
  lastSpokenPly: number;
  lastPendingBotKey: string | null;
  startRequested: boolean;
}

// ============================================================
// PAGE
// ============================================================

export default function LiveGamePage() {
  const navigate = useNavigate();

  const [state, setState] = useState<LiveGameState | null>(null);
  const [whiteName, setWhiteName] = useState("White");
  const [blackName, setBlackName] = useState("Black");
  const [gameMode, setGameMode] = useState<GameMode>("human_vs_human");
  const [botType, setBotType] = useState<BotSelection>("beginner");
  const [humanColor, setHumanColor] = useState<HumanColor>("white");
  const [sideToMove, setSideToMove] = useState<SideToMove>("w");
  const [cameraOrientation, setCameraOrientation] =
    useState<CameraOrientation>("white_left");
  const [positionMode, setPositionMode] = useState<PositionMode>("standard");
  const [manualResult, setManualResult] = useState("*");
  const [actionLoading, setActionLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [voiceError, setVoiceError] = useState<string | null>(null);
  const reconnectTimer = useRef<number | null>(null);

  // NEW: only the spoken chess moves use this language setting.
  const [speechLanguage, setSpeechLanguage] = useState<SpeechLanguage>("en");
  const speechLanguageRef = useRef<SpeechLanguage>("en");

  const speechTrackingRef = useRef<SpeechTrackingState>({
    initialized: false,
    sessionKey: null,
    lastSpokenPly: 0,
    lastPendingBotKey: null,
    startRequested: false,
  });

  function handleSpeechLanguageChange(language: SpeechLanguage): void {
    if (speechLanguageRef.current === language) return;

    speechLanguageRef.current = language;
    setSpeechLanguage(language);

    // Cancel both EN speech and any VI MP3 currently pending/playing.
    // Keep move-tracking state unchanged; do not replay past moves.
    cancelChessSpeech();
    setVoiceError(null);

    if ("speechSynthesis" in window) {
      window.speechSynthesis.resume();
    }
  }

  // ==========================================================
  // ANNOUNCE NEW CHESS MOVES
  // ==========================================================

  function announceNewMoves(nextState: LiveGameState): void {
    const tracking = speechTrackingRef.current;
    const sessionKey = nextState.started_at ?? "no-session";
    const moves = nextState.moves ?? [];
    const latestPly = moves.reduce(
      (maximum, move) => Math.max(maximum, move.ply), 0,
    );
    const pending = nextState.pending_bot_move;
    const pendingKey = pending
      ? `${sessionKey}:${latestPly}:${pending.uci}`
      : null;

    // First state loaded on page open: do not read old move history.
    if (!tracking.initialized) {
      tracking.initialized = true;
      tracking.sessionKey = sessionKey;
      tracking.lastSpokenPly = tracking.startRequested ? 0 : latestPly;
      tracking.lastPendingBotKey = tracking.startRequested ? null : pendingKey;
      if (!tracking.startRequested) return;
    }

    // New game started here: speak the first move if needed.
    // New session originating elsewhere: only sync its history.
    if (tracking.sessionKey !== sessionKey) {
      const announceNewSession = tracking.startRequested && nextState.running;
      tracking.sessionKey = sessionKey;
      tracking.lastSpokenPly = announceNewSession ? 0 : latestPly;
      tracking.lastPendingBotKey = announceNewSession ? null : pendingKey;
      tracking.startRequested = false;
      if (!announceNewSession) return;
    }

    if (latestPly < tracking.lastSpokenPly) {
      tracking.lastSpokenPly = latestPly;
      tracking.lastPendingBotKey = pendingKey;
      return;
    }

    const newMoves = moves.filter(
      (move) => move.ply > tracking.lastSpokenPly,
    );

    for (const move of newMoves) {
      const isBotMove =
        nextState.game_mode === "human_vs_bot" &&
        nextState.bot_color === move.color;

      // Bot suggestions are spoken from pending_bot_move instead.
      if (!isBotMove) {
        const language = speechLanguageRef.current;
        speakChessMove(
          chessMoveToSpeech(move.san, move.color, language),
          language,
          setVoiceError,
        );
      }
    }

    tracking.lastSpokenPly = latestPly;

    if (
      nextState.game_mode === "human_vs_bot" &&
      pending && pendingKey &&
      pendingKey !== tracking.lastPendingBotKey
    ) {
      const language = speechLanguageRef.current;
      speakChessMove(
        chessMoveToSpeech(pending.san, pending.color, language),
        language,
        setVoiceError,
      );
      tracking.lastPendingBotKey = pendingKey;
    }
  }

  // ==========================================================
  // BACKEND STATE + WEBSOCKET
  // ==========================================================

  useEffect(() => {
    let disposed = false;
    let socket: WebSocket | null = null;

    getLiveGameState()
      .then((nextState) => {
        if (!disposed) {
          announceNewMoves(nextState);
          setState(nextState);
        }
      })
      .catch((requestError: unknown) => {
        if (!disposed) {
          setError(
            requestError instanceof Error
              ? requestError.message
              : "Could not load live game state.",
          );
        }
      });

    function connect() {
      if (disposed) return;
      socket = new WebSocket(LIVE_GAME_WS_URL);

      socket.onmessage = (event) => {
        try {
          const nextState: LiveGameState = JSON.parse(event.data);
          announceNewMoves(nextState);
          setState(nextState);
          setError(null);
        } catch {
          setError("Invalid live state received from backend.");
        }
      };

      socket.onclose = () => {
        if (!disposed) {
          reconnectTimer.current = window.setTimeout(connect, 1000);
        }
      };

      socket.onerror = () => {
        socket?.close();
      };
    }

    connect();

    return () => {
      disposed = true;
      if (reconnectTimer.current !== null) {
        window.clearTimeout(reconnectTimer.current);
      }
      socket?.close();
      cancelChessSpeech();
    };
  }, []);

  // ==========================================================
  // EFFECTIVE PLAYER NAMES
  // ==========================================================

  const selectedBotName =
    BOT_OPTIONS.find((bot) => bot.id === botType)?.name ?? "Beginner Bot";

  const effectiveWhiteName = useMemo(() => {
    if (gameMode === "human_vs_bot" && humanColor === "black") {
      return selectedBotName;
    }
    return whiteName.trim() || "White";
  }, [gameMode, humanColor, selectedBotName, whiteName]);

  const effectiveBlackName = useMemo(() => {
    if (gameMode === "human_vs_bot" && humanColor === "white") {
      return selectedBotName;
    }
    return blackName.trim() || "Black";
  }, [gameMode, humanColor, selectedBotName, blackName]);

  const moveRows = useMemo(
    () => buildMoveRows(state?.moves ?? []),
    [state?.moves],
  );

  // ==========================================================
  // EXISTING SETUP CONTROLS
  // ==========================================================

  function handleGameModeChange(event: ChangeEvent<HTMLSelectElement>) {
    const value = event.target.value;
    if (value === "human_vs_human" || value === "human_vs_bot") {
      setGameMode(value);
    }
  }

  function handleBotTypeChange(bot: BotSelection) {
    setBotType(bot);
  }

  function handleHumanColorChange(event: ChangeEvent<HTMLSelectElement>) {
    const value = event.target.value;
    if (value === "white" || value === "black") {
      setHumanColor(value);
    }
  }

  function handleSideToMoveChange(event: ChangeEvent<HTMLSelectElement>) {
    const value = event.target.value;
    if (value === "w" || value === "b") {
      setSideToMove(value);
    }
  }

  function handleCameraOrientationChange(event: ChangeEvent<HTMLSelectElement>) {
    const value = event.target.value;
    if (value === "white_left" || value === "black_left") {
      setCameraOrientation(value);
    }
  }

  // ==========================================================
  // START GAME
  // ==========================================================

  async function handleStart() {
    setError(null);
    setActionLoading(true);

    const setup: LiveGameStartRequest = {
      white_name: effectiveWhiteName,
      black_name: effectiveBlackName,
      game_mode: gameMode,
      bot_type: botType,
      human_color: gameMode === "human_vs_bot" ? humanColor : null,
      side_to_move: sideToMove,
      camera_orientation: cameraOrientation,
      position_mode: positionMode,
    };

    speechTrackingRef.current.startRequested = true;
    cancelChessSpeech();
    setVoiceError(null);
    if ("speechSynthesis" in window) {
      window.speechSynthesis.resume();
    }

    try {
      const nextState = await startLiveGame(setup);
      announceNewMoves(nextState);
      setState(nextState);
      setManualResult("*");
    } catch (requestError) {
      speechTrackingRef.current.startRequested = false;
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Could not start game.",
      );
    } finally {
      setActionLoading(false);
    }
  }

  // ==========================================================
  // STOP ONLY
  // ==========================================================

  async function handleStop() {
    cancelChessSpeech();
    setError(null);
    setActionLoading(true);

    try {
      const nextState = await stopLiveGame();
      setState(nextState);
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Could not stop game.",
      );
    } finally {
      setActionLoading(false);
    }
  }

  // ==========================================================
  // END + SAVE
  // ==========================================================

  async function handleEndAndSave() {
    if (!state || !state.initialized || !state.initial_fen) {
      setError("Game position has not been initialized yet.");
      return;
    }

    const snapshot = state;
    const result = snapshot.game_over ? snapshot.result : manualResult;
    cancelChessSpeech();
    setSaving(true);
    setError(null);

    try {
      if (snapshot.running) {
        await stopLiveGame();
      }

      await saveGame({
        white_name: snapshot.white_name,
        black_name: snapshot.black_name,
        initial_fen: snapshot.initial_fen,
        final_fen: snapshot.fen,
        pgn: applyResultToPgn(snapshot.pgn, result),
        result,
        termination: snapshot.game_over ? "normal" : "manual",
        started_at: snapshot.started_at,
        ended_at: new Date().toISOString(),
        moves: snapshot.moves,
      });

      navigate("/games");
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Could not save game.",
      );
    } finally {
      setSaving(false);
    }
  }

  const showSetup = !state?.running && !saving;

  // ==========================================================
  // RENDER
  // ==========================================================

  return (
    <div className="page live-game-page">
      {/* HEADER / GAME ACTIONS */}
      <div className="live-header">
        <div>
          <h1>Live Game</h1>
          <p className="page-description">
            Track a physical game, play Human vs Human
            or against a chess bot, then save the
            result to MySQL.
          </p>
        </div>

        <div style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "flex-end",
          gap: 12,
          flexWrap: "wrap",
        }}>
          {/* Voice language toggle - does not translate the UI. */}
          <div
            role="group"
            aria-label="Move voice language"
            style={{ display: "flex", alignItems: "center", gap: 8 }}
          >
            <span style={{ fontSize: 12, color: "#aab7c8", fontWeight: 700 }}>
              Move voice
            </span>
            <div style={{
              display: "inline-flex",
              gap: 3,
              padding: 3,
              border: "1px solid #425269",
              borderRadius: 9,
              background: "#121c2a",
            }}>
              {(["en", "vi"] as const).map((language) => (
                <button
                  key={language}
                  type="button"
                  aria-pressed={speechLanguage === language}
                  aria-label={
                    language === "en"
                      ? "Speak moves in English"
                      : "Đọc nước đi bằng tiếng Việt"
                  }
                  onClick={() => handleSpeechLanguageChange(language)}
                  style={{
                    minWidth: 39,
                    minHeight: 30,
                    padding: "5px 9px",
                    borderRadius: 6,
                    background:
                      speechLanguage === language ? "#3b82f6" : "transparent",
                    color: speechLanguage === language ? "#ffffff" : "#9ca3af",
                    fontSize: 12,
                    fontWeight: 800,
                    boxShadow: "none",
                  }}
                >
                  {language.toUpperCase()}
                </button>
              ))}
            </div>
          </div>

          {state?.running && (
            <div className="live-header-actions">
              <select
                value={state.game_over ? state.result : manualResult}
                disabled={state.game_over || saving}
                onChange={(event) => setManualResult(event.target.value)}
              >
                <option value="*">Result: *</option>
                <option value="1-0">Result: 1-0</option>
                <option value="0-1">Result: 0-1</option>
                <option value="1/2-1/2">Result: 1/2-1/2</option>
              </select>

              <button
                type="button"
                className="secondary-button"
                disabled={actionLoading || saving}
                onClick={handleStop}
              >
                Stop
              </button>

              <button
                type="button"
                className="primary-button"
                disabled={saving || !state.initialized}
                onClick={handleEndAndSave}
              >
                {saving ? "Saving..." : "End & Save"}
              </button>
            </div>
          )}
        </div>
      </div>

      {error && (
        <div className="error-message live-error">
          {error}
        </div>
      )}
      {voiceError && (
        <div className="error-message live-error" role="alert">
          Move voice: {voiceError}
        </div>
      )}

      {/* GAME SETUP */}
      {showSetup && (
        <div className="live-setup-shell">
          {/* BOARD PREVIEW */}
          <aside className="live-preview-panel" aria-label="Chessboard preview">
            <div className="live-preview-player">
              <span className="live-preview-player-avatar" aria-hidden="true">
                ♟
              </span>
              <div>
                <small>Black</small>
                <strong>{effectiveBlackName}</strong>
              </div>
            </div>

            <LiveChessBoard
              fen={PREVIEW_START_FEN}
              orientation={gameMode === "human_vs_bot" ? humanColor : "white"}
            />

            <div className="live-preview-player">
              <span className="live-preview-player-avatar" aria-hidden="true">
                ♙
              </span>
              <div>
                <small>White</small>
                <strong>{effectiveWhiteName}</strong>
              </div>
            </div>

            <p className="live-preview-note">
              Board preview only. The physical camera
              remains the source of moves.
            </p>
          </aside>

          {/* SETUP CONTROLS */}
          <section className="live-setup-card">
            <div className="live-setup-title">
              <h2>Game Setup</h2>
              <p>
                Configure the game before starting
                the physical-board tracker.
              </p>
            </div>

            <div className="live-setup-grid">
              {/* GAME MODE */}
              <label className="live-field">
                <span>Game mode</span>
                <select value={gameMode} onChange={handleGameModeChange}>
                  <option value="human_vs_human">Human vs Human</option>
                  <option value="human_vs_bot">Human vs Bot</option>
                </select>
              </label>

              {/* BOT OPPONENTS */}
              {gameMode === "human_vs_bot" && (
                <div className="live-bot-section">
                  <div className="live-bot-section-heading">
                    <span className="live-section-label">Choose your opponent</span>
                    <span className="live-bot-count">3 bots</span>
                  </div>

                  <div
                    className="live-bot-options"
                    role="radiogroup"
                    aria-label="Choose your bot opponent"
                  >
                    {BOT_OPTIONS.map((bot) => (
                      <button
                        key={bot.id}
                        type="button"
                        role="radio"
                        aria-checked={botType === bot.id}
                        className={
                          botType === bot.id
                            ? "live-bot-option selected"
                            : "live-bot-option"
                        }
                        onClick={() => handleBotTypeChange(bot.id)}
                      >
                        {/* DEFAULT AVATAR */}
                        <span className="live-bot-avatar" aria-hidden="true">
                          <svg viewBox="0 0 48 48" fill="none" aria-hidden="true">
                            <circle cx="24" cy="17" r="9" fill="currentColor" />
                            <path
                              d="M7 43c0-10 7.6-17 17-17s17 7 17 17"
                              fill="currentColor"
                            />
                          </svg>
                        </span>

                        <span className="live-bot-meta">
                          <strong>{bot.name}</strong>
                          <small>{bot.description}</small>
                        </span>

                        <span className="live-bot-rank">
                          <strong>{bot.rating}</strong>
                          {!bot.available && <small>SOON</small>}
                        </span>
                      </button>
                    ))}
                  </div>

                </div>
              )}

              {/* YOUR SIDE */}
              {gameMode === "human_vs_bot" && (
                <label className="live-field">
                  <span>Your side</span>
                  <select value={humanColor} onChange={handleHumanColorChange}>
                    <option value="white">White</option>
                    <option value="black">Black</option>
                  </select>
                </label>
              )}

              {/* WHITE NAME */}
              <label className="live-field">
                <span>White</span>
                <input
                  type="text"
                  value={effectiveWhiteName}
                  disabled={gameMode === "human_vs_bot" && humanColor === "black"}
                  onChange={(event) => setWhiteName(event.target.value)}
                />
              </label>

              {/* BLACK NAME */}
              <label className="live-field">
                <span>Black</span>
                <input
                  type="text"
                  value={effectiveBlackName}
                  disabled={gameMode === "human_vs_bot" && humanColor === "white"}
                  onChange={(event) => setBlackName(event.target.value)}
                />
              </label>

              {/* SIDE TO MOVE */}
              <label className="live-field">
                <span>Side to move</span>
                <select value={sideToMove} onChange={handleSideToMoveChange}>
                  <option value="w">White</option>
                  <option value="b">Black</option>
                </select>
              </label>

              {/* CAMERA ORIENTATION */}
              <label className="live-field">
                <span>Camera orientation</span>
                <select
                  value={cameraOrientation}
                  onChange={handleCameraOrientationChange}
                >
                  <option value="white_left">White left / Black right</option>
                  <option value="black_left">Black left / White right</option>
                </select>
              </label>
            </div>

            {/* INITIAL POSITION */}
            <div className="live-position-section">
              <div className="live-section-label">Initial position</div>
              <div className="live-position-options">
                <label className={
                  positionMode === "standard"
                    ? "live-position-option selected"
                    : "live-position-option"
                }>
                  <input
                    type="radio"
                    name="position-mode"
                    checked={positionMode === "standard"}
                    onChange={() => setPositionMode("standard")}
                  />
                  <div>
                    <strong>Standard starting position</strong>
                    <span>
                      Start the digital board from the normal
                      chess starting position.
                    </span>
                  </div>
                </label>

                <label className={
                  positionMode === "detect"
                    ? "live-position-option selected"
                    : "live-position-option"
                }>
                  <input
                    type="radio"
                    name="position-mode"
                    checked={positionMode === "detect"}
                    onChange={() => setPositionMode("detect")}
                  />
                  <div>
                    <strong>Detect current position</strong>
                    <span>
                      Recognize the position currently visible
                      on the physical board.
                    </span>
                  </div>
                </label>
              </div>
            </div>

            {/* SUMMARY / START GAME */}
            <div className="live-setup-footer">
              <div className="live-setup-match">
                <strong>{effectiveWhiteName}</strong>
                <span>vs</span>
                <strong>{effectiveBlackName}</strong>
              </div>
              <button
                type="button"
                className="primary-button live-start-button"
                disabled={actionLoading}
                onClick={handleStart}
              >
                {actionLoading ? "Starting..." : "Start Game"}
              </button>
            </div>
          </section>
        </div>
      )}

      {/* ACTIVE GAME / PLAYER INFORMATION */}
      {state?.running && (
        <div className="live-match-card">
          <div className="live-player">
            <span>White</span>
            <strong>{state.white_name}</strong>
          </div>
          <div className="live-vs">VS</div>
          <div className="live-player">
            <span>Black</span>
            <strong>{state.black_name}</strong>
          </div>
          <div className="live-game-mode-badge">
            {state.game_mode === "human_vs_bot"
              ? state.bot_type === "stockfish_2800"
                ? "Grandmaster Bot ~2800"
                : state.bot_type === "stockfish_1800"
                  ? "Stockfish Bot ~1800"
                  : "Beginner Bot ~800"
              : "Human vs Human"}
          </div>
        </div>
      )}

      {/* LIVE STATUS */}
      <div className="live-status-card">
        <div className={`live-status-dot status-${state?.status ?? "stopped"}`} />
        <div className="live-status-main">
          <strong>{state?.status ?? "connecting"}</strong>
          <span>{state?.status_message ?? "Connecting to backend..."}</span>
        </div>
        {state && (
          <div className="live-status-metrics">
            <span>Shift {state.tracking_shift_px.toFixed(1)} px</span>
            <span>Changed {state.observation_change_count}</span>
            <span>Checker {state.board_checker_score?.toFixed(2) ?? "—"}</span>
          </div>
        )}
      </div>

      {/* BOARD AREA */}
      <div className="live-board-layout">
        {/* PHYSICAL BOARD */}
        <section className="live-panel">
          <h2>Physical board</h2>
          <div className="physical-board-stream">
            <img src={LIVE_GAME_DEBUG_STREAM_URL} alt="Physical chessboard" />
          </div>
          <div className="physical-help">
            <span>Green grid = detected 8×8 board area.</span>
            <span>Keep all physical squares inside the grid.</span>
            {state && (
              <span>
                Camera: {state.camera_orientation === "white_left"
                  ? "White left / Black right"
                  : "Black left / White right"}
              </span>
            )}
          </div>

          {/* PENDING BOT MOVE - below physical board */}
          {state?.running && state.pending_bot_move && (
            <div
              className="bot-move-card"
              style={{
                gridTemplateColumns: "minmax(0, 1fr)",
                gap: 10,
                marginTop: 16,
                marginBottom: 0,
              }}
            >
              <div className="bot-move-info">
                <span>{state.pending_bot_move.name} move</span>
                <strong>{state.pending_bot_move.san}</strong>
              </div>
              <div className="bot-move-description">
                Move the bot&apos;s piece on the physical board according to
                this move. The system will verify it before continuing.
              </div>
            </div>
          )}
        </section>

        {/* DIGITAL BOARD */}
        <section className="live-panel">
          <h2>Digital board</h2>
          {state?.initialized ? (
            <LiveChessBoard fen={state.fen} />
          ) : (
            <div className="digital-board-waiting">
              <strong>Waiting for position</strong>
              <span>
                {state?.position_mode === "detect"
                  ? "Recognizing the current physical position..."
                  : "Start a game to load the board."}
              </span>
            </div>
          )}
          <div className="current-turn">
            Turn: <strong>{state?.initialized ? state.turn : "—"}</strong>
          </div>
          <div className="last-move">
            Last move: <strong>{state?.last_move?.san ?? "—"}</strong>
          </div>
        </section>

        {/* MOVES */}
        <section className="live-panel moves-panel">
          <h2>Moves</h2>
          {moveRows.length === 0 ? (
            <div className="moves-empty">No moves yet.</div>
          ) : (
            <div className="move-list">
              {moveRows.map((row) => (
                <div className="move-row" key={row.moveNumber}>
                  <span className="move-number">{row.moveNumber}.</span>
                  <span>{row.white?.san ?? ""}</span>
                  <span>{row.black?.san ?? ""}</span>
                </div>
              ))}
            </div>
          )}
        </section>
      </div>

      {/* OPENING / FEN */}
      <div className="live-info-grid">
        <section className="live-panel">
          <h2>Opening</h2>
          <p className="muted-text">
            Opening recognition runs after the game is saved.
          </p>
        </section>
        <section className="live-panel">
          <h2>Current FEN</h2>
          <code className="fen-code">
            {state?.initialized ? state.fen : "—"}
          </code>
        </section>
      </div>

      {/* PGN */}
      <section className="live-panel pgn-panel">
        <h2>PGN</h2>
        <pre>{state?.initialized ? state.pgn : ""}</pre>
      </section>

      {/* BACKEND ERROR */}
      {state?.last_error && (
        <div className="error-message live-error">
          Backend: {state.last_error}
        </div>
      )}
    </div>
  );
}
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
// 2800 is only a frontend selection.
// Backend BotType remains unchanged.
// ============================================================

type BotSelection = BotType | "stockfish_2800";

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
    description: "Coming soon — interface preview only",
    available: false,
  },
];

const PREVIEW_START_FEN =
  "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";


// ============================================================
// MOVE ROW
// ============================================================

interface MoveRow {
  moveNumber: number;
  white: LiveMove | null;
  black: LiveMove | null;
}


// ============================================================
// MOVE TABLE
// ============================================================

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


// ============================================================
// PGN RESULT
// ============================================================

function applyResultToPgn(
  pgn: string,
  result: string,
): string {
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
// CHESS MOVE VOICE
//
// Convert SAN into natural English.
//
// Examples:
//
// Nf3  -> White Knight f three
// d5   -> Black pawn d five
// Bxc4 -> White Bishop takes c four
// O-O  -> White castles kingside
// Qh7# -> White Queen h seven, checkmate
//
// ============================================================

const PIECE_SPEECH_NAMES: Record<string, string> = {
  K: "King",
  Q: "Queen",
  R: "Rook",
  B: "Bishop",
  N: "Knight",
  P: "pawn",
};

const RANK_SPEECH_NAMES: Record<string, string> = {
  "1": "one",
  "2": "two",
  "3": "three",
  "4": "four",
  "5": "five",
  "6": "six",
  "7": "seven",
  "8": "eight",
};


// ============================================================
// SPEAK ONE SQUARE OR DISAMBIGUATION HINT
// ============================================================

function squarePartToSpeech(
  value: string,
): string {
  return value
    .split("")
    .map((character) => {
      return (
        RANK_SPEECH_NAMES[character]
        ?? character.toLowerCase()
      );
    })
    .join(" ");
}


// ============================================================
// CONVERT SAN TO SPOKEN ENGLISH
// ============================================================

function chessMoveToSpeech(
  san: string,
  color: "white" | "black",
): string {

  const player =
    color === "white"
      ? "White"
      : "Black";

  const cleaned = san
    .trim()
    .replace(/[!?]+$/g, "");

  if (!cleaned) {
    return "";
  }

  const isCheckmate =
    cleaned.includes("#");

  const isCheck =
    cleaned.includes("+") && !isCheckmate;

  const move = cleaned
    .replace(/[+#]+$/g, "");

  let spokenMove = "";


  // ==========================================================
  // CASTLING
  // ==========================================================

  if (
    move === "O-O" ||
    move === "0-0"
  ) {
    spokenMove = `${player} castles kingside`;

  } else if (
    move === "O-O-O" ||
    move === "0-0-0"
  ) {
    spokenMove = `${player} castles queenside`;

  } else {

    // ========================================================
    // NORMAL MOVE / CAPTURE / PROMOTION
    // ========================================================

    const firstCharacter = move.charAt(0);

    const isNamedPiece =
      Object.prototype.hasOwnProperty.call(
        PIECE_SPEECH_NAMES,
        firstCharacter,
      ) && firstCharacter !== "P";

    const pieceName = isNamedPiece
      ? PIECE_SPEECH_NAMES[firstCharacter]
      : "pawn";

    const destinationMatch = move.match(
      /([a-h])([1-8])(?:=([QRBN]))?$/,
    );

    if (!destinationMatch) {
      return `${player} ${move}`;
    }

    const destinationFile =
      destinationMatch[1];

    const destinationRank =
      destinationMatch[2];

    const promotedPiece =
      destinationMatch[3];

    const destinationText =
      squarePartToSpeech(
        destinationFile + destinationRank,
      );

    // Remove destination to find capture and
    // disambiguation information.

    const prefix = move.slice(
      isNamedPiece ? 1 : 0,
      move.length - destinationMatch[0].length,
    );

    const isCapture =
      prefix.includes("x");

    const fromHint = prefix.replace(
      /x/g,
      "",
    );

    spokenMove = `${player} ${pieceName}`;

    // Examples:
    // Nbd2 -> Knight from b d two
    // R1e2 -> Rook from one e two
    // exd5 -> pawn from e takes d five

    if (fromHint) {
      spokenMove += (
        ` from ${squarePartToSpeech(fromHint)}`
      );
    }

    if (isCapture) {
      spokenMove += (
        ` takes ${destinationText}`
      );

    } else {
      spokenMove += (
        ` ${destinationText}`
      );
    }

    if (promotedPiece) {
      spokenMove += (
        ` promotes to ${
          PIECE_SPEECH_NAMES[promotedPiece]
        }`
      );
    }
  }


  // ==========================================================
  // CHECK / CHECKMATE
  // ==========================================================

  if (isCheckmate) {
    spokenMove += ", checkmate";

  } else if (isCheck) {
    spokenMove += ", check";
  }

  return spokenMove;
}


// ============================================================
// BROWSER TEXT TO SPEECH
//
// No backend required.
// Uses the browser's installed English voice.
// ============================================================

function speakChessMove(
  text: string,
): void {

  if (!text) {
    return;
  }

  if (
    typeof window === "undefined" ||
    !("speechSynthesis" in window) ||
    !("SpeechSynthesisUtterance" in window)
  ) {
    return;
  }

  try {
    const utterance =
      new SpeechSynthesisUtterance(text);

    utterance.lang = "en-US";

    // Slightly slower than normal conversation
    // to make square coordinates easier to hear.

    utterance.rate = 0.92;
    utterance.pitch = 1.0;
    utterance.volume = 1.0;

    // Do not cancel here.
    //
    // When a human move and the bot reply arrive
    // in the same WebSocket update, both should
    // be spoken in order.

    window.speechSynthesis.speak(
      utterance
    );

  } catch (error) {
    console.warn(
      "Chess voice unavailable:",
      error,
    );
  }
}


// ============================================================
// SPEECH TRACKING
//
// Prevent duplicate speech on:
// - WebSocket updates
// - HTTP + WebSocket receiving the same state
// - Bot move confirmation on the physical board
// - Page refresh / reconnection
//
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

  const [state, setState] =
    useState<LiveGameState | null>(null);

  const [whiteName, setWhiteName] =
    useState("White");

  const [blackName, setBlackName] =
    useState("Black");

  const [gameMode, setGameMode] =
    useState<GameMode>("human_vs_human");

  const [botType, setBotType] =
    useState<BotSelection>("beginner");

  const [humanColor, setHumanColor] =
    useState<HumanColor>("white");

  const [sideToMove, setSideToMove] =
    useState<SideToMove>("w");

  const [cameraOrientation, setCameraOrientation] =
    useState<CameraOrientation>("white_left");

  const [positionMode, setPositionMode] =
    useState<PositionMode>("standard");

  const [manualResult, setManualResult] =
    useState("*");

  const [actionLoading, setActionLoading] =
    useState(false);

  const [saving, setSaving] =
    useState(false);

  const [error, setError] =
    useState<string | null>(null);

  const reconnectTimer =
    useRef<number | null>(null);


  // ==========================================================
  // NEW: SPEECH STATE
  // ==========================================================

  const speechTrackingRef =
    useRef<SpeechTrackingState>({
      initialized: false,

      sessionKey: null,

      lastSpokenPly: 0,

      lastPendingBotKey: null,

      startRequested: false,
    });


  // ==========================================================
  // NEW: ANNOUNCE NEW CHESS MOVES
  // ==========================================================

  function announceNewMoves(
    nextState: LiveGameState,
  ): void {

    const tracking =
      speechTrackingRef.current;

    const sessionKey =
      nextState.started_at ?? "no-session";

    const moves =
      nextState.moves ?? [];

    const latestPly = moves.reduce(
      (maximum, move) =>
        Math.max(maximum, move.ply),
      0,
    );

    const pending =
      nextState.pending_bot_move;

    const pendingKey = pending
      ? (
          `${sessionKey}:` +
          `${latestPly}:` +
          `${pending.uci}`
        )
      : null;


    // ========================================================
    // FIRST STATE AFTER OPENING / REFRESHING THE PAGE
    //
    // Existing moves and pending bot suggestions should
    // not suddenly be read aloud from history.
    // ========================================================

    if (!tracking.initialized) {
      tracking.initialized = true;

      tracking.sessionKey = sessionKey;

      tracking.lastSpokenPly = (
        tracking.startRequested
          ? 0
          : latestPly
      );

      tracking.lastPendingBotKey = (
        tracking.startRequested
          ? null
          : pendingKey
      );

      if (!tracking.startRequested) {
        return;
      }
    }


    // ========================================================
    // NEW GAME SESSION
    // ========================================================

    if (tracking.sessionKey !== sessionKey) {

      const announceNewSession =
        tracking.startRequested &&
        nextState.running;

      tracking.sessionKey = sessionKey;

      tracking.lastSpokenPly = (
        announceNewSession
          ? 0
          : latestPly
      );

      tracking.lastPendingBotKey = (
        announceNewSession
          ? null
          : pendingKey
      );

      tracking.startRequested = false;

      // A game already running elsewhere is treated as
      // existing history, not as freshly played moves.

      if (!announceNewSession) {
        return;
      }
    }


    // ========================================================
    // RECOVER FROM MOVE HISTORY RESET
    // ========================================================

    if (latestPly < tracking.lastSpokenPly) {
      tracking.lastSpokenPly = latestPly;
      tracking.lastPendingBotKey = pendingKey;

      return;
    }


    // ========================================================
    // READ CONFIRMED PHYSICAL MOVES
    //
    // Human vs Human:
    //   Read both colors.
    //
    // Human vs Bot:
    //   Read human moves on commit.
    //   Bot moves are read from pending_bot_move instead.
    // ========================================================

    const newMoves = moves.filter(
      (move) =>
        move.ply > tracking.lastSpokenPly,
    );

    for (const move of newMoves) {

      const isBotMove =
        nextState.game_mode === "human_vs_bot" &&
        nextState.bot_color === move.color;

      if (!isBotMove) {

        const spokenText =
          chessMoveToSpeech(
            move.san,
            move.color,
          );

        speakChessMove(spokenText);
      }
    }

    tracking.lastSpokenPly = latestPly;


    // ========================================================
    // READ BOT MOVE WHEN IT IS SUGGESTED
    //
    // Read the bot's move immediately, even before the
    // camera sees the piece moved on the physical board.
    // ========================================================

    if (
      nextState.game_mode === "human_vs_bot" &&
      pending &&
      pendingKey &&
      pendingKey !== tracking.lastPendingBotKey
    ) {

      const spokenText =
        chessMoveToSpeech(
          pending.san,
          pending.color,
        );

      speakChessMove(spokenText);

      tracking.lastPendingBotKey =
        pendingKey;
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
      if (disposed) {
        return;
      }

      socket = new WebSocket(LIVE_GAME_WS_URL);

      socket.onmessage = (event) => {
        try {
          const nextState: LiveGameState =
            JSON.parse(event.data);

          // Read only newly confirmed/suggested moves.
          announceNewMoves(nextState);

          setState(nextState);
          setError(null);

        } catch {
          setError(
            "Invalid live state received from backend.",
          );
        }
      };

      socket.onclose = () => {
        if (disposed) {
          return;
        }

        reconnectTimer.current =
          window.setTimeout(connect, 1000);
      };

      socket.onerror = () => {
        socket?.close();
      };
    }

    connect();

    return () => {
      disposed = true;

      if (reconnectTimer.current !== null) {
        window.clearTimeout(
          reconnectTimer.current
        );
      }

      socket?.close();

      // Stop speaking if the Live Game page is closed.
      if ("speechSynthesis" in window) {
        window.speechSynthesis.cancel();
      }
    };
  }, []);


  // ==========================================================
  // EFFECTIVE PLAYER NAMES
  // ==========================================================

  const selectedBotName =
    BOT_OPTIONS.find(
      (bot) => bot.id === botType
    )?.name
    ?? "Beginner Bot";

  const effectiveWhiteName = useMemo(() => {
    if (
      gameMode === "human_vs_bot" &&
      humanColor === "black"
    ) {
      return selectedBotName;
    }

    return whiteName.trim() || "White";
  }, [
    gameMode,
    humanColor,
    selectedBotName,
    whiteName,
  ]);

  const effectiveBlackName = useMemo(() => {
    if (
      gameMode === "human_vs_bot" &&
      humanColor === "white"
    ) {
      return selectedBotName;
    }

    return blackName.trim() || "Black";
  }, [
    gameMode,
    humanColor,
    selectedBotName,
    blackName,
  ]);

  const moveRows = useMemo(
    () => buildMoveRows(
      state?.moves ?? []
    ),
    [state?.moves],
  );


  // ==========================================================
  // EXISTING SETUP CONTROLS
  // ==========================================================

  function handleGameModeChange(
    event: ChangeEvent<HTMLSelectElement>,
  ) {
    const value = event.target.value;

    if (
      value === "human_vs_human" ||
      value === "human_vs_bot"
    ) {
      setGameMode(value);
    }
  }

  function handleBotTypeChange(
    bot: BotSelection,
  ) {
    setBotType(bot);
  }

  function handleHumanColorChange(
    event: ChangeEvent<HTMLSelectElement>,
  ) {
    const value = event.target.value;

    if (
      value === "white" ||
      value === "black"
    ) {
      setHumanColor(value);
    }
  }

  function handleSideToMoveChange(
    event: ChangeEvent<HTMLSelectElement>,
  ) {
    const value = event.target.value;

    if (
      value === "w" ||
      value === "b"
    ) {
      setSideToMove(value);
    }
  }

  function handleCameraOrientationChange(
    event: ChangeEvent<HTMLSelectElement>,
  ) {
    const value = event.target.value;

    if (
      value === "white_left" ||
      value === "black_left"
    ) {
      setCameraOrientation(value);
    }
  }


  // ==========================================================
  // START GAME
  // ==========================================================

  async function handleStart() {

    // Bot 2800 is UI-only.
    // Never send unsupported bot type to backend.

    if (
      gameMode === "human_vs_bot" &&
      botType === "stockfish_2800"
    ) {
      setError(
        "Grandmaster Bot (2800) is coming soon. Choose 800 or 1800 to play.",
      );

      return;
    }

    setError(null);
    setActionLoading(true);

    const setup: LiveGameStartRequest = {
      white_name: effectiveWhiteName,
      black_name: effectiveBlackName,

      game_mode: gameMode,

      bot_type:
        botType === "stockfish_2800"
          ? "beginner"
          : botType,

      human_color:
        gameMode === "human_vs_bot"
          ? humanColor
          : null,

      side_to_move: sideToMove,
      camera_orientation: cameraOrientation,
      position_mode: positionMode,
    };


    // ========================================================
    // NEW: PREPARE VOICE FOR A NEW GAME
    //
    // Starting the game is a user interaction, allowing
    // the browser to activate its speech engine.
    // ========================================================

    speechTrackingRef.current.startRequested = true;

    if ("speechSynthesis" in window) {
      window.speechSynthesis.cancel();
      window.speechSynthesis.resume();
    }


    try {
      const nextState =
        await startLiveGame(setup);

      // Handle first bot move when the bot plays White.
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
    setError(null);
    setActionLoading(true);

    try {
      const nextState =
        await stopLiveGame();

      setState(nextState);

      // Stop any queued voice announcements.
      if ("speechSynthesis" in window) {
        window.speechSynthesis.cancel();
      }

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
    if (
      !state ||
      !state.initialized ||
      !state.initial_fen
    ) {
      setError(
        "Game position has not been initialized yet.",
      );

      return;
    }

    const snapshot = state;

    const result = snapshot.game_over
      ? snapshot.result
      : manualResult;

    setSaving(true);
    setError(null);

    try {
      if (snapshot.running) {
        await stopLiveGame();
      }

      if ("speechSynthesis" in window) {
        window.speechSynthesis.cancel();
      }

      await saveGame({
        white_name: snapshot.white_name,
        black_name: snapshot.black_name,

        initial_fen: snapshot.initial_fen,
        final_fen: snapshot.fen,

        pgn: applyResultToPgn(
          snapshot.pgn,
          result,
        ),

        result,

        termination:
          snapshot.game_over
            ? "normal"
            : "manual",

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


  // ==========================================================
  // SETUP SCREEN
  // ==========================================================

  const showSetup =
    !state?.running && !saving;

  return (
    <div className="page live-game-page">

      {/* =====================================================
          HEADER / GAME ACTIONS
      ===================================================== */}

      <div className="live-header">
        <div>
          <h1>Live Game</h1>

          <p className="page-description">
            Track a physical game, play Human vs Human
            or against a chess bot, then save the
            result to MySQL.
          </p>
        </div>

        {state?.running && (
          <div className="live-header-actions">
            <select
              value={
                state.game_over
                  ? state.result
                  : manualResult
              }
              disabled={
                state.game_over || saving
              }
              onChange={(event) =>
                setManualResult(
                  event.target.value
                )
              }
            >
              <option value="*">
                Result: *
              </option>

              <option value="1-0">
                Result: 1-0
              </option>

              <option value="0-1">
                Result: 0-1
              </option>

              <option value="1/2-1/2">
                Result: 1/2-1/2
              </option>
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
              disabled={
                saving || !state.initialized
              }
              onClick={handleEndAndSave}
            >
              {saving ? "Saving..." : "End & Save"}
            </button>
          </div>
        )}
      </div>


      {/* ERROR */}

      {error && (
        <div className="error-message live-error">
          {error}
        </div>
      )}


      {/* =====================================================
          GAME SETUP
      ===================================================== */}

      {showSetup && (
        <div className="live-setup-shell">

          {/* BOARD PREVIEW */}

          <aside
            className="live-preview-panel"
            aria-label="Chessboard preview"
          >
            <div className="live-preview-player">
              <span
                className="live-preview-player-avatar"
                aria-hidden="true"
              >
                ♟
              </span>

              <div>
                <small>Black</small>
                <strong>
                  {effectiveBlackName}
                </strong>
              </div>
            </div>

            <LiveChessBoard
              fen={PREVIEW_START_FEN}
              orientation={
                gameMode === "human_vs_bot"
                  ? humanColor
                  : "white"
              }
            />

            <div className="live-preview-player">
              <span
                className="live-preview-player-avatar"
                aria-hidden="true"
              >
                ♙
              </span>

              <div>
                <small>White</small>
                <strong>
                  {effectiveWhiteName}
                </strong>
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

                <select
                  value={gameMode}
                  onChange={handleGameModeChange}
                >
                  <option value="human_vs_human">
                    Human vs Human
                  </option>

                  <option value="human_vs_bot">
                    Human vs Bot
                  </option>
                </select>
              </label>


              {/* BOT OPPONENTS */}

              {gameMode === "human_vs_bot" && (
                <div className="live-bot-section">

                  <div className="live-bot-section-heading">
                    <span className="live-section-label">
                      Choose your opponent
                    </span>

                    <span className="live-bot-count">
                      3 bots
                    </span>
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
                        aria-checked={
                          botType === bot.id
                        }
                        className={
                          botType === bot.id
                            ? "live-bot-option selected"
                            : "live-bot-option"
                        }
                        onClick={() =>
                          handleBotTypeChange(
                            bot.id
                          )
                        }
                      >

                        {/* DEFAULT AVATAR */}

                        <span
                          className="live-bot-avatar"
                          aria-hidden="true"
                        >
                          <svg
                            viewBox="0 0 48 48"
                            fill="none"
                            aria-hidden="true"
                          >
                            <circle
                              cx="24"
                              cy="17"
                              r="9"
                              fill="currentColor"
                            />

                            <path
                              d="M7 43c0-10 7.6-17 17-17s17 7 17 17"
                              fill="currentColor"
                            />
                          </svg>
                        </span>


                        {/* BOT NAME */}

                        <span className="live-bot-meta">
                          <strong>
                            {bot.name}
                          </strong>

                          <small>
                            {bot.description}
                          </small>
                        </span>


                        {/* BOT RATING */}

                        <span className="live-bot-rank">
                          <strong>
                            {bot.rating}
                          </strong>

                          {!bot.available && (
                            <small>
                              SOON
                            </small>
                          )}
                        </span>

                      </button>
                    ))}
                  </div>


                  {/* 2800 UI PLACEHOLDER */}

                  {botType === "stockfish_2800" && (
                    <p
                      className="live-bot-notice"
                      role="status"
                    >
                      Grandmaster Bot 2800 is a visual
                      placeholder. The backend does not
                      support this opponent yet.
                    </p>
                  )}

                </div>
              )}


              {/* YOUR SIDE */}

              {gameMode === "human_vs_bot" && (
                <label className="live-field">
                  <span>Your side</span>

                  <select
                    value={humanColor}
                    onChange={handleHumanColorChange}
                  >
                    <option value="white">
                      White
                    </option>

                    <option value="black">
                      Black
                    </option>
                  </select>
                </label>
              )}


              {/* WHITE NAME */}

              <label className="live-field">
                <span>White</span>

                <input
                  type="text"
                  value={effectiveWhiteName}
                  disabled={
                    gameMode === "human_vs_bot" &&
                    humanColor === "black"
                  }
                  onChange={(event) =>
                    setWhiteName(
                      event.target.value
                    )
                  }
                />
              </label>


              {/* BLACK NAME */}

              <label className="live-field">
                <span>Black</span>

                <input
                  type="text"
                  value={effectiveBlackName}
                  disabled={
                    gameMode === "human_vs_bot" &&
                    humanColor === "white"
                  }
                  onChange={(event) =>
                    setBlackName(
                      event.target.value
                    )
                  }
                />
              </label>


              {/* SIDE TO MOVE */}

              <label className="live-field">
                <span>Side to move</span>

                <select
                  value={sideToMove}
                  onChange={handleSideToMoveChange}
                >
                  <option value="w">
                    White
                  </option>

                  <option value="b">
                    Black
                  </option>
                </select>
              </label>


              {/* CAMERA ORIENTATION */}

              <label className="live-field">
                <span>Camera orientation</span>

                <select
                  value={cameraOrientation}
                  onChange={
                    handleCameraOrientationChange
                  }
                >
                  <option value="white_left">
                    White left / Black right
                  </option>

                  <option value="black_left">
                    Black left / White right
                  </option>
                </select>
              </label>

            </div>


            {/* INITIAL POSITION */}

            <div className="live-position-section">
              <div className="live-section-label">
                Initial position
              </div>

              <div className="live-position-options">

                <label
                  className={
                    positionMode === "standard"
                      ? "live-position-option selected"
                      : "live-position-option"
                  }
                >
                  <input
                    type="radio"
                    name="position-mode"
                    checked={
                      positionMode === "standard"
                    }
                    onChange={() =>
                      setPositionMode("standard")
                    }
                  />

                  <div>
                    <strong>
                      Standard starting position
                    </strong>

                    <span>
                      Start the digital board from
                      the normal chess starting
                      position.
                    </span>
                  </div>
                </label>


                <label
                  className={
                    positionMode === "detect"
                      ? "live-position-option selected"
                      : "live-position-option"
                  }
                >
                  <input
                    type="radio"
                    name="position-mode"
                    checked={
                      positionMode === "detect"
                    }
                    onChange={() =>
                      setPositionMode("detect")
                    }
                  />

                  <div>
                    <strong>
                      Detect current position
                    </strong>

                    <span>
                      Recognize the position
                      currently visible on the
                      physical board.
                    </span>
                  </div>
                </label>

              </div>
            </div>


            {/* SUMMARY / START GAME */}

            <div className="live-setup-footer">
              <div className="live-setup-match">
                <strong>
                  {effectiveWhiteName}
                </strong>

                <span>vs</span>

                <strong>
                  {effectiveBlackName}
                </strong>
              </div>

              <button
                type="button"
                className="primary-button live-start-button"
                disabled={
                  actionLoading ||
                  (
                    gameMode === "human_vs_bot" &&
                    botType === "stockfish_2800"
                  )
                }
                onClick={handleStart}
              >
                {actionLoading
                  ? "Starting..."
                  : (
                      gameMode === "human_vs_bot" &&
                      botType === "stockfish_2800"
                    )
                    ? "Coming soon — 2800"
                    : "Start Game"}
              </button>
            </div>

          </section>
        </div>
      )}


      {/* =====================================================
          ACTIVE GAME / PLAYER INFORMATION
      ===================================================== */}

      {state?.running && (
        <div className="live-match-card">
          <div className="live-player">
            <span>White</span>

            <strong>
              {state.white_name}
            </strong>
          </div>

          <div className="live-vs">
            VS
          </div>

          <div className="live-player">
            <span>Black</span>

            <strong>
              {state.black_name}
            </strong>
          </div>

          <div className="live-game-mode-badge">
            {state.game_mode === "human_vs_bot"
              ? state.bot_type === "stockfish_1800"
                ? "Stockfish Bot ~1800"
                : "Beginner Bot ~800"
              : "Human vs Human"}
          </div>
        </div>
      )}


      {/* =====================================================
          LIVE STATUS
      ===================================================== */}

      <div className="live-status-card">
        <div
          className={
            `live-status-dot status-${state?.status ?? "stopped"}`
          }
        />

        <div className="live-status-main">
          <strong>
            {state?.status ?? "connecting"}
          </strong>

          <span>
            {state?.status_message ??
              "Connecting to backend..."}
          </span>
        </div>

        {state && (
          <div className="live-status-metrics">
            <span>
              Shift{" "}
              {state.tracking_shift_px.toFixed(1)} px
            </span>

            <span>
              Changed{" "}
              {state.observation_change_count}
            </span>

            <span>
              Checker{" "}
              {state.board_checker_score?.toFixed(2) ?? "—"}
            </span>
          </div>
        )}
      </div>


      {/* =====================================================
          BOARD AREA
      ===================================================== */}

      <div className="live-board-layout">

        {/* PHYSICAL BOARD */}

        <section className="live-panel">
          <h2>Physical board</h2>

          <div className="physical-board-stream">
            <img
              src={LIVE_GAME_DEBUG_STREAM_URL}
              alt="Physical chessboard"
            />
          </div>

          <div className="physical-help">
            <span>
              Green grid = detected 8×8 board area.
            </span>

            <span>
              Keep all physical squares inside
              the grid.
            </span>

            {state && (
              <span>
                Camera:{" "}
                {state.camera_orientation === "white_left"
                  ? "White left / Black right"
                  : "Black left / White right"}
              </span>
            )}
          </div>


          {/* =================================================
              PENDING BOT MOVE

              Displayed below the physical board.
              Bot calculation and verification are unchanged.
          ================================================= */}

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
                <span>
                  {state.pending_bot_move.name} move
                </span>

                <strong>
                  {state.pending_bot_move.san}
                </strong>
              </div>

              <div className="bot-move-description">
                Move the bot&apos;s piece on the
                physical board according to this
                move. The system will verify it
                before continuing.
              </div>

            </div>
          )}

        </section>


        {/* DIGITAL BOARD */}

        <section className="live-panel">
          <h2>Digital board</h2>

          {state?.initialized ? (
            <LiveChessBoard
              fen={state.fen}
            />
          ) : (
            <div className="digital-board-waiting">
              <strong>
                Waiting for position
              </strong>

              <span>
                {state?.position_mode === "detect"
                  ? "Recognizing the current physical position..."
                  : "Start a game to load the board."}
              </span>
            </div>
          )}

          <div className="current-turn">
            Turn:{" "}

            <strong>
              {state?.initialized
                ? state.turn
                : "—"}
            </strong>
          </div>

          <div className="last-move">
            Last move:{" "}

            <strong>
              {state?.last_move?.san ?? "—"}
            </strong>
          </div>
        </section>


        {/* MOVES */}

        <section className="live-panel moves-panel">
          <h2>Moves</h2>

          {moveRows.length === 0 ? (
            <div className="moves-empty">
              No moves yet.
            </div>
          ) : (
            <div className="move-list">
              {moveRows.map((row) => (
                <div
                  className="move-row"
                  key={row.moveNumber}
                >
                  <span className="move-number">
                    {row.moveNumber}.
                  </span>

                  <span>
                    {row.white?.san ?? ""}
                  </span>

                  <span>
                    {row.black?.san ?? ""}
                  </span>
                </div>
              ))}
            </div>
          )}
        </section>

      </div>


      {/* =====================================================
          OPENING / FEN
      ===================================================== */}

      <div className="live-info-grid">
        <section className="live-panel">
          <h2>Opening</h2>

          <p className="muted-text">
            Opening recognition runs after
            the game is saved.
          </p>
        </section>

        <section className="live-panel">
          <h2>Current FEN</h2>

          <code className="fen-code">
            {state?.initialized
              ? state.fen
              : "—"}
          </code>
        </section>
      </div>


      {/* =====================================================
          PGN
      ===================================================== */}

      <section className="live-panel pgn-panel">
        <h2>PGN</h2>

        <pre>
          {state?.initialized
            ? state.pgn
            : ""}
        </pre>
      </section>


      {/* =====================================================
          BACKEND ERROR
      ===================================================== */}

      {state?.last_error && (
        <div className="error-message live-error">
          Backend: {state.last_error}
        </div>
      )}

    </div>
  );
}
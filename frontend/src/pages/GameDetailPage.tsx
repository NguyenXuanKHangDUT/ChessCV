import { useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties, MouseEvent } from "react";
import { Link, useParams } from "react-router-dom";

import { analyzeGame, getGame } from "../api/games";
import LiveChessBoard from "../components/chess/LiveChessBoard";
import type {
  GameAnalysis,
  MoveClassification,
  ReviewedMove,
  SavedGameDetail,
  SaveGameMove,
} from "../types/game";

import "./GameDetailPage.css";

// ============================================================
// REVIEW SYMBOLS
// These are approximate labels, not Chess.com's own algorithm.
// ============================================================

const QUALITY: Record<
  MoveClassification,
  { label: string; symbol: string; note: string }
> = {
  brilliant: {
    label: "Brilliant",
    symbol: "!!",
    note: "Sound voluntary material offer",
  },
  great: {
    label: "Great",
    symbol: "!",
    note: "Critical engine-best move",
  },
  best: {
    label: "Best",
    symbol: "★",
    note: "Engine's first choice",
  },
  excellent: {
    label: "Excellent",
    symbol: "✓",
    note: "Nearly no loss",
  },
  good: {
    label: "Good",
    symbol: "●",
    note: "Small evaluation loss",
  },
  book: {
    label: "Book",
    symbol: "📖",
    note: "Known opening line",
  },
  inaccuracy: {
    label: "Inaccuracy",
    symbol: "?!",
    note: "Noticeable loss",
  },
  mistake: {
    label: "Mistake",
    symbol: "?",
    note: "Significant loss",
  },
  miss: {
    label: "Miss",
    symbol: "✕",
    note: "Missed forcing opportunity",
  },
  blunder: {
    label: "Blunder",
    symbol: "??",
    note: "Very large loss",
  },
};

const QUALITY_ORDER: MoveClassification[] = [
  "brilliant",
  "great",
  "best",
  "excellent",
  "good",
  "book",
  "inaccuracy",
  "mistake",
  "miss",
  "blunder",
];

const STARTING_QUALITY_COUNTS: Record<MoveClassification, number> = {
  brilliant: 0,
  great: 0,
  best: 0,
  excellent: 0,
  good: 0,
  book: 0,
  inaccuracy: 0,
  mistake: 0,
  miss: 0,
  blunder: 0,
};

// ============================================================
// REVIEW TEXT / EVALUATION / DATE
// ============================================================

function reviewHeadline(move: ReviewedMove): string {
  if (move.classification === "book") {
    return `${move.san} is a book move`;
  }
  if (move.classification === "best") {
    return `${move.san} is the best move`;
  }
  if (move.classification === "excellent") {
    return `${move.san} is an excellent move`;
  }
  if (move.classification === "inaccuracy") {
    return `${move.san} is an inaccuracy`;
  }
  if (move.classification === "miss") {
    return `${move.san} misses a winning chance`;
  }
  return `${move.san} is a ${
    QUALITY[move.classification].label.toLowerCase()
  } move`;
}

function evalText(cp: number, mate: number | null): string {
  if (mate !== null) {
    return mate > 0
      ? `M${mate}`
      : mate < 0
        ? `-M${-mate}`
        : "M0";
  }

  const pawns = cp / 100;
  return `${pawns > 0 ? "+" : ""}${pawns.toFixed(2)}`;
}

function formatDate(value: string | null): string {
  if (!value) return "—";

  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleString("vi-VN");
}

// ============================================================
// MOVE ROWS
// ============================================================

function groupMoves(moves: SaveGameMove[]) {
  const rows = new Map<
    number,
    {
      number: number;
      white: SaveGameMove | null;
      black: SaveGameMove | null;
    }
  >();

  for (const move of moves) {
    let row = rows.get(move.move_number);

    if (!row) {
      row = {
        number: move.move_number,
        white: null,
        black: null,
      };
      rows.set(move.move_number, row);
    }

    row[move.color] = move;
  }

  return Array.from(rows.values());
}

// ============================================================
// BOARD SQUARE COORDINATES
// Marker sits at upper-right of the played destination square.
// ============================================================

function squarePosition(
  square: string,
  orientation: "white" | "black",
): { x: number; y: number } | null {
  if (!/^[a-h][1-8]$/.test(square)) return null;

  const file = square.charCodeAt(0) - 97;
  const rank = Number(square[1]) - 1;

  return orientation === "white"
    ? { x: file, y: 7 - rank }
    : { x: 7 - file, y: rank };
}

function squareStyle(
  square: string,
  orientation: "white" | "black",
): CSSProperties {
  const pos = squarePosition(square, orientation);

  return pos
    ? {
        left: `${pos.x * 12.5}%`,
        top: `${pos.y * 12.5}%`,
      }
    : { display: "none" };
}

function arrowPoints(
  uci: string,
  orientation: "white" | "black",
): {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
} | null {
  const from = squarePosition(uci.slice(0, 2), orientation);
  const to = squarePosition(uci.slice(2, 4), orientation);

  if (!from || !to) return null;

  return {
    x1: (from.x + 0.5) * 12.5,
    y1: (from.y + 0.5) * 12.5,
    x2: (to.x + 0.5) * 12.5,
    y2: (to.y + 0.5) * 12.5,
  };
}

// ============================================================
// INTERACTIVE EVALUATION GRAPH
// ============================================================

function EvaluationChart({
  analysis,
  selectedPly,
  onSelect,
}: {
  analysis: GameAnalysis;
  selectedPly: number;
  onSelect: (ply: number) => void;
}) {
  const values = [
    analysis.initial_evaluation_cp,
    ...analysis.moves.map((move) => move.evaluation_cp),
  ];

  const last = Math.max(1, values.length - 1);

  const x = (index: number) => (index / last) * 640;

  const y = (cp: number) =>
    54 - (Math.max(-900, Math.min(900, cp)) / 900) * 42;

  const points = values
    .map((value, index) => `${x(index)},${y(value)}`)
    .join(" ");

  const marker = Math.min(
    values.length - 1,
    Math.max(0, selectedPly),
  );

  function handleGraphClick(event: MouseEvent<SVGSVGElement>) {
    const rect = event.currentTarget.getBoundingClientRect();

    const fraction = Math.max(
      0,
      Math.min(
        1,
        (event.clientX - rect.left) / rect.width,
      ),
    );

    onSelect(Math.round(fraction * last));
  }

  return (
    <div className="review-chart-card">
      <div className="review-card-heading">
        <h3>Evaluation graph</h3>
        <span>Click to jump to a move</span>
      </div>

      <svg
        viewBox="0 0 640 108"
        role="img"
        aria-label="Clickable Stockfish evaluation graph"
        className="review-eval-chart"
        onClick={handleGraphClick}
      >
        <rect
          width="640"
          height="54"
          fill="#284960"
          opacity="0.75"
        />

        <rect
          y="54"
          width="640"
          height="54"
          fill="#121c2c"
        />

        <line
          x1="0"
          y1="54"
          x2="640"
          y2="54"
          stroke="#8194aa"
          strokeDasharray="5 5"
        />

        <polyline
          fill="none"
          stroke="#69c7ea"
          strokeWidth="3"
          strokeLinejoin="round"
          points={points}
        />

        {analysis.moves.map((move, index) =>
          [
            "brilliant",
            "great",
            "inaccuracy",
            "mistake",
            "miss",
            "blunder",
          ].includes(move.classification) ? (
            <circle
              key={move.ply}
              className={`review-graph-point class-${
                move.classification
              }`}
              cx={x(index + 1)}
              cy={y(move.evaluation_cp)}
              r="3.6"
            />
          ) : null,
        )}

        <line
          x1={x(marker)}
          y1="0"
          x2={x(marker)}
          y2="108"
          stroke="#ffd780"
          strokeWidth="2"
        />

        <circle
          cx={x(marker)}
          cy={y(values[marker])}
          r="5.5"
          fill="#ffd780"
          stroke="#12233b"
          strokeWidth="2"
        />
      </svg>

      <div className="review-chart-labels">
        <span>Starting position</span>
        <span>Final position</span>
      </div>
    </div>
  );
}

// ============================================================
// GAME REVIEW
// ============================================================

export default function GameDetailPage() {
  const { id } = useParams();
  const gameId = Number(id);

  const [game, setGame] = useState<SavedGameDetail | null>(null);
  const [analysis, setAnalysis] = useState<GameAnalysis | null>(null);

  const [selectedPly, setSelectedPly] = useState(0);
  const [orientation, setOrientation] =
    useState<"white" | "black">("white");

  const [previewBest, setPreviewBest] = useState(false);
  const [autoplay, setAutoplay] = useState(false);

  const [loading, setLoading] = useState(true);
  const [analyzing, setAnalyzing] = useState(false);

  const [error, setError] = useState<string | null>(null);
  const [analysisError, setAnalysisError] =
    useState<string | null>(null);

  const moveListRef = useRef<HTMLDivElement | null>(null);

  // ==========================================================
  // LOAD SAVED GAME
  // ==========================================================

  useEffect(() => {
    let active = true;

    setLoading(true);
    setError(null);
    setGame(null);
    setAnalysis(null);
    setSelectedPly(0);
    setPreviewBest(false);
    setAutoplay(false);

    if (!Number.isSafeInteger(gameId) || gameId < 1) {
      setError("Invalid game ID.");
      setLoading(false);
      return;
    }

    getGame(gameId)
      .then((data) => {
        if (active) setGame(data);
      })
      .catch((cause: unknown) => {
        if (active) {
          setError(
            cause instanceof Error
              ? cause.message
              : "Could not load game.",
          );
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
    };
  }, [gameId]);

  // ==========================================================
  // REPLAY STATE
  // ==========================================================

  const moves = useMemo(() => game?.move_list ?? [], [game]);

  const rows = useMemo(() => groupMoves(moves), [moves]);

  const currentMove =
    selectedPly > 0 ? moves[selectedPly - 1] : null;

  const selectedReview: ReviewedMove | undefined =
    analysis?.moves.find(
      (item) => item.ply === currentMove?.ply,
    );

  const bestAlternative = Boolean(
    currentMove &&
      selectedReview?.best_uci &&
      selectedReview.best_uci !== currentMove.uci,
  );

  const showBest = previewBest && bestAlternative;

  const currentFen = showBest
    ? currentMove?.fen_before
    : currentMove?.fen_after ?? game?.initial_fen;

  // Best move preview shows the position before the played move.
  const evaluationIndex = showBest
    ? Math.max(0, selectedPly - 1)
    : selectedPly;

  const evaluatedMove =
    evaluationIndex > 0
      ? analysis?.moves[evaluationIndex - 1]
      : null;

  const displayedCp =
    evaluationIndex === 0
      ? analysis?.initial_evaluation_cp ?? 0
      : evaluatedMove?.evaluation_cp ?? 0;

  const displayedMate =
    evaluationIndex === 0
      ? analysis?.initial_evaluation_mate ?? null
      : evaluatedMove?.evaluation_mate ?? null;

  const whitePercentage =
    100 /
    (1 +
      Math.exp(
        -Math.max(-2000, Math.min(2000, displayedCp)) / 220,
      ));

  function selectMove(ply: number) {
    setAutoplay(false);
    setSelectedPly(
      Math.max(0, Math.min(moves.length, ply)),
    );
    setPreviewBest(false);
  }

  // ==========================================================
  // ANALYZE GAME
  // ==========================================================

  async function handleAnalyze() {
    if (!game || analyzing || moves.length === 0) return;

    setAnalysisError(null);
    setAnalyzing(true);
    setPreviewBest(false);
    setAutoplay(false);

    try {
      setAnalysis(await analyzeGame(game.id));
    } catch (cause) {
      setAnalysisError(
        cause instanceof Error
          ? cause.message
          : "Could not analyze game.",
      );
    } finally {
      setAnalyzing(false);
    }
  }

  // ==========================================================
  // KEYBOARD REPLAY
  // ==========================================================

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      const target = event.target;

      if (
        target instanceof HTMLElement &&
        (
          ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName) ||
          target.isContentEditable
        )
      ) {
        return;
      }

      if (event.key === "ArrowRight") {
        event.preventDefault();
        setPreviewBest(false);
        setAutoplay(false);
        setSelectedPly((value) =>
          Math.min(moves.length, value + 1),
        );
      } else if (event.key === "ArrowLeft") {
        event.preventDefault();
        setPreviewBest(false);
        setAutoplay(false);
        setSelectedPly((value) =>
          Math.max(0, value - 1),
        );
      }
    }

    window.addEventListener("keydown", onKeyDown);

    return () => {
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [moves.length]);

  // ==========================================================
  // AUTO SCROLL MOVE LIST
  // ==========================================================

  useEffect(() => {
    const list = moveListRef.current;
    if (!list || selectedPly === 0) return;

    const selected = list.querySelector<HTMLButtonElement>(
      `[data-ply="${selectedPly}"]`,
    );

    if (!selected) return;

    const outer = list.getBoundingClientRect();
    const inner = selected.getBoundingClientRect();

    if (inner.bottom > outer.bottom) {
      list.scrollTop += inner.bottom - outer.bottom + 8;
    } else if (inner.top < outer.top) {
      list.scrollTop -= outer.top - inner.top + 8;
    }
  }, [selectedPly, analysis]);

  // ==========================================================
  // AUTO REPLAY
  // ==========================================================

  useEffect(() => {
    if (!autoplay) return;

    const timer = window.setInterval(() => {
      setPreviewBest(false);

      setSelectedPly((ply) =>
        Math.min(moves.length, ply + 1),
      );
    }, 1100);

    return () => {
      window.clearInterval(timer);
    };
  }, [autoplay, moves.length]);

  useEffect(() => {
    if (autoplay && selectedPly >= moves.length) {
      setAutoplay(false);
    }
  }, [autoplay, selectedPly, moves.length]);

  // ==========================================================
  // LOADING / ERROR
  // ==========================================================

  if (loading) {
    return (
      <div className="page review-page">
        <p>Loading saved game...</p>
      </div>
    );
  }

  if (error || !game) {
    return (
      <div className="page review-page">
        <Link className="review-back" to="/games">
          ← Games
        </Link>

        <div className="error-message">
          {error ?? "Game not found."}
        </div>
      </div>
    );
  }

  // ==========================================================
  // BOARD MARKERS AND PLAYER BARS
  // ==========================================================

  const playedFrom = currentMove?.uci.slice(0, 2);
  const playedTo = currentMove?.uci.slice(2, 4);

  const bestArrow =
    showBest && selectedReview?.best_uci
      ? arrowPoints(selectedReview.best_uci, orientation)
      : null;

  const activeQuality = selectedReview
    ? QUALITY[selectedReview.classification]
    : null;

  const count = (
    color: "white" | "black",
    type: MoveClassification,
  ) =>
    analysis?.summary[color].counts[type] ??
    STARTING_QUALITY_COUNTS[type];

  const topColor =
    orientation === "white" ? "black" : "white";

  const bottomColor = orientation;

  const playerName = (color: "white" | "black") =>
    color === "white" ? game.white : game.black;

  // ==========================================================
  // RENDER
  // ==========================================================

  return (
    <div className="page review-page">

      {/* PAGE HEADER */}

      <header className="review-header">
        <div>
          <Link className="review-back" to="/games">
            ← All saved games
          </Link>

          <h1>Game Review</h1>

          <p>
            {formatDate(game.date)}
            {" · "}
            {game.opening ?? "Unknown opening"}
            {" "}
            {game.eco_code
              ? `(${game.eco_code})`
              : ""}
          </p>
        </div>

        <button
          type="button"
          className="review-analyze-button"
          disabled={analyzing || moves.length === 0}
          onClick={() => void handleAnalyze()}
        >
          {analyzing
            ? "Analyzing with Stockfish..."
            : analysis
              ? "Re-analyze game"
              : "Analyze with Stockfish"}
        </button>
      </header>

      {analysisError && (
        <div className="error-message review-error">
          {analysisError}
        </div>
      )}

      {analyzing && (
        <div className="review-analyzing" role="status">
          <span className="review-spinner" />
          Evaluating moves and classifying game decisions.
          Longer games take more time.
        </div>
      )}

      <div className="review-layout">

        {/* ====================================================
            LEFT - BOARD WITH PLAYER NAMES
        ==================================================== */}

        <section
          className="review-board-panel"
          aria-label="Game board and players"
        >

          {/* TOP PLAYER */}

          <div className="review-player-bar review-player-top">
            <span
              className={`review-player-avatar ${topColor}`}
              aria-hidden="true"
            >
              {topColor === "white" ? "♙" : "♟"}
            </span>

            <div className="review-player-details">
              <strong>{playerName(topColor)}</strong>
              <span>
                {topColor === "white" ? "White" : "Black"}
              </span>
            </div>

            <button
              type="button"
              className="review-flip-button"
              onClick={() =>
                setOrientation((value) =>
                  value === "white" ? "black" : "white"
                )
              }
              title="Flip board"
            >
              <span aria-hidden="true">⇅</span>
              Flip board
            </button>
          </div>

          {/* BOARD + EVALUATION BAR */}

          <div className="review-board-and-eval">
            {analysis ? (
              <div
                className="review-eval-meter"
                aria-label={`Evaluation for White: ${
                  evalText(displayedCp, displayedMate)
                }`}
              >
                <div className="review-eval-black" />

                <div
                  className="review-eval-white"
                  style={{
                    height: `${whitePercentage}%`,
                  }}
                />

                <span>
                  {evalText(displayedCp, displayedMate)}
                </span>
              </div>
            ) : (
              <div
                className="review-eval-placeholder"
                aria-hidden="true"
              />
            )}

            <div className="review-board">
              {currentFen ? (
                <div className="review-board-surface">
                  <LiveChessBoard
                    fen={currentFen}
                    orientation={orientation}
                  />

                  <div
                    className="review-board-overlay"
                    aria-hidden="true"
                  >
                    {showBest && bestArrow ? (
                      <svg
                        className="review-best-arrow"
                        viewBox="0 0 100 100"
                        preserveAspectRatio="none"
                      >
                        <defs>
                          <marker
                            id="review-best-head"
                            markerWidth="7"
                            markerHeight="7"
                            refX="5"
                            refY="3"
                            orient="auto"
                          >
                            <path
                              d="M0,0 L0,6 L6,3 Z"
                              fill="#74c9e7"
                            />
                          </marker>
                        </defs>

                        <line
                          x1={bestArrow.x1}
                          y1={bestArrow.y1}
                          x2={bestArrow.x2}
                          y2={bestArrow.y2}
                          stroke="#74c9e7"
                          strokeWidth="1.8"
                          strokeLinecap="round"
                          markerEnd="url(#review-best-head)"
                          opacity="0.85"
                        />
                      </svg>
                    ) : currentMove && playedFrom && playedTo ? (
                      <>
                        <div
                          className="review-highlight-square from"
                          style={squareStyle(playedFrom, orientation)}
                        />

                        <div
                          className="review-highlight-square to"
                          style={squareStyle(playedTo, orientation)}
                        />

                        {activeQuality && selectedReview && (
                          <div
                            className="review-marker-square"
                            style={squareStyle(playedTo, orientation)}
                          >
                            <span
                              className={`review-board-badge class-${
                                selectedReview.classification
                              }`}
                            >
                              {activeQuality.symbol}
                            </span>
                          </div>
                        )}
                      </>
                    ) : null}
                  </div>
                </div>
              ) : (
                <p>No saved board position available.</p>
              )}
            </div>
          </div>

          {/* BOTTOM PLAYER */}

          <div className="review-player-bar review-player-bottom">
            <span
              className={`review-player-avatar ${bottomColor}`}
              aria-hidden="true"
            >
              {bottomColor === "white" ? "♙" : "♟"}
            </span>

            <div className="review-player-details">
              <strong>{playerName(bottomColor)}</strong>
              <span>
                {bottomColor === "white" ? "White" : "Black"}
              </span>
            </div>

            <span
              className="review-result"
              title="Game result"
            >
              {game.result}
            </span>
          </div>

          <p className="review-board-caption">
            {showBest
              ? "Stockfish suggestion · position before the selected move"
              : `Position ${selectedPly} of ${moves.length}`}
          </p>
        </section>

        {/* ====================================================
            RIGHT - GAME REVIEW
        ==================================================== */}

        <aside className="review-side-panel">

          {/* STOCKFISH COMMENTARY */}

          <section className="review-card review-coach-card">
            <div className="review-coach-heading">
              <span
                className="review-coach-title-icon"
                aria-hidden="true"
              >
                ★
              </span>

              <strong>Game Review</strong>

              <span className="review-coach-engine">
                Stockfish
              </span>
            </div>

            <div className="review-coach-body">
              <span
                className="review-coach-avatar"
                aria-hidden="true"
              >
                ♞
              </span>

              <div className="review-coach-bubble">
                {selectedReview && activeQuality ? (
                  <>
                    <div className="review-coach-bubble-top">
                      <span
                        className={`review-move-symbol review-coach-quality class-${
                          selectedReview.classification
                        }`}
                      >
                        {activeQuality.symbol}
                      </span>

                      <strong>
                        {reviewHeadline(selectedReview)}
                      </strong>

                      <span className="review-coach-score">
                        {evalText(
                          selectedReview.evaluation_cp,
                          selectedReview.evaluation_mate,
                        )}
                      </span>
                    </div>

                    <p>
                      {selectedReview.classification_reason}
                    </p>
                  </>
                ) : analysis ? (
                  <>
                    <strong>Start of the game</strong>
                    <p>
                      Select a move to see its classification,
                      evaluation and the engine's best alternative.
                    </p>
                  </>
                ) : (
                  <>
                    <strong>Ready to review this game?</strong>
                    <p>
                      Replay the saved moves, then select
                      Analyze with Stockfish to see move-quality
                      symbols and explanations.
                    </p>
                  </>
                )}
              </div>
            </div>

            {selectedReview && (
              <div className="review-coach-details">
                <span>
                  Played by{" "}
                  <strong>
                    {selectedReview.color === "white"
                      ? game.white
                      : game.black}
                  </strong>
                </span>

                <span>
                  Estimated accuracy{" "}
                  <strong>
                    {selectedReview.accuracy.toFixed(1)}%
                  </strong>
                </span>
              </div>
            )}

            {/* BEST MOVE CONTROL MOVED TO RIGHT SIDE */}

            <div className="review-coach-actions">
              <button
                type="button"
                className={`review-best-preview-button${
                  showBest ? " active" : ""
                }`}
                disabled={!bestAlternative}
                onClick={() => {
                  setAutoplay(false);
                  setPreviewBest((value) => !value);
                }}
                title={
                  bestAlternative
                    ? `Stockfish suggests ${selectedReview?.best_san}`
                    : "This is already the engine's first choice, or analysis is not available."
                }
              >
                <span aria-hidden="true">★</span>

                {showBest
                  ? `Played: ${currentMove?.san}`
                  : bestAlternative
                    ? `Best: ${selectedReview?.best_san}`
                    : "Best move"}
              </button>

              <button
                type="button"
                className="review-next-button"
                disabled={selectedPly === moves.length}
                onClick={() =>
                  selectMove(selectedPly + 1)
                }
              >
                Next{" "}
                <span aria-hidden="true">→</span>
              </button>
            </div>

            {showBest && (
              <p className="review-best-note">
                Showing the position before the played move,
                with Stockfish's proposed move marked by the
                blue arrow.
              </p>
            )}
          </section>

          {/* MOVE LIST */}

          <section className="review-card review-moves-card">
            <div className="review-card-heading">
              <h2>Moves</h2>
              <span>{moves.length} half-moves</span>
            </div>

            <div
              className="review-moves-list"
              ref={moveListRef}
            >
              {rows.length === 0 ? (
                <p className="review-muted">
                  No moves were saved.
                </p>
              ) : (
                rows.map((row) => (
                  <div
                    className="review-move-row"
                    key={row.number}
                  >
                    <span className="review-move-number">
                      {row.number}.
                    </span>

                    {([row.white, row.black] as const).map(
                      (move, column) => {
                        if (!move) {
                          return <span key={column} />;
                        }

                        const review = analysis?.moves.find(
                          (entry) =>
                            entry.ply === move.ply,
                        );

                        return (
                          <button
                            key={move.ply}
                            data-ply={
                              moves.indexOf(move) + 1
                            }
                            type="button"
                            className={
                              `review-move-button${
                                currentMove?.ply === move.ply
                                  ? " selected"
                                  : ""
                              }${
                                review
                                  ? ` class-${review.classification}`
                                  : ""
                              }`
                            }
                            onClick={() =>
                              selectMove(
                                moves.indexOf(move) + 1,
                              )
                            }
                            title={
                              review
                                ? `${QUALITY[review.classification].label}: ${review.classification_reason}`
                                : move.san
                            }
                          >
                            {review && (
                              <span
                                className={`review-move-symbol class-${
                                  review.classification
                                }`}
                              >
                                {QUALITY[review.classification].symbol}
                              </span>
                            )}

                            <span className="review-move-san">
                              {move.san}
                            </span>
                          </button>
                        );
                      },
                    )}
                  </div>
                ))
              )}
            </div>
          </section>

          {/* EVALUATION GRAPH */}

          {analysis && (
            <EvaluationChart
              analysis={analysis}
              selectedPly={evaluationIndex}
              onSelect={selectMove}
            />
          )}

          {/* GAME REPLAY CONTROLS */}

          <div
            className="review-playback"
            aria-label="Game replay controls"
          >
            <button
              type="button"
              onClick={() => selectMove(0)}
              disabled={selectedPly === 0}
              aria-label="First position"
              title="First position"
            >
              |◀
            </button>

            <button
              type="button"
              onClick={() =>
                selectMove(selectedPly - 1)
              }
              disabled={selectedPly === 0}
              aria-label="Previous move"
              title="Previous move"
            >
              ◀
            </button>

            <button
              type="button"
              className="review-autoplay-button"
              disabled={
                moves.length === 0 ||
                (!autoplay && selectedPly === moves.length)
              }
              onClick={() => {
                setPreviewBest(false);
                setAutoplay((value) => !value);
              }}
              aria-label={
                autoplay
                  ? "Pause replay"
                  : "Play moves automatically"
              }
              title={autoplay ? "Pause" : "Auto replay"}
            >
              {autoplay ? "❚❚" : "▶"}
            </button>

            <button
              type="button"
              onClick={() =>
                selectMove(selectedPly + 1)
              }
              disabled={selectedPly === moves.length}
              aria-label="Next move"
              title="Next move"
            >
              ▶
            </button>

            <button
              type="button"
              onClick={() => selectMove(moves.length)}
              disabled={selectedPly === moves.length}
              aria-label="Last position"
              title="Last position"
            >
              ▶|
            </button>
          </div>

          <p className="review-keyboard-hint">
            {currentMove
              ? `${
                  currentMove.move_number
                }${
                  currentMove.color === "white"
                    ? "."
                    : "..."
                } ${currentMove.san}`
              : "Start position"}

            {" · "} Use ← / → to step through moves
          </p>

          {/* ACCURACY AND MOVE QUALITY COUNTS */}

          {analysis && (
            <section className="review-card review-summary-card">
              <h2>Estimated game accuracy</h2>

              <div className="review-accuracy-grid">
                <div>
                  <span>{game.white}</span>

                  <strong>
                    {analysis.summary.white.accuracy?.toFixed(1) ?? "—"}%
                  </strong>

                  <small>White</small>
                </div>

                <div>
                  <span>{game.black}</span>

                  <strong>
                    {analysis.summary.black.accuracy?.toFixed(1) ?? "—"}%
                  </strong>

                  <small>Black</small>
                </div>
              </div>

              <div className="review-quality-breakdown">
                <div className="review-breakdown-header">
                  <span>Move quality</span>
                  <span>White</span>
                  <span>Black</span>
                </div>

                {QUALITY_ORDER.map((type) => {
                  const whiteCount = count("white", type);
                  const blackCount = count("black", type);

                  const highest = Math.max(
                    1,
                    whiteCount,
                    blackCount,
                  );

                  return (
                    <div
                      className="review-breakdown-row"
                      key={type}
                    >
                      <div className="review-breakdown-name">
                        <span
                          className={`review-breakdown-icon class-${type}`}
                        >
                          {QUALITY[type].symbol}
                        </span>

                        <span>{QUALITY[type].label}</span>
                      </div>

                      <div className="review-breakdown-count">
                        <strong>{whiteCount}</strong>

                        <span className="review-count-bar">
                          <i
                            style={{
                              width: `${
                                (whiteCount / highest) * 100
                              }%`,
                            }}
                          />
                        </span>
                      </div>

                      <div className="review-breakdown-count">
                        <strong>{blackCount}</strong>

                        <span className="review-count-bar">
                          <i
                            style={{
                              width: `${
                                (blackCount / highest) * 100
                              }%`,
                            }}
                          />
                        </span>
                      </div>
                    </div>
                  );
                })}
              </div>

              <p className="review-disclaimer">
                {analysis.method}
                {" "}Quick review:{" "}
                {analysis.seconds_per_position}s/position.
                Accuracy and all labels are estimates,
                not Chess.com scoring.
              </p>
            </section>
          )}
        </aside>
      </div>

      {/* SAVED PGN */}

      <section className="review-card review-pgn">
        <h2>Saved PGN</h2>
        <pre>{game.pgn ?? "No PGN stored."}</pre>
      </section>
    </div>
  );
}
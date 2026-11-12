import {
  useEffect,
  useMemo,
  useState,
} from "react";

import {
  Link,
  useParams,
} from "react-router-dom";

import {
  analyzeGame,
  getGame,
} from "../api/games";

import LiveChessBoard
  from "../components/chess/LiveChessBoard";

import type {
  GameAnalysis,
  MoveClassification,
  ReviewedMove,
  SavedGameDetail,
  SaveGameMove,
} from "../types/game";

import "./GameDetailPage.css";


// ============================================================
// MOVE CLASSIFICATION
// ============================================================

const CLASSIFICATION_LABELS:
  Record<MoveClassification, string> = {
    best: "Best",
    excellent: "Excellent",
    good: "Good",
    inaccuracy: "Inaccuracy",
    mistake: "Mistake",
    blunder: "Blunder",
  };


// ============================================================
// EVALUATION DISPLAY
// ============================================================

function evalText(
  cp: number,
  mate: number | null,
): string {

  if (mate !== null) {
    return mate > 0
      ? `M${mate}`
      : `-M${-mate}`;
  }

  const pawns = cp / 100;

  return (
    `${pawns > 0 ? "+" : ""}${pawns.toFixed(2)}`
  );
}


// ============================================================
// DATE FORMATTING
// ============================================================

function formatDate(
  value: string | null,
): string {

  if (!value) {
    return "—";
  }

  const date = new Date(value);

  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleString("vi-VN");
}


// ============================================================
// MOVE ROWS
// ============================================================

function groupMoves(
  moves: SaveGameMove[],
) {

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
// EVALUATION CHART
// ============================================================

function EvaluationChart({
  analysis,
  selectedPly,
}: {
  analysis: GameAnalysis;
  selectedPly: number;
}) {

  const values = [
    analysis.initial_evaluation_cp,
    ...analysis.moves.map(
      (move) => move.evaluation_cp
    ),
  ];

  const last = Math.max(
    1,
    values.length - 1,
  );

  const x = (index: number) =>
    (index / last) * 640;

  const y = (cp: number) =>
    54 - (
      Math.max(
        -900,
        Math.min(900, cp),
      ) / 900
    ) * 42;

  const points = values
    .map(
      (value, index) =>
        `${x(index)},${y(value)}`
    )
    .join(" ");

  const marker = Math.min(
    values.length - 1,
    selectedPly,
  );

  return (
    <div className="review-chart-card">

      <div className="review-card-heading">
        <h3>Evaluation graph</h3>

        <span>
          White above · Black below
        </span>
      </div>

      <svg
        viewBox="0 0 640 108"
        role="img"
        aria-label={
          "Stockfish evaluation across the saved game"
        }
        className="review-eval-chart"
      >

        <rect
          x="0"
          y="0"
          width="640"
          height="54"
          fill="#253d56"
          opacity="0.65"
        />

        <rect
          x="0"
          y="54"
          width="640"
          height="54"
          fill="#142033"
        />

        <line
          x1="0"
          y1="54"
          x2="640"
          y2="54"
          stroke="#8495aa"
          strokeDasharray="4 4"
        />

        <polyline
          fill="none"
          stroke="#69c7ea"
          strokeWidth="2.8"
          points={points}
        />

        <line
          x1={x(marker)}
          y1="0"
          x2={x(marker)}
          y2="108"
          stroke="#f9ce71"
          strokeWidth="1.5"
        />

        <circle
          cx={x(marker)}
          cy={y(values[marker])}
          r="5"
          fill="#f9ce71"
        />

      </svg>
    </div>
  );
}


// ============================================================
// GAME REVIEW PAGE
// ============================================================

export default function GameDetailPage() {

  const { id } = useParams();

  const gameId = Number(id);

  const [
    game,
    setGame,
  ] = useState<SavedGameDetail | null>(null);

  const [
    analysis,
    setAnalysis,
  ] = useState<GameAnalysis | null>(null);

  const [
    selectedPly,
    setSelectedPly,
  ] = useState(0);

  const [
    orientation,
    setOrientation,
  ] = useState<"white" | "black">("white");

  const [
    loading,
    setLoading,
  ] = useState(true);

  const [
    analyzing,
    setAnalyzing,
  ] = useState(false);

  const [
    error,
    setError,
  ] = useState<string | null>(null);

  const [
    analysisError,
    setAnalysisError,
  ] = useState<string | null>(null);


  // ==========================================================
  // LOAD SAVED GAME
  // ==========================================================

  useEffect(() => {

    let active = true;

    setLoading(true);
    setError(null);
    setAnalysis(null);
    setSelectedPly(0);

    if (
      !Number.isSafeInteger(gameId) ||
      gameId < 1
    ) {
      setError("Invalid game ID.");
      setLoading(false);
      return;
    }

    getGame(gameId)
      .then((data) => {
        if (active) {
          setGame(data);
        }
      })
      .catch((cause: unknown) => {

        if (active) {
          setError(
            cause instanceof Error
              ? cause.message
              : "Could not load game.",
          );

          setGame(null);
        }
      })
      .finally(() => {
        if (active) {
          setLoading(false);
        }
      });

    return () => {
      active = false;
    };

  }, [gameId]);


  // ==========================================================
  // REPLAY STATE
  // ==========================================================

  const moves = useMemo(
    () => game?.move_list ?? [],
    [game],
  );

  const rows = useMemo(
    () => groupMoves(moves),
    [moves],
  );

  const currentMove =
    selectedPly > 0
      ? moves[selectedPly - 1]
      : null;

  const selectedReview:
    ReviewedMove | undefined =
      analysis?.moves.find(
        (move) =>
          move.ply === currentMove?.ply,
      );

  const currentFen =
    currentMove?.fen_after ??
    game?.initial_fen;

  const displayedCp =
    selectedPly === 0
      ? (
          analysis?.initial_evaluation_cp ?? 0
        )
      : (
          selectedReview?.evaluation_cp ?? 0
        );

  const displayedMate =
    selectedPly === 0
      ? (
          analysis?.initial_evaluation_mate ?? null
        )
      : (
          selectedReview?.evaluation_mate ?? null
        );

  const whitePercentage =
    100 / (
      1 + Math.exp(
        -Math.max(
          -2000,
          Math.min(2000, displayedCp),
        ) / 220,
      )
    );


  // ==========================================================
  // ANALYZE GAME
  // ==========================================================

  async function handleAnalyze() {

    if (
      !game ||
      analyzing ||
      !moves.length
    ) {
      return;
    }

    setAnalysisError(null);
    setAnalyzing(true);

    try {
      const report = await analyzeGame(game.id);

      setAnalysis(report);

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
  // KEYBOARD NAVIGATION
  // ==========================================================

  useEffect(() => {

    function onKeyDown(
      event: KeyboardEvent,
    ) {

      const target = event.target;

      if (
        target instanceof HTMLElement &&
        (
          target.tagName === "INPUT" ||
          target.tagName === "TEXTAREA" ||
          target.tagName === "SELECT"
        )
      ) {
        return;
      }

      if (event.key === "ArrowRight") {
        event.preventDefault();

        setSelectedPly(
          (value) =>
            Math.min(
              moves.length,
              value + 1,
            ),
        );
      }

      if (event.key === "ArrowLeft") {
        event.preventDefault();

        setSelectedPly(
          (value) =>
            Math.max(
              0,
              value - 1,
            ),
        );
      }
    }

    window.addEventListener(
      "keydown",
      onKeyDown,
    );

    return () => {
      window.removeEventListener(
        "keydown",
        onKeyDown,
      );
    };

  }, [moves.length]);


  // ==========================================================
  // LOADING
  // ==========================================================

  if (loading) {
    return (
      <div className="page review-page">
        <p>Loading saved game...</p>
      </div>
    );
  }


  // ==========================================================
  // ERROR
  // ==========================================================

  if (error || !game) {
    return (
      <div className="page review-page">

        <Link
          className="review-back"
          to="/games"
        >
          ← Games
        </Link>

        <div className="error-message">
          {error ?? "Game not found."}
        </div>

      </div>
    );
  }


  // ==========================================================
  // RENDER
  // ==========================================================

  return (
    <div className="page review-page">

      {/* HEADER */}

      <div className="review-header">

        <div>
          <Link
            className="review-back"
            to="/games"
          >
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
          disabled={
            analyzing ||
            moves.length === 0
          }
          onClick={() =>
            void handleAnalyze()
          }
        >
          {analyzing
            ? "Analyzing moves..."
            : analysis
              ? "Analyze again"
              : "Analyze with Stockfish"}
        </button>

      </div>


      {/* ENGINE ERROR */}

      {analysisError && (
        <div className="error-message review-error">
          {analysisError}
        </div>
      )}


      {/* PLAYERS */}

      <div className="review-match">

        <strong>
          {game.white}
        </strong>

        <span>vs</span>

        <strong>
          {game.black}
        </strong>

        <span className="review-result">
          {game.result}
        </span>

      </div>


      {/* MAIN LAYOUT */}

      <div className="review-layout">

        {/* LEFT - BOARD */}

        <section className="review-board-panel">

          <div className="review-board-heading">

            <span>
              Move {selectedPly} / {moves.length}
            </span>

            <button
              type="button"
              onClick={() =>
                setOrientation(
                  (value) =>
                    value === "white"
                      ? "black"
                      : "white"
                )
              }
            >
              Flip board
            </button>

          </div>


          {/* BOARD AND EVALUATION BAR */}

          <div className="review-board-and-eval">

            {analysis && (

              <div
                className="review-eval-meter"
                aria-label={
                  `White evaluation ${
                    evalText(
                      displayedCp,
                      displayedMate,
                    )
                  }`
                }
              >

                <div className="review-eval-black" />

                <div
                  className="review-eval-white"
                  style={{
                    height:
                      `${whitePercentage}%`,
                  }}
                />

                <span>
                  {evalText(
                    displayedCp,
                    displayedMate,
                  )}
                </span>

              </div>
            )}


            <div className="review-board">

              {currentFen ? (

                <LiveChessBoard
                  fen={currentFen}
                  orientation={orientation}
                />

              ) : (

                <p>
                  No saved board position available.
                </p>

              )}

            </div>

          </div>


          {/* REPLAY CONTROLS */}

          <div
            className="review-playback"
            aria-label="Game replay controls"
          >

            <button
              type="button"
              onClick={() =>
                setSelectedPly(0)
              }
              disabled={selectedPly === 0}
              aria-label="First position"
            >
              |◀
            </button>

            <button
              type="button"
              onClick={() =>
                setSelectedPly(
                  (value) =>
                    Math.max(
                      0,
                      value - 1,
                    )
                )
              }
              disabled={selectedPly === 0}
              aria-label="Previous move"
            >
              ◀
            </button>

            <span>
              {currentMove
                ? (
                    `${
                      currentMove.move_number
                    }${
                      currentMove.color === "white"
                        ? "."
                        : "..."
                    } ${
                      currentMove.san
                    }`
                  )
                : "Start position"}
            </span>

            <button
              type="button"
              onClick={() =>
                setSelectedPly(
                  (value) =>
                    Math.min(
                      moves.length,
                      value + 1,
                    )
                )
              }
              disabled={
                selectedPly === moves.length
              }
              aria-label="Next move"
            >
              ▶
            </button>

            <button
              type="button"
              onClick={() =>
                setSelectedPly(moves.length)
              }
              disabled={
                selectedPly === moves.length
              }
              aria-label="Last position"
            >
              ▶|
            </button>

          </div>


          <p className="review-keyboard-hint">
            Use ← / → to step through moves.
          </p>


          {/* EVALUATION GRAPH */}

          {analysis && (
            <EvaluationChart
              analysis={analysis}
              selectedPly={selectedPly}
            />
          )}

        </section>


        {/* RIGHT - MOVE LIST AND ANALYSIS */}

        <aside className="review-side-panel">

          {/* MOVE LIST */}

          <section className="review-card">

            <div className="review-card-heading">
              <h2>Moves</h2>

              <span>
                {moves.length} half-moves
              </span>
            </div>

            <div className="review-moves-list">

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

                    {(
                      [row.white, row.black] as const
                    ).map((move, column) => {

                      if (!move) {
                        return (
                          <span key={column} />
                        );
                      }

                      const review = analysis?.moves.find(
                        (entry) =>
                          entry.ply === move.ply
                      );

                      return (
                        <button
                          key={move.ply}
                          type="button"

                          className={
                            `review-move-button${
                              currentMove?.ply === move.ply
                                ? " selected"
                                : ""
                            }`
                          }

                          onClick={() =>
                            setSelectedPly(
                              moves.indexOf(move) + 1
                            )
                          }

                          title={
                            review
                              ? CLASSIFICATION_LABELS[
                                  review.classification
                                ]
                              : move.san
                          }
                        >

                          {move.san}

                          {review && (

                            <span
                              className={
                                `review-move-symbol class-${
                                  review.classification
                                }`
                              }
                            >

                              {review.classification === "best"
                                ? "★"
                                : review.classification === "excellent"
                                  ? "✓"
                                  : review.classification === "good"
                                    ? "·"
                                    : review.classification === "inaccuracy"
                                      ? "?!"
                                      : review.classification === "mistake"
                                        ? "?"
                                        : "??"}
                            </span>

                          )}

                        </button>
                      );
                    })}

                  </div>

                ))

              )}

            </div>

          </section>


          {/* SELECTED MOVE ANALYSIS */}

          <section className="review-card review-details-card">

            <h2>
              {analysis
                ? "Move analysis"
                : "Engine analysis"}
            </h2>

            {!analysis ? (

              <p className="review-muted">
                Click <strong>Analyze with Stockfish</strong>
                {" "}to evaluate each saved move,
                show best moves,
                and estimate accuracy.
              </p>

            ) : selectedReview ? (

              <div className="review-move-details">

                <div className="review-classification">

                  <span
                    className={
                      `review-class-tag class-${
                        selectedReview.classification
                      }`
                    }
                  >
                    {CLASSIFICATION_LABELS[
                      selectedReview.classification
                    ]}
                  </span>

                  <strong>
                    {selectedReview.san}
                  </strong>

                </div>


                <div>
                  <span>Played by</span>

                  <strong>
                    {selectedReview.color === "white"
                      ? game.white
                      : game.black}
                  </strong>
                </div>


                <div>
                  <span>
                    Best move before playing
                  </span>

                  <strong>
                    {selectedReview.best_san ?? "—"}
                  </strong>
                </div>


                <div>
                  <span>
                    Evaluation (White)
                  </span>

                  <strong>
                    {evalText(
                      selectedReview.evaluation_cp,
                      selectedReview.evaluation_mate,
                    )}
                  </strong>
                </div>


                <div>
                  <span>
                    Estimated move accuracy
                  </span>

                  <strong>
                    {selectedReview.accuracy.toFixed(1)}%
                  </strong>
                </div>

              </div>

            ) : (

              <p className="review-muted">
                Select a move to see the engine's
                evaluation and recommended move.
              </p>

            )}

          </section>


          {/* GAME ANALYSIS SUMMARY */}

          {analysis && (

            <section className="review-card">

              <h2>Estimated game accuracy</h2>

              <div className="review-accuracy-grid">

                <div>
                  <span>{game.white}</span>

                  <strong>
                    {analysis.summary.white.accuracy?.toFixed(1)
                      ?? "—"}%
                  </strong>

                  <small>White</small>
                </div>


                <div>
                  <span>{game.black}</span>

                  <strong>
                    {analysis.summary.black.accuracy?.toFixed(1)
                      ?? "—"}%
                  </strong>

                  <small>Black</small>
                </div>

              </div>


              <table className="review-summary-table">

                <thead>
                  <tr>
                    <th>Move quality</th>
                    <th>White</th>
                    <th>Black</th>
                  </tr>
                </thead>

                <tbody>

                  {(
                    Object.keys(
                      CLASSIFICATION_LABELS
                    ) as MoveClassification[]
                  ).map((label) => (

                    <tr key={label}>

                      <td>
                        <span
                          className={
                            `class-${label}`
                          }
                        >
                          ●
                        </span>
                        {" "}
                        {CLASSIFICATION_LABELS[label]}
                      </td>

                      <td>
                        {analysis.summary.white.counts[label]}
                      </td>

                      <td>
                        {analysis.summary.black.counts[label]}
                      </td>

                    </tr>

                  ))}

                </tbody>

              </table>


              <p className="review-disclaimer">
                {analysis.method}
                {" "}
                Quick engine review
                {" "}
                ({analysis.seconds_per_position}s/position).
                Accuracy is an estimate,
                not Chess.com scoring.
              </p>

            </section>

          )}

        </aside>

      </div>


      {/* SAVED PGN */}

      <section className="review-card review-pgn">

        <h2>Saved PGN</h2>

        <pre>
          {game.pgn ?? "No PGN stored."}
        </pre>

      </section>

    </div>
  );
}
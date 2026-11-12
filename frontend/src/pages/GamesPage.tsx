import {
  useEffect,
  useState,
} from "react";

import {
  Link,
} from "react-router-dom";

import {
  getGames,
} from "../api/games";

import type {
  GameHistoryItem,
} from "../types/game";

import "./GamesPage.css";


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

  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return date.toLocaleString(
    "vi-VN",
    {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    },
  );
}


// ============================================================
// GAMES HISTORY PAGE
// ============================================================

export default function GamesPage() {

  const [
    games,
    setGames,
  ] = useState<GameHistoryItem[]>([]);

  const [
    loading,
    setLoading,
  ] = useState(true);

  const [
    error,
    setError,
  ] = useState<string | null>(null);


  // =========================================================
  // LOAD GAMES
  // =========================================================

  async function loadGames() {
    setLoading(true);
    setError(null);

    try {
      const data = await getGames();
      setGames(data);

    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Could not load games.",
      );

    } finally {
      setLoading(false);
    }
  }


  useEffect(() => {
    void loadGames();
  }, []);


  // =========================================================
  // RENDER
  // =========================================================

  return (
    <div className="page games-page">

      {/* HEADER */}

      <div className="games-header">

        <div>
          <h1>Games History</h1>

          <p className="page-description">
            Games saved in MySQL.
            Opening recognition is performed
            when a game is saved.
            Select a game to replay its moves
            and review it with Stockfish.
          </p>
        </div>

        <button
          type="button"
          className="games-refresh-button"
          disabled={loading}
          onClick={loadGames}
        >
          {loading ? "Loading..." : "Refresh"}
        </button>

      </div>


      {/* ERROR */}

      {error && (
        <div className="error-message games-error">
          {error}
        </div>
      )}


      {/* HISTORY TABLE */}

      <section className="games-table-card">

        {loading && games.length === 0 ? (

          <div className="games-empty">
            Loading games...
          </div>

        ) : games.length === 0 ? (

          <div className="games-empty">
            <strong>No saved games yet.</strong>

            <span>
              Finish a Live Game
              and press End &amp; Save.
            </span>
          </div>

        ) : (

          <div className="games-table-wrapper">

            <table className="games-table">

              <thead>
                <tr>
                  <th>Date</th>
                  <th>White</th>
                  <th>Black</th>
                  <th>Result</th>
                  <th>Opening</th>
                  <th>Moves</th>
                  <th>Review</th>
                </tr>
              </thead>


              <tbody>

                {games.map((game) => (

                  <tr key={game.id}>

                    <td className="game-date">
                      {formatDate(game.date)}
                    </td>

                    <td className="game-player">
                      {game.white}
                    </td>

                    <td className="game-player">
                      {game.black}
                    </td>

                    <td>
                      <span className="game-result">
                        {game.result}
                      </span>
                    </td>

                    <td>
                      {game.opening ?? "—"}
                    </td>

                    <td className="game-moves">
                      {game.moves}
                    </td>

                    <td>
                      <Link
                        className="games-review-link"
                        to={`/games/${game.id}`}
                        aria-label={
                          `Replay and analyze game ${game.id}`
                        }
                      >
                        Replay / Analyze
                      </Link>
                    </td>

                  </tr>

                ))}

              </tbody>

            </table>

          </div>

        )}

      </section>

    </div>
  );
}
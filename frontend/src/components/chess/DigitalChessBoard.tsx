import {
  useMemo,
  useState,
} from "react";

import {
  Chess,
} from "chess.js";

import {
  Chessboard,
} from "react-chessboard";


interface Props {
  boardFen: string;

  initialTurn:
    "w"
    |
    "b";
}


// ============================================================
// SAFE CHESS CREATION
// ============================================================

function createChessSafely(
  boardFen: string,
  initialTurn: "w" | "b",
): {
  game: Chess | null;
  error: string | null;
} {

  const fullFen =
    `${boardFen} ${initialTurn} - - 0 1`;


  try {

    const game =
      new Chess(
        fullFen,
      );


    return {
      game,
      error: null,
    };

  } catch (error) {

    let message =
      "Recognized position is not a legal chess position.";


    if (
      error instanceof Error
    ) {

      message =
        error.message;
    }


    return {
      game: null,
      error: message,
    };
  }
}


// ============================================================
// COMPONENT
// ============================================================

export default function DigitalChessBoard({
  boardFen,
  initialTurn,
}: Props) {

  const initialState =
    createChessSafely(
      boardFen,
      initialTurn,
    );


  const [
    game,
    setGame,
  ] = useState<Chess | null>(
    initialState.game,
  );


  const [
    error,
    setError,
  ] = useState<string | null>(
    initialState.error,
  );


  // =========================================================
  // DISPLAY FEN
  // =========================================================
  //
  // Even if chess.js rejects the position,
  // react-chessboard can still receive the recognized FEN
  // so the user can inspect what CV detected.
  //
  // =========================================================

  const displayFen =
    game
      ?
      game.fen()
      :
      `${boardFen} ${initialTurn} - - 0 1`;


  // =========================================================
  // MOVE
  // =========================================================

  function makeMove(
    sourceSquare: string,
    targetSquare: string,
  ) {

    // Invalid recognition:
    // do not allow interactive moves.

    if (!game) {

      setError(
        "This recognized position is invalid, so moves are disabled.",
      );

      return false;
    }


    const gameCopy =
      new Chess(
        game.fen(),
      );


    try {

      const move =
        gameCopy.move({
          from:
            sourceSquare,

          to:
            targetSquare,

          promotion:
            "q",
        });


      if (!move) {

        return false;
      }


      setGame(
        gameCopy,
      );


      setError(
        null,
      );


      return true;

    } catch {

      setError(
        "Illegal move",
      );


      return false;
    }
  }


  // =========================================================
  // BOARD OPTIONS
  // =========================================================

  const options =
    useMemo(
      () => ({

        position:
          displayFen,

        boardOrientation:
          "white" as const,


        // ====================================================
        // MAGNUS ACADEMY-LIKE THEME
        // ====================================================

        lightSquareStyle: {
          backgroundColor:
            "#eef6f8",
        },

        darkSquareStyle: {
          backgroundColor:
            "#91d5e5",
        },


        boardStyle: {

          border:
            "4px solid #7fc9da",

          borderRadius:
            "3px",

          boxShadow:
            "0 4px 14px rgba(0, 0, 0, 0.18)",
        },


        lightSquareNotationStyle: {

          color:
            "#5b9aaa",

          fontSize:
            "11px",

          fontWeight:
            "600",
        },


        darkSquareNotationStyle: {

          color:
            "#f3fbfd",

          fontSize:
            "11px",

          fontWeight:
            "600",
        },


        showNotation:
          true,


        animationDurationInMs:
          180,


        onPieceDrop: ({
          sourceSquare,
          targetSquare,
        }: {
          sourceSquare: string;
          targetSquare: string | null;
        }) => {

          if (!targetSquare) {

            return false;
          }


          return makeMove(
            sourceSquare,
            targetSquare,
          );
        },

      }),

      [
        displayFen,
        game,
      ],
    );


  // =========================================================
  // UI
  // =========================================================

  return (

    <div
      className=
        "digital-board-panel"
    >

      <div
        style={{

          width:
            "min(500px, 82vw)",

          margin:
            "0 auto",

        }}
      >

        <Chessboard
          options={
            options
          }
        />

      </div>


      {/* ===================================================
          RECOGNITION / CHESS ERROR
      =================================================== */}

      {
        error
        &&
        (
          <div
            className=
              "error-message"

            style={{
              marginTop:
                "16px",
            }}
          >

            <strong>
              Position warning:
            </strong>

            {" "}

            {error}


            {
              game === null
              &&
              (
                <div
                  style={{
                    marginTop:
                      "8px",
                  }}
                >

                  The board is displayed,
                  but interactive moves are disabled
                  because the recognized position
                  is not legal.

                </div>
              )
            }

          </div>
        )
      }


      {/* ===================================================
          FEN
      =================================================== */}

      <div
        className=
          "fen-box"
      >

        <strong>
          Current FEN
        </strong>

        <code>
          {displayFen}
        </code>

      </div>


      {/* ===================================================
          TURN
      =================================================== */}

      <div
        className=
          "turn-box"
      >

        Turn:{" "}

        <strong>

          {
            game
              ?
              (
                game.turn()
                ===
                "w"
                  ?
                  "White"
                  :
                  "Black"
              )
              :
              (
                initialTurn
                ===
                "w"
                  ?
                  "White"
                  :
                  "Black"
              )
          }

        </strong>

      </div>

    </div>
  );
}
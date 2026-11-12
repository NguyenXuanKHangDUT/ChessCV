import {
  useMemo,
} from "react";

import {
  Chessboard,
} from "react-chessboard";


interface Props {
  fen: string;

  orientation?:
    | "white"
    | "black";
}


export default function LiveChessBoard({
  fen,
  orientation = "white",
}: Props) {

  const options =
    useMemo(
      () => ({

        position:
          fen,

        boardOrientation:
          orientation,

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
            "4px",

          boxShadow:
            "0 8px 22px rgba(0, 0, 0, 0.25)",
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

      }),
      [
        fen,
        orientation,
      ],
    );


  return (
    <div
      className=
        "live-digital-board"
    >

      <div
        style={{
          pointerEvents:
            "none",

          width:
            "100%",
        }}
      >

        <Chessboard
          options={
            options
          }
        />

      </div>

    </div>
  );
}
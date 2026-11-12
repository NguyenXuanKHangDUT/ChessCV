import {
  useEffect,
  useRef,
} from "react";

import type {
  Point,
} from "../../types/position";


interface Props {

  imageUrl:
    string;

  points:
    Point[];

  onPointsChange:
    (
      points: Point[],
    ) => void;
}


const LABELS = [
  "OUTER TL",
  "OUTER TR",
  "OUTER BR",
  "OUTER BL",

  "BOARD TL",
  "BOARD TR",
  "BOARD BR",
  "BOARD BL",
];


// ============================================================
// COMPONENT
// ============================================================

export default function PositionCalibration({
  imageUrl,
  points,
  onPointsChange,
}: Props) {

  const canvasRef =
    useRef<HTMLCanvasElement | null>(
      null,
    );


  const imageRef =
    useRef<HTMLImageElement | null>(
      null,
    );


  // =========================================================
  // DRAW
  // =========================================================

  useEffect(() => {

    const canvas =
      canvasRef.current;


    if (!canvas) {

      return;
    }


    const rawContext =
      canvas.getContext(
        "2d",
      );


    if (!rawContext) {

      return;
    }


    // Keep a guaranteed non-null reference.
    const ctx =
      rawContext;


    const image =
      new Image();


    image.onload = () => {

      imageRef.current =
        image;


      const maxWidth =
        1000;


      const scale =
        Math.min(
          1,
          maxWidth
          /
          image.width,
        );


      canvas.width =
        Math.round(
          image.width
          *
          scale,
        );


      canvas.height =
        Math.round(
          image.height
          *
          scale,
        );


      ctx.clearRect(
        0,
        0,
        canvas.width,
        canvas.height,
      );


      ctx.drawImage(
        image,
        0,
        0,
        canvas.width,
        canvas.height,
      );


      // =====================================================
      // POLYGON
      // =====================================================

      function drawPolygon(
        polygonPoints:
          Point[],

        strokeStyle:
          string,
      ) {

        if (
          polygonPoints.length
          ===
          0
        ) {

          return;
        }


        ctx.beginPath();


        ctx.moveTo(
          polygonPoints[0][0]
          *
          scale,

          polygonPoints[0][1]
          *
          scale,
        );


        for (
          let i = 1;
          i <
          polygonPoints.length;
          i++
        ) {

          ctx.lineTo(
            polygonPoints[i][0]
            *
            scale,

            polygonPoints[i][1]
            *
            scale,
          );
        }


        if (
          polygonPoints.length
          ===
          4
        ) {

          ctx.closePath();
        }


        ctx.lineWidth =
          3;


        ctx.strokeStyle =
          strokeStyle;


        ctx.stroke();
      }


      // OUTER

      drawPolygon(
        points.slice(
          0,
          4,
        ),

        "#facc15",
      );


      // BOARD

      drawPolygon(
        points.slice(
          4,
          8,
        ),

        "#22c55e",
      );


      // =====================================================
      // POINTS
      // =====================================================

      points.forEach(
        (
          point,
          index,
        ) => {

          const x =
            point[0]
            *
            scale;


          const y =
            point[1]
            *
            scale;


          ctx.beginPath();


          ctx.arc(
            x,
            y,
            7,
            0,
            Math.PI * 2,
          );


          ctx.fillStyle =
            index < 4
              ?
              "#facc15"
              :
              "#22c55e";


          ctx.fill();


          ctx.lineWidth =
            2;


          ctx.strokeStyle =
            "#000000";


          ctx.stroke();


          ctx.font =
            "14px Arial";


          ctx.fillStyle =
            "#ffffff";


          ctx.fillText(
            `${index + 1}`,
            x + 10,
            y - 10,
          );
        },
      );
    };


    image.src =
      imageUrl;


  }, [
    imageUrl,
    points,
  ]);


  // =========================================================
  // CLICK
  // =========================================================

  function handleClick(
    event:
      React.MouseEvent<HTMLCanvasElement>,
  ) {

    if (
      points.length
      >=
      8
    ) {

      return;
    }


    const canvas =
      canvasRef.current;


    const image =
      imageRef.current;


    if (
      !canvas
      ||
      !image
    ) {

      return;
    }


    const rect =
      canvas.getBoundingClientRect();


    const canvasX =
      (
        event.clientX
        -
        rect.left
      )
      *
      (
        canvas.width
        /
        rect.width
      );


    const canvasY =
      (
        event.clientY
        -
        rect.top
      )
      *
      (
        canvas.height
        /
        rect.height
      );


    const scaleX =
      image.width
      /
      canvas.width;


    const scaleY =
      image.height
      /
      canvas.height;


    const imageX =
      canvasX
      *
      scaleX;


    const imageY =
      canvasY
      *
      scaleY;


    onPointsChange(
      [
        ...points,

        [
          imageX,
          imageY,
        ],
      ],
    );
  }


  // =========================================================
  // UI
  // =========================================================

  return (

    <div
      className=
        "calibration-panel"
    >

      <div
        className=
          "calibration-info"
      >

        {
          points.length < 8
            ?
            (
              <>
                Click point{" "}

                <strong>
                  {
                    points.length
                    +
                    1
                  }
                </strong>

                {" — "}

                {
                  LABELS[
                    points.length
                  ]
                }
              </>
            )
            :
            (
              <strong>
                Calibration complete.
              </strong>
            )
        }

      </div>


      <canvas
        ref={
          canvasRef
        }

        onClick={
          handleClick
        }

        className=
          "calibration-canvas"
      />


      <div
        className=
          "calibration-controls"
      >

        <button
          type="button"

          disabled={
            points.length
            ===
            0
          }

          onClick={() => {

            onPointsChange(
              points.slice(
                0,
                -1,
              ),
            );

          }}
        >
          Undo
        </button>


        <button
          type="button"

          disabled={
            points.length
            ===
            0
          }

          onClick={() => {

            onPointsChange(
              [],
            );

          }}
        >
          Reset points
        </button>

      </div>

    </div>
  );
}
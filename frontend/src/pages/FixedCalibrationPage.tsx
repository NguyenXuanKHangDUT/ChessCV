import {
  useEffect,
  useRef,
  useState,
} from "react";

import type {
  MouseEvent,
} from "react";

import {
  CAMERA_STREAM_URL,
  captureCameraFrame,
} from "../api/camera";

import "./FixedCalibrationPage.css";


const API_URL =
  "http://127.0.0.1:8000/api/calibration/fixed";

const CORNER_LABELS = [
  "TL",
  "TR",
  "BR",
  "BL",
] as const;


type Point = {
  x: number;
  y: number;
};


// ============================================================
// PROJECT A POINT FROM THE UNIT BOARD TO CAMERA QUADRILATERAL
// ============================================================

function projectToQuadrilateral(
  points: Point[],
  u: number,
  v: number,
): Point {

  const [p0, p1, p2, p3] = points;

  const dx1 = p1.x - p2.x;
  const dx2 = p3.x - p2.x;
  const dx3 = p0.x - p1.x + p2.x - p3.x;

  const dy1 = p1.y - p2.y;
  const dy2 = p3.y - p2.y;
  const dy3 = p0.y - p1.y + p2.y - p3.y;

  const determinant =
    dx1 * dy2 - dx2 * dy1;

  let g = 0;
  let h = 0;

  if (Math.abs(determinant) > 1e-9) {
    g = (
      dx3 * dy2 - dx2 * dy3
    ) / determinant;

    h = (
      dx1 * dy3 - dx3 * dy1
    ) / determinant;
  }

  const a =
    p1.x - p0.x + g * p1.x;

  const b =
    p3.x - p0.x + h * p3.x;

  const d =
    p1.y - p0.y + g * p1.y;

  const e =
    p3.y - p0.y + h * p3.y;

  const denominator =
    g * u + h * v + 1;

  return {
    x: (
      a * u + b * v + p0.x
    ) / denominator,

    y: (
      d * u + e * v + p0.y
    ) / denominator,
  };
}


// ============================================================
// PAGE
// ============================================================

export default function FixedCalibrationPage() {

  const [frozenUrl, setFrozenUrl] =
    useState<string | null>(null);

  const [frameSize, setFrameSize] = useState({
    width: 0,
    height: 0,
  });

  const [points, setPoints] =
    useState<Point[]>([]);

  const [loading, setLoading] =
    useState(false);

  const [saving, setSaving] =
    useState(false);

  const [error, setError] =
    useState<string | null>(null);

  const [success, setSuccess] =
    useState<string | null>(null);

  const frozenUrlRef =
    useRef<string | null>(null);


  // ==========================================================
  // CLEANUP CAMERA SNAPSHOT URL
  // ==========================================================

  useEffect(() => {
    return () => {
      if (frozenUrlRef.current) {
        URL.revokeObjectURL(
          frozenUrlRef.current
        );
      }
    };
  }, []);


  // ==========================================================
  // FREEZE CAMERA FRAME
  // ==========================================================

  async function freezeFrame() {
    setLoading(true);
    setError(null);
    setSuccess(null);

    try {
      const frame =
        await captureCameraFrame();

      const objectUrl =
        URL.createObjectURL(frame);

      const image = new Image();

      try {
        const size = await new Promise<{
          width: number;
          height: number;
        }>((resolve, reject) => {

          image.onload = () => resolve({
            width: image.naturalWidth,
            height: image.naturalHeight,
          });

          image.onerror = () => reject(
            new Error(
              "Could not read camera image."
            )
          );

          image.src = objectUrl;
        });

        if (frozenUrlRef.current) {
          URL.revokeObjectURL(
            frozenUrlRef.current
          );
        }

        frozenUrlRef.current = objectUrl;

        setFrozenUrl(objectUrl);
        setFrameSize(size);

        // New frame requires new corner selection.
        setPoints([]);

      } catch (loadError) {
        URL.revokeObjectURL(objectUrl);
        throw loadError;
      }

    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "Could not capture camera frame."
      );

    } finally {
      setLoading(false);
    }
  }


  // ==========================================================
  // RESUME LIVE PREVIEW
  // ==========================================================

  function resumeLive() {

    setFrozenUrl(null);

    setFrameSize({
      width: 0,
      height: 0,
    });

    setPoints([]);
    setError(null);
    setSuccess(null);

    if (frozenUrlRef.current) {
      URL.revokeObjectURL(
        frozenUrlRef.current
      );

      frozenUrlRef.current = null;
    }
  }


  // ==========================================================
  // SELECT BOARD CORNER
  // ==========================================================

  function handleBoardClick(
    event: MouseEvent<SVGSVGElement>,
  ) {

    if (
      !frozenUrl ||
      points.length >= 4 ||
      saving
    ) {
      return;
    }

    const rect =
      event.currentTarget.getBoundingClientRect();

    if (
      rect.width === 0 ||
      rect.height === 0
    ) {
      return;
    }

    const x = Math.max(
      0,
      Math.min(
        frameSize.width - 1,
        (
          (event.clientX - rect.left)
          / rect.width
        ) * frameSize.width,
      ),
    );

    const y = Math.max(
      0,
      Math.min(
        frameSize.height - 1,
        (
          (event.clientY - rect.top)
          / rect.height
        ) * frameSize.height,
      ),
    );

    setPoints((old) => [
      ...old,
      { x, y },
    ]);

    setError(null);
    setSuccess(null);
  }


  // ==========================================================
  // SAVE CALIBRATION
  // ==========================================================

  async function saveCalibration() {

    if (
      !frozenUrl ||
      points.length !== 4
    ) {
      return;
    }

    setSaving(true);
    setError(null);
    setSuccess(null);

    try {
      const response = await fetch(
        API_URL,
        {
          method: "POST",

          headers: {
            "Content-Type": "application/json",
          },

          body: JSON.stringify({
            camera_width: frameSize.width,

            camera_height: frameSize.height,

            source_points: points.map(
              (point) => [
                point.x,
                point.y,
              ]
            ),
          }),
        },
      );

      if (!response.ok) {
        let message =
          `Calibration could not be saved (${response.status}).`;

        try {
          const data: {
            detail?: string;
          } = await response.json();

          if (typeof data.detail === "string") {
            message = data.detail;
          }

        } catch {
          // Keep fallback error.
        }

        throw new Error(message);
      }

      setSuccess(
        "Fixed board calibration saved to " +
        "config/calibration.json. " +
        "Future Live Games will use the new position."
      );

    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "Could not save calibration."
      );

    } finally {
      setSaving(false);
    }
  }


  // ==========================================================
  // PREVIEW 8x8 GRID
  // ==========================================================

  const grid = points.length === 4

    ? Array.from(
        { length: 9 },
        (_, index) => {

          const fraction =
            index / 8;

          return {
            verticalStart:
              projectToQuadrilateral(
                points,
                fraction,
                0,
              ),

            verticalEnd:
              projectToQuadrilateral(
                points,
                fraction,
                1,
              ),

            horizontalStart:
              projectToQuadrilateral(
                points,
                0,
                fraction,
              ),

            horizontalEnd:
              projectToQuadrilateral(
                points,
                1,
                fraction,
              ),
          };
        },
      )

    : [];


  // ==========================================================
  // RENDER
  // ==========================================================

  return (
    <div className="page fixed-calibration-page">

      {/* HEADER */}

      <div className="fixed-calibration-heading">
        <h1>Fixed Board Calibration</h1>

        <p>
          Set the four corners of the physical
          chessboard from the camera.
        </p>
      </div>


      <div className="fixed-calibration-layout">

        {/* CAMERA PANEL */}

        <section className="fixed-calibration-panel">

          <div className="fixed-calibration-toolbar">

            <div>
              <strong>
                {frozenUrl
                  ? "Frozen frame"
                  : "Live camera"}
              </strong>

              <span>
                {frozenUrl
                  ? `${frameSize.width} × ${frameSize.height}`
                  : "Press Freeze frame to select corners"}
              </span>
            </div>


            <div className="fixed-calibration-actions">

              <button
                type="button"
                onClick={freezeFrame}
                disabled={loading || saving}
              >
                {loading
                  ? "Capturing..."
                  : frozenUrl
                    ? "Capture again"
                    : "Freeze frame"}
              </button>


              {frozenUrl && (
                <button
                  type="button"
                  onClick={resumeLive}
                  disabled={saving}
                >
                  Resume live
                </button>
              )}

            </div>
          </div>


          {/* CAMERA IMAGE / CORNER OVERLAY */}

          <div className="fixed-calibration-camera">

            <img
              src={
                frozenUrl ??
                CAMERA_STREAM_URL
              }
              alt={
                frozenUrl
                  ? "Frozen camera for calibration"
                  : "Live camera preview"
              }
            />


            {frozenUrl && frameSize.width > 0 && (

              <svg
                className="fixed-calibration-overlay"

                viewBox={
                  `0 0 ${frameSize.width} ${frameSize.height}`
                }

                preserveAspectRatio="none"

                onClick={handleBoardClick}

                role="button"

                aria-label={
                  "Select chessboard corner on frozen frame"
                }
              >

                {/* BOARD OUTLINE + 8x8 GRID */}

                {points.length === 4 && (
                  <>

                    <polygon
                      points={
                        points.map(
                          (point) =>
                            `${point.x},${point.y}`
                        ).join(" ")
                      }

                      fill="rgba(59,130,246,0.10)"

                      stroke="#60a5fa"

                      strokeWidth="3"
                    />


                    {grid.map((line, index) => (

                      <g
                        key={index}
                        stroke="#39e896"
                        strokeWidth="1.7"
                        fill="none"
                      >

                        <line
                          x1={line.verticalStart.x}
                          y1={line.verticalStart.y}
                          x2={line.verticalEnd.x}
                          y2={line.verticalEnd.y}
                        />

                        <line
                          x1={line.horizontalStart.x}
                          y1={line.horizontalStart.y}
                          x2={line.horizontalEnd.x}
                          y2={line.horizontalEnd.y}
                        />

                      </g>
                    ))}

                  </>
                )}


                {/* SELECTED CORNERS */}

                {points.map((point, index) => (

                  <g key={index}>

                    <circle
                      cx={point.x}
                      cy={point.y}
                      r="7"
                      fill="#60a5fa"
                      stroke="#fff"
                      strokeWidth="2"
                    />

                    <text
                      x={point.x + 12}
                      y={point.y - 11}

                      fill="white"
                      fontSize="20"
                      fontWeight="bold"

                      stroke="#111827"
                      strokeWidth="3"
                      paintOrder="stroke"
                    >
                      {CORNER_LABELS[index]}
                    </text>

                  </g>
                ))}

              </svg>
            )}

          </div>


          {/* CAPTION */}

          <p className="fixed-calibration-caption">
            {frozenUrl

              ? (
                "Click the four outer corners of the " +
                "8×8 PLAYING AREA, not the wooden border."
              )

              : (
                "The preview is live. Freeze a frame " +
                "before selecting points."
              )
            }
          </p>

        </section>


        {/* CONTROLS PANEL */}

        <aside
          className={
            "fixed-calibration-panel fixed-calibration-controls"
          }
        >

          <h2>Board corners</h2>

          <p>
            Click in this exact order,
            as in src/calibration.py:
          </p>


          <div className="fixed-calibration-corners">

            {CORNER_LABELS.map(
              (label, index) => (

                <div
                  key={label}

                  className={
                    `fixed-calibration-corner${
                      points.length === index
                        ? " active"
                        : ""
                    }`
                  }
                >

                  <span>
                    {index + 1}
                  </span>

                  <strong>
                    {label}
                  </strong>

                  <small>
                    {points[index]

                      ? (
                        `${Math.round(points[index].x)}, ` +
                        `${Math.round(points[index].y)}`
                      )

                      : "Not selected"
                    }
                  </small>

                </div>
              )
            )}

          </div>


          {/* UNDO / RESET */}

          <div className="fixed-calibration-buttons">

            <button
              type="button"

              disabled={
                !frozenUrl ||
                points.length === 0 ||
                saving
              }

              onClick={() =>
                setPoints(
                  (previous) =>
                    previous.slice(0, -1)
                )
              }
            >
              Undo last point
            </button>


            <button
              type="button"

              disabled={
                !frozenUrl ||
                points.length === 0 ||
                saving
              }

              onClick={() => setPoints([])}
            >
              Reset points
            </button>

          </div>


          {/* SAVE */}

          <button
            type="button"

            className="fixed-calibration-save"

            disabled={
              !frozenUrl ||
              points.length !== 4 ||
              saving
            }

            onClick={saveCalibration}
          >
            {saving
              ? "Saving..."
              : "Save Fixed Board"}
          </button>


          {/* STATUS */}

          {error && (
            <p
              className="fixed-calibration-error"
              role="alert"
            >
              {error}
            </p>
          )}

          {success && (
            <p
              className="fixed-calibration-success"
              role="status"
            >
              {success}
            </p>
          )}


          {/* HELP */}

          <p className="fixed-calibration-hint">

            Stop Live Game before saving.

            The new configuration replaces

            <code>
              {" "}config/calibration.json
            </code>.

            The previous version is backed up as

            <code>
              {" "}calibration.json.bak
            </code>.

          </p>

        </aside>

      </div>

    </div>
  );
}
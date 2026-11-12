import {
  useEffect,
  useState,
} from "react";

import {
  recognizePosition,
} from "../api/positions";

import {
  CAMERA_STREAM_URL,
  captureCameraFrame,
} from "../api/camera";

import PositionCalibration
  from "../components/position/PositionCalibration";

import DigitalChessBoard
  from "../components/chess/DigitalChessBoard";

import type {
  Point,
  PositionRecognitionResponse,
} from "../types/position";


export default function UploadPositionPage() {

  const [
    imageFile,
    setImageFile,
  ] = useState<File | null>(
    null,
  );


  const [
    imageUrl,
    setImageUrl,
  ] = useState<string | null>(
    null,
  );


  const [
    cameraOpen,
    setCameraOpen,
  ] = useState(
    false,
  );


  const [
    capturing,
    setCapturing,
  ] = useState(
    false,
  );


  const [
    points,
    setPoints,
  ] = useState<Point[]>(
    [],
  );


  const [
    result,
    setResult,
  ] = useState<
    PositionRecognitionResponse
    |
    null
  >(null);


  const [
    sideToMove,
    setSideToMove,
  ] = useState<"w" | "b">(
    "w",
  );


  const [
    loading,
    setLoading,
  ] = useState(
    false,
  );


  const [
    error,
    setError,
  ] = useState<
    string | null
  >(null);


  // =========================================================
  // CLEANUP
  // =========================================================

  useEffect(() => {

    return () => {

      if (imageUrl) {

        URL.revokeObjectURL(
          imageUrl,
        );
      }
    };

  }, [
    imageUrl,
  ]);


  // =========================================================
  // SET IMAGE
  // =========================================================

  function setSelectedImage(
    file: File,
  ) {

    if (imageUrl) {

      URL.revokeObjectURL(
        imageUrl,
      );
    }


    const nextUrl =
      URL.createObjectURL(
        file,
      );


    setImageFile(
      file,
    );


    setImageUrl(
      nextUrl,
    );


    setPoints(
      [],
    );


    setResult(
      null,
    );


    setError(
      null,
    );
  }


  // =========================================================
  // FILE
  // =========================================================

  function handleFile(
    file: File,
  ) {

    setCameraOpen(
      false,
    );


    setSelectedImage(
      file,
    );
  }


  // =========================================================
  // CAMERA
  // =========================================================

  function handleOpenCamera() {

    setCameraOpen(
      true,
    );


    setResult(
      null,
    );


    setError(
      null,
    );
  }


  function handleCloseCamera() {

    setCameraOpen(
      false,
    );
  }


  async function handleCaptureCamera() {

    setCapturing(
      true,
    );


    setError(
      null,
    );


    try {

      const file =
        await captureCameraFrame();


      setSelectedImage(
        file,
      );


      setCameraOpen(
        false,
      );


    } catch (err) {

      if (
        err instanceof Error
      ) {

        setError(
          err.message,
        );

      } else {

        setError(
          "Could not capture camera frame.",
        );
      }


    } finally {

      setCapturing(
        false,
      );
    }
  }


  // =========================================================
  // SIDE
  // =========================================================

  function handleSideToMoveChange(
    value: string,
  ) {

    if (
      value === "w"
      ||
      value === "b"
    ) {

      setSideToMove(
        value,
      );
    }
  }


  // =========================================================
  // RECOGNIZE
  // =========================================================

  async function handleRecognize() {

    if (!imageFile) {

      setError(
        "Please select or capture an image first.",
      );

      return;
    }


    if (
      points.length !== 8
    ) {

      setError(
        "Please select exactly 8 calibration points.",
      );

      return;
    }


    setLoading(
      true,
    );


    setError(
      null,
    );


    try {

      const response =
        await recognizePosition(

          imageFile,

          points.slice(
            0,
            4,
          ),

          points.slice(
            4,
            8,
          ),
        );


      setResult(
        response,
      );


    } catch (err) {

      if (
        err instanceof Error
      ) {

        setError(
          err.message,
        );

      } else {

        setError(
          "Unknown recognition error.",
        );
      }


    } finally {

      setLoading(
        false,
      );
    }
  }


  // =========================================================
  // RESET
  // =========================================================

  function handleAnotherImage() {

    setResult(
      null,
    );


    setPoints(
      [],
    );


    setError(
      null,
    );
  }


  // =========================================================
  // UI
  // =========================================================

  return (

    <div className="page">

      <h1>
        Upload Position
      </h1>


      <p className="page-description">
        Choose an image from your computer
        or capture a frame directly from
        the physical chess camera.
      </p>


      {/* ===================================================
          INPUT MODE
      =================================================== */}

      {!result && (

        <>

          <div
            className="upload-panel"
          >

            <div
              style={{
                display:
                  "flex",

                gap:
                  "12px",

                alignItems:
                  "center",

                flexWrap:
                  "wrap",
              }}
            >

              <input
                type="file"

                accept="image/*"

                onChange={
                  event => {

                    const file =
                      event
                      .target
                      .files?.[0];


                    if (file) {

                      handleFile(
                        file,
                      );
                    }
                  }
                }
              />


              <span>
                or
              </span>


              <button
                type="button"

                onClick={
                  handleOpenCamera
                }
              >
                Open Camera
              </button>

            </div>

          </div>


          {/* ===============================================
              CAMERA
          =============================================== */}

          {
            cameraOpen
            &&
            (
              <div
                style={{
                  marginBottom:
                    "24px",
                }}
              >

                <div
                  style={{
                    width:
                      "min(800px, 100%)",

                    border:
                      "1px solid #374151",

                    borderRadius:
                      "10px",

                    overflow:
                      "hidden",

                    background:
                      "#000000",
                  }}
                >

                  <img
                    src={
                      CAMERA_STREAM_URL
                    }

                    alt=
                      "Live chess camera"

                    style={{
                      display:
                        "block",

                      width:
                        "100%",

                      height:
                        "auto",
                    }}
                  />

                </div>


                <div
                  style={{
                    display:
                      "flex",

                    gap:
                      "12px",

                    marginTop:
                      "12px",
                  }}
                >

                  <button
                    type="button"

                    className=
                      "primary-button"

                    disabled={
                      capturing
                    }

                    onClick={
                      handleCaptureCamera
                    }
                  >

                    {
                      capturing
                        ?
                        "Capturing..."
                        :
                        "Capture Photo"
                    }

                  </button>


                  <button
                    type="button"

                    onClick={
                      handleCloseCamera
                    }
                  >
                    Close Camera
                  </button>

                </div>

              </div>
            )
          }


          {/* ===============================================
              CAPTURED / UPLOADED IMAGE + CALIBRATION
          =============================================== */}

          {
            imageUrl
            &&
            (
              <PositionCalibration

                imageUrl={
                  imageUrl
                }

                points={
                  points
                }

                onPointsChange={
                  setPoints
                }

              />
            )
          }


          {/* ===============================================
              RECOGNIZE
          =============================================== */}

          {
            imageFile
            &&
            (
              <button
                type="button"

                className=
                  "primary-button"

                disabled={
                  loading
                  ||
                  points.length !== 8
                }

                onClick={
                  handleRecognize
                }
              >

                {
                  loading
                    ?
                    "Recognizing..."
                    :
                    "Recognize Position"
                }

              </button>
            )
          }

        </>

      )}


      {/* ===================================================
          ERROR
      =================================================== */}

      {
        error
        &&
        (
          <div
            className=
              "error-message"
          >
            {error}
          </div>
        )
      }


      {/* ===================================================
          RESULT
      =================================================== */}

      {
        result
        &&
        (
          <div
            className=
              "recognition-result"
          >

            <div
              className=
                "result-controls"
            >

              <label>
                Side to move
              </label>


              <select

                value={
                  sideToMove
                }

                onChange={
                  event => {

                    handleSideToMoveChange(
                      event.target.value,
                    );
                  }
                }
              >

                <option
                  value="w"
                >
                  White
                </option>


                <option
                  value="b"
                >
                  Black
                </option>

              </select>


              <button
                type="button"

                onClick={
                  handleAnotherImage
                }
              >
                Scan another image
              </button>

            </div>


            <div
              className=
                "recognized-fen"
            >

              <strong>
                Recognized board FEN
              </strong>


              <code>
                {
                  result.board_fen
                }
              </code>

            </div>


            <DigitalChessBoard

              key={
                `${result.board_fen}-${sideToMove}`
              }

              boardFen={
                result.board_fen
              }

              initialTurn={
                sideToMove
              }

            />

          </div>
        )
      }

    </div>
  );
}
import type {
  Point,
  PositionRecognitionResponse,
} from "../types/position";


const API_BASE_URL =
  "http://127.0.0.1:8000/api";


// ============================================================
// MANUAL RECOGNITION
// ============================================================

export async function recognizePosition(
  image: File,
  outerPoints: Point[],
  boardPoints: Point[],
): Promise<PositionRecognitionResponse> {

  const formData =
    new FormData();


  formData.append(
    "image",
    image,
  );


  formData.append(
    "outer_points",
    JSON.stringify(
      outerPoints,
    ),
  );


  formData.append(
    "board_points",
    JSON.stringify(
      boardPoints,
    ),
  );


  const response =
    await fetch(
      `${API_BASE_URL}/positions/recognize`,
      {
        method: "POST",
        body: formData,
      },
    );


  if (!response.ok) {

    let message =
      `Recognition failed: ${response.status}`;


    try {

      const data =
        await response.json();


      if (data.detail) {

        message =
          data.detail;
      }

    } catch {

      // Keep default error message.

    }


    throw new Error(
      message,
    );
  }


  return response.json();
}


// ============================================================
// AUTO RECOGNITION
// ============================================================

export async function recognizePositionAuto(
  image: File,
): Promise<PositionRecognitionResponse> {

  const formData =
    new FormData();


  formData.append(
    "image",
    image,
  );


  const response =
    await fetch(
      `${API_BASE_URL}/positions/recognize-auto`,
      {
        method: "POST",
        body: formData,
      },
    );


  if (!response.ok) {

    let message =
      `Recognition failed: ${response.status}`;


    try {

      const data =
        await response.json();


      if (data.detail) {

        message =
          data.detail;
      }

    } catch {

      // Keep default error message.

    }


    throw new Error(
      message,
    );
  }


  return response.json();
}
const API_BASE_URL =
  "http://127.0.0.1:8000/api";


export const CAMERA_STREAM_URL =
  `${API_BASE_URL}/camera/stream`;


// ============================================================
// CAPTURE FRAME
// ============================================================

export async function captureCameraFrame():
  Promise<File> {

  const response =
    await fetch(
      `${API_BASE_URL}/camera/snapshot`,
      {
        method: "GET",
        cache: "no-store",
      },
    );


  if (!response.ok) {

    let message =
      `Camera capture failed: ${response.status}`;


    try {

      const data =
        await response.json();


      if (data.detail) {

        message =
          data.detail;
      }

    } catch {

      // Keep default message.

    }


    throw new Error(
      message
    );
  }


  const blob =
    await response.blob();


  return new File(
    [
      blob,
    ],

    `camera_${Date.now()}.jpg`,

    {
      type:
        "image/jpeg",
    },
  );
}
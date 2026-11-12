import cv2
from pathlib import Path
from datetime import datetime


# ============================================================
# CONFIG
# ============================================================

RTSP_URL = (
    "rtsp://admin:L278A5D7@192.168.1.106:554/"
    "cam/realmonitor?channel=1&subtype=0"
)

SAVE_DIR = Path("captured_images")

# Giống workflow hiện tại:
# IMOU native -> resize thành 1280x720 để làm working frame
WORKING_WIDTH = 1280
WORKING_HEIGHT = 720


# ============================================================
# OPEN CAMERA
# ============================================================

def open_camera():

    print("Opening IMOU...")

    cap = cv2.VideoCapture(
        RTSP_URL,
        cv2.CAP_FFMPEG
    )

    cap.set(
        cv2.CAP_PROP_BUFFERSIZE,
        1
    )

    if not cap.isOpened():
        raise RuntimeError(
            "Cannot open IMOU RTSP stream."
        )

    print("IMOU connected.")

    return cap


# ============================================================
# MAIN
# ============================================================

def main():

    SAVE_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    cap = open_camera()

    cv2.namedWindow(
        "IMOU Camera"
    )

    count = 0

    print()
    print("==============================")
    print("SPACE = capture image")
    print("Q / ESC = quit")
    print("==============================")
    print()

    while True:

        ret, frame = cap.read()

        if not ret or frame is None:
            print("Failed to read frame.")
            break

        # ----------------------------------------------------
        # Resize giống dataset_capture hiện tại
        # ----------------------------------------------------

        frame = cv2.resize(
            frame,
            (
                WORKING_WIDTH,
                WORKING_HEIGHT
            ),
            interpolation=cv2.INTER_AREA
        )

        display = frame.copy()

        cv2.putText(
            display,
            "SPACE = capture | Q = quit",
            (20, 40),
            cv2.FONT_HERSHEY_SIMPLEX,
            1,
            (0, 255, 0),
            2
        )

        cv2.imshow(
            "IMOU Camera",
            display
        )

        key = cv2.waitKey(1) & 0xFF

        # ====================================================
        # SPACE = SAVE
        # ====================================================

        if key == 32:

            timestamp = (
                datetime.now()
                .strftime(
                    "%Y%m%d_%H%M%S_%f"
                )[:-3]
            )

            path = (
                SAVE_DIR
                /
                f"{timestamp}.png"
            )

            success = cv2.imwrite(
                str(path),
                frame
            )

            if success:

                count += 1

                print(
                    f"[{count}] Saved: "
                    f"{path}"
                )

            else:

                print(
                    "Failed to save image."
                )

        # ====================================================
        # QUIT
        # ====================================================

        elif key in (
            ord("q"),
            ord("Q"),
            27
        ):

            break

    cap.release()
    cv2.destroyAllWindows()

    print()
    print(
        f"Finished. "
        f"Total images saved: {count}"
    )


if __name__ == "__main__":
    main()
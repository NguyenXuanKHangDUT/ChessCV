import cv2
import time

url = "rtsp://admin:L278A5D7@192.168.1.106:554/cam/realmonitor?channel=1&subtype=0"

cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)

if not cap.isOpened():
    print("Khong mo duoc camera")
    exit()

print("Connected")
print("Width :", cap.get(cv2.CAP_PROP_FRAME_WIDTH))
print("Height:", cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
print("FPS   :", cap.get(cv2.CAP_PROP_FPS))

while True:
    ret, frame = cap.read()

    if not ret:
        print("Mat frame")
        break

    cv2.imshow("IMOU IPC-A52P", frame)

    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

cap.release()
cv2.destroyAllWindows()
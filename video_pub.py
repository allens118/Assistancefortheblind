"""
Video publisher:
- Reads frames from a video file
- Publishes one frame every N seconds to MQTT topic assist/cam/raw
Useful for simulating camera input with a recorded clip.
"""

import base64
import json
import os
import time

import cv2
from paho.mqtt import client as mqtt


BROKER = os.getenv("MQTT_BROKER", "localhost")
PORT = int(os.getenv("MQTT_PORT", "1883"))
USERNAME = os.getenv("MQTT_USER")
PASSWORD = os.getenv("MQTT_PASS")
USE_TLS = os.getenv("MQTT_TLS", "0") == "1"
TOPIC_RAW = os.getenv("TOPIC_RAW", "assist/cam/raw")
TOPIC_RAW_ALT = os.getenv("TOPIC_RAW_ALT", "ntut/SourceImage")
TOPIC_RAW_ALT_RAW_ONLY = os.getenv("TOPIC_RAW_ALT_RAW_ONLY", "0") == "1"
TOPIC_RAW_ALT_META = os.getenv("TOPIC_RAW_ALT_META", "ntut/SourceMeta")
VIDEO_PATH = os.getenv("VIDEO_PATH", "14881231_3840_2160_24fps.mp4")
SLEEP_SEC = float(os.getenv("SLEEP_SEC", "10"))  # publish interval (wall-clock)
LOOP_VIDEO = os.getenv("LOOP_VIDEO", "1") == "1"
FRAME_ID = os.getenv("FRAME_ID", "cam1")
JPEG_QUALITY = int(os.getenv("JPEG_QUALITY", "85"))
QOS = 1


def make_jpeg_data_url(b64: str) -> str:
    return f"data:image/jpeg;base64,{b64}"


def connect_mqtt() -> mqtt.Client:
    client = mqtt.Client()
    if USERNAME:
        client.username_pw_set(USERNAME, PASSWORD or "")
    if USE_TLS:
        client.tls_set()
    client.connect(BROKER, PORT, keepalive=30)
    return client


def main():
    if not os.path.exists(VIDEO_PATH):
        raise FileNotFoundError(f"Video not found: {VIDEO_PATH}")

    cap = cv2.VideoCapture(VIDEO_PATH)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {VIDEO_PATH}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 0
    fps = fps if fps > 0 else 30.0
    step_frames = int(max(1, fps * SLEEP_SEC))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)

    client = connect_mqtt()
    print(
        f"Publishing every {SLEEP_SEC}s from {VIDEO_PATH} "
        f"({fps:.2f} fps, {total_frames} frames) to {TOPIC_RAW} on {BROKER}:{PORT}"
    )

    next_frame_idx = 0
    try:
        while True:
            cap.set(cv2.CAP_PROP_POS_FRAMES, next_frame_idx)
            ok, frame = cap.read()
            if not ok:
                if LOOP_VIDEO:
                    next_frame_idx = 0
                    continue
                else:
                    print("End of video; stopping (LOOP_VIDEO=0)")
                    break

            ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY])
            if not ok:
                print("JPEG encode failed; skipping frame")
            else:
                payload = {
                    "ts": int(time.time() * 1000),
                    "frame_id": FRAME_ID,
                    "w": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                    "h": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
                    "encoding": "jpg",
                    "data": base64.b64encode(buf.tobytes()).decode("ascii"),
                }
                client.publish(TOPIC_RAW, json.dumps(payload), qos=QOS)
                if TOPIC_RAW_ALT:
                    data_url = make_jpeg_data_url(payload["data"])
                    # SourceImage 只送純圖片（data URL）
                    client.publish(TOPIC_RAW_ALT, data_url, qos=QOS)
                if TOPIC_RAW_ALT_META:
                    # metadata 另開 topic
                    client.publish(TOPIC_RAW_ALT_META, json.dumps(payload), qos=QOS)

            next_frame_idx += step_frames
            time.sleep(SLEEP_SEC)
    except KeyboardInterrupt:
        print("Stopped by user")
    finally:
        cap.release()


if __name__ == "__main__":
    main()

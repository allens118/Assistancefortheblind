"""
Camera publisher:
- Captures frames from a local camera (device 0 by default)
- Encodes as JPEG and publishes to MQTT topic assist/cam/raw
"""

import base64
import json
import os
import time
from typing import Optional

import cv2
from paho.mqtt import client as mqtt


BROKER = os.getenv("MQTT_BROKER", "localhost")
PORT = int(os.getenv("MQTT_PORT", "1883"))
USERNAME = os.getenv("MQTT_USER")
PASSWORD = os.getenv("MQTT_PASS")
USE_TLS = os.getenv("MQTT_TLS", "0") == "1"
TOPIC_RAW = os.getenv("TOPIC_RAW", "assist/cam/raw")
TOPIC_RAW_ALT = os.getenv("TOPIC_RAW_ALT", "ntut/SourceImage")  # optional extra topic for raw image
TOPIC_RAW_ALT_RAW_ONLY = os.getenv("TOPIC_RAW_ALT_RAW_ONLY", "0") == "1"  # if True, publish base64 string only
TOPIC_RAW_ALT_META = os.getenv("TOPIC_RAW_ALT_META", "ntut/SourceMeta")  # metadata topic
DEVICE_INDEX = int(os.getenv("CAM_INDEX", "0"))
WIDTH = int(os.getenv("CAM_WIDTH", "640"))
HEIGHT = int(os.getenv("CAM_HEIGHT", "480"))
FPS = float(os.getenv("CAM_FPS", "10"))
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


def open_camera() -> cv2.VideoCapture:
    cap = cv2.VideoCapture(DEVICE_INDEX, cv2.CAP_DSHOW)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, HEIGHT)
    cap.set(cv2.CAP_PROP_FPS, FPS)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open camera index {DEVICE_INDEX}")
    return cap


def encode_frame(frame) -> Optional[bytes]:
    ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
    if not ok:
        return None
    return base64.b64encode(buf.tobytes())


def main():
    client = connect_mqtt()
    cap = open_camera()
    frame_id = os.getenv("FRAME_ID", "cam1")
    period = 1.0 / FPS if FPS > 0 else 0.1

    print(f"Publishing to {BROKER}:{PORT} topic {TOPIC_RAW} at ~{FPS} fps")
    try:
        while True:
            start = time.time()
            ok, frame = cap.read()
            if not ok:
                print("Frame grab failed; retrying")
                time.sleep(0.1)
                continue
            data = encode_frame(frame)
            if data is None:
                print("JPEG encode failed; skipping frame")
                continue
            payload = {
                "ts": int(time.time() * 1000),
                "frame_id": frame_id,
                "w": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                "h": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
                "encoding": "jpg",
                "data": data.decode("ascii"),
            }
            client.publish(TOPIC_RAW, json.dumps(payload), qos=QOS)
            if TOPIC_RAW_ALT:
                data_url = make_jpeg_data_url(payload["data"])
                # SourceImage 只送純圖片（data URL）
                client.publish(TOPIC_RAW_ALT, data_url, qos=QOS)
            if TOPIC_RAW_ALT_META:
                # metadata 另開 topic
                client.publish(TOPIC_RAW_ALT_META, json.dumps(payload), qos=QOS)
            elapsed = time.time() - start
            sleep_time = max(0, period - elapsed)
            if sleep_time:
                time.sleep(sleep_time)
    except KeyboardInterrupt:
        print("Stopped by user")
    finally:
        cap.release()


if __name__ == "__main__":
    main()

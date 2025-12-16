"""
Fruit detector node (YOLOv8):
- Subscribes to camera MQTT topics (base64 JPEG string or data URL)
- Detects fruit classes and estimates distance
- Publishes detections to MQTT (JSON) and optional annotated JPEG/data URL
"""

import base64
import json
import os
import time
from typing import List, Tuple

import cv2
import numpy as np
from paho.mqtt import client as mqtt
from ultralytics import YOLO

# Safe unpickling for newer torch versions; ignore if unavailable
try:
    from torch.serialization import add_safe_globals
    from ultralytics.nn.tasks import DetectionModel

    add_safe_globals([DetectionModel])
except Exception:
    pass


BROKER = os.getenv("MQTT_BROKER", "localhost")
PORT = int(os.getenv("MQTT_PORT", "1883"))
USERNAME = os.getenv("MQTT_USER")
PASSWORD = os.getenv("MQTT_PASS")
USE_TLS = os.getenv("MQTT_TLS", "0") == "1"
# Align defaults with existing pipeline topics
TOPIC_RAW = os.getenv("TOPIC_RAW", "ntut/SourceImage")
TOPIC_RAW_ESP = os.getenv("TOPIC_RAW_ESP", "ntut/CAM/SourceImage")
RELAY_RAW_TOPIC = os.getenv("RELAY_RAW_TOPIC", TOPIC_RAW)
TOPIC_DET = os.getenv("TOPIC_FRUIT_DET", "assist/detections")
TOPIC_ANN = os.getenv("TOPIC_FRUIT_ANN", "assist/cam/annotated")
TOPIC_ANN_ALT = os.getenv("TOPIC_FRUIT_ANN_ALT", "ntut/ProcessImage")
PUBLISH_ANN = os.getenv("PUBLISH_ANN", "1") == "1"
TOPIC_INFO = os.getenv("TOPIC_FRUIT_INFO", "ntut/ProcessInfo")
TOPIC_INFO_ZH = os.getenv("TOPIC_FRUIT_INFO_ZH", "ntut/ProcessInfoZh")
TOPIC_INFO_EN = os.getenv("TOPIC_FRUIT_INFO_EN", "ntut/ProcessInfoEn")
TOPIC_SPEECH_ZH = os.getenv("TOPIC_FRUIT_SPEECH_ZH", "ntut/ProcessSpeechZh")
TOPIC_SPEECH_EN = os.getenv("TOPIC_FRUIT_SPEECH_EN", "ntut/ProcessSpeechEn")

MODEL_PATH = os.getenv("YOLO_MODEL", "yolov8n.pt")
IMGSZ = int(os.getenv("IMGSZ", "1280"))  # higher imgsz helps small fruit in wide images
CONF_THRESH = float(os.getenv("CONF_THRESH", "0.1"))  # lower default for fruit
FOCAL_PX = float(os.getenv("FOCAL_PX", "600"))  # adjust to your camera
FRUIT_HEIGHT_M = float(os.getenv("FRUIT_HEIGHT_M", "0.08"))  # typical fruit height in meters
DIST_MULTIPLIER_ESP = float(os.getenv("DIST_MULTIPLIER_ESP", "0.1"))  # ESP32-CAM wide FOV correction
SPEECH_CONF_MIN = float(os.getenv("SPEECH_CONF_MIN", "0.8"))  # min confidence for speech output

QOS_SUB = 1
QOS_PUB = 1

FRUIT_CLASSES = {"apple", "banana", "orange", "broccoli", "carrot"}
CLASS_NAME_ZH = {
    "apple": "蘋果",
    "banana": "香蕉",
    "orange": "橘子",
    "broccoli": "花椰菜",
    "carrot": "紅蘿蔔",
}
SIDE_ZH = {"left": "左側", "center": "正前", "right": "右側"}
SIDE_EN = {"left": "left", "center": "center", "right": "right"}


def make_jpeg_data_url(b64: str) -> str:
    return f"data:image/jpeg;base64,{b64}"


def estimate_distance_m(bbox: Tuple[int, int, int, int], real_height_m: float, focal_px: float) -> float:
    _, y1, _, y2 = bbox
    pix_h = max(1, y2 - y1)
    return (real_height_m * focal_px) / pix_h


def side_of_frame(bbox: Tuple[int, int, int, int], img_w: int) -> str:
    x1, _, x2, _ = bbox
    cx = (x1 + x2) / 2
    if cx < img_w / 3:
        return "left"
    if cx > 2 * img_w / 3:
        return "right"
    return "center"


class FruitDetector:
    def __init__(self):
        self.model = YOLO(MODEL_PATH)
        self.class_names: List[str] = self.model.names
        self.client = mqtt.Client()
        if USERNAME:
            self.client.username_pw_set(USERNAME, PASSWORD or "")
        if USE_TLS:
            self.client.tls_set()
        self.client.on_message = self.on_message
        print(f"Connecting to MQTT {BROKER}:{PORT} TLS={USE_TLS} user_set={bool(USERNAME)}")
        self.client.connect(BROKER, PORT, keepalive=30)
        for t in {TOPIC_RAW, TOPIC_RAW_ESP}:
            if t:
                self.client.subscribe(t, qos=QOS_SUB)
        print(f"Fruit detector subscribed to {TOPIC_RAW} and {TOPIC_RAW_ESP}, publishing to {TOPIC_DET}")
        if PUBLISH_ANN:
            print(f"Annotated frames will be published to {TOPIC_ANN}")

    def run(self):
        self.client.loop_forever()

    def on_message(self, _cli, _userdata, msg):
        try:
            print(f"[rx] topic={msg.topic} bytes={len(msg.payload)}")
            raw_bytes = msg.payload
            from_esp = msg.topic == TOPIC_RAW_ESP
            try:
                raw = json.loads(raw_bytes)
            except (json.JSONDecodeError, TypeError, UnicodeDecodeError):
                if raw_bytes.startswith(b"\xff\xd8"):  # JPEG magic
                    raw = base64.b64encode(raw_bytes).decode("ascii")
                else:
                    try:
                        raw = raw_bytes.decode("ascii", errors="strict")
                    except UnicodeDecodeError:
                        raw = base64.b64encode(raw_bytes).decode("ascii")
            if isinstance(raw, (bytes, bytearray)):
                raw = base64.b64encode(raw).decode("ascii")
            if isinstance(raw, str):
                payload = {"data": raw}
            elif isinstance(raw, dict):
                if raw.get("_relay_skip"):
                    return
                payload = raw
            else:
                print(f"Unsupported payload type {type(raw)}; skipping")
                return

            frame = self.decode_frame(payload)
            if frame is None:
                print("Frame decode failed; skipping message")
                return

            dist_scale = DIST_MULTIPLIER_ESP if from_esp else 1.0
            dets, ann = self.detect(frame, dist_scale=dist_scale)
            if not dets:
                return

            out_msg = {
                "frame_id": payload.get("frame_id"),
                "ts": int(time.time() * 1000),
                "objects": dets,
            }
            print(f"[det] objects={len(dets)} publish {TOPIC_DET}")
            self.client.publish(TOPIC_DET, json.dumps(out_msg), qos=QOS_PUB)
            if TOPIC_INFO:
                self.client.publish(TOPIC_INFO, json.dumps(out_msg), qos=QOS_PUB)
            if TOPIC_INFO_ZH:
                zh = self.format_text(dets, lang="zh")
                self.client.publish(TOPIC_INFO_ZH, zh, qos=QOS_PUB)
            if TOPIC_INFO_EN:
                en = self.format_text(dets, lang="en")
                self.client.publish(TOPIC_INFO_EN, en, qos=QOS_PUB)
            if TOPIC_SPEECH_ZH:
                speech_zh = self.format_nearest(dets, lang="zh")
                if speech_zh:
                    self.client.publish(TOPIC_SPEECH_ZH, speech_zh, qos=QOS_PUB)
            if TOPIC_SPEECH_EN:
                speech_en = self.format_nearest(dets, lang="en")
                if speech_en:
                    self.client.publish(TOPIC_SPEECH_EN, speech_en, qos=QOS_PUB)

            if from_esp and RELAY_RAW_TOPIC and RELAY_RAW_TOPIC != msg.topic and "data" in payload:
                relay_payload = {"data": payload["data"], "_relay_skip": True}
                self.client.publish(RELAY_RAW_TOPIC, json.dumps(relay_payload), qos=QOS_PUB)

            if ann is not None and PUBLISH_ANN:
                ann_payload = {
                    "ts": out_msg["ts"],
                    "frame_id": out_msg["frame_id"],
                    "encoding": "jpg",
                    "data": base64.b64encode(ann).decode("ascii"),
                }
                self.client.publish(TOPIC_ANN, json.dumps(ann_payload), qos=QOS_PUB)
                if TOPIC_ANN_ALT:
                    self.client.publish(TOPIC_ANN_ALT, make_jpeg_data_url(ann_payload["data"]), qos=QOS_PUB)
        except Exception as e:
            print(f"Error handling frame: {e}")

    def decode_frame(self, payload):
        if "data" not in payload:
            return None
        data_b64 = payload["data"]
        if data_b64.startswith("data:image"):
            data_b64 = data_b64.split(",", 1)[1]
        data = base64.b64decode(data_b64)
        arr = np.frombuffer(data, dtype=np.uint8)
        frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        return frame

    def detect(self, frame, dist_scale: float = 1.0):
        h, w = frame.shape[:2]
        result = self.model(frame, verbose=False, conf=CONF_THRESH, imgsz=IMGSZ)[0]
        detections = []
        for box in result.boxes:
            conf = float(box.conf)
            if conf < CONF_THRESH:
                continue
            cls_id = int(box.cls)
            cls_name = self.class_names.get(cls_id, str(cls_id)) if isinstance(self.class_names, dict) else (
                self.class_names[cls_id] if cls_id < len(self.class_names) else str(cls_id)
            )
            if cls_name not in FRUIT_CLASSES:
                continue
            x1, y1, x2, y2 = box.xyxy[0].cpu().numpy().astype(int).tolist()
            bbox = [x1, y1, x2, y2]
            pix_h = max(1, y2 - y1)
            dist_m = estimate_distance_m(bbox, FRUIT_HEIGHT_M, FOCAL_PX) * dist_scale
            detections.append(
                {
                    "id": cls_name,
                    "id_zh": CLASS_NAME_ZH.get(cls_name, cls_name),
                    "conf": round(conf, 3),
                    "bbox": bbox,
                    "pix_h": pix_h,
                    "dist_m": round(dist_m, 2),
                    "side": side_of_frame(bbox, w),
                }
            )
        annotated = self.draw_annotations(frame, detections)
        if not detections:
            print("[det] no fruit detected")
        return detections, annotated

    def draw_annotations(self, frame, detections):
        for det in detections:
            x1, y1, x2, y2 = det["bbox"]
            color = (0, 255, 0)
            label = f"{det['id']} {det['conf']:.2f} {det['dist_m']}m"
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            cv2.putText(frame, label, (x1, max(15, y1 - 5)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
        ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
        if not ok:
            return None
        return buf.tobytes()

    def format_text(self, detections: List[dict], lang: str) -> str:
        if not detections:
            return "沒有偵測到水果" if lang == "zh" else "No fruits detected"
        parts = []
        for det in detections:
            cls = det["id"]
            cls_zh = CLASS_NAME_ZH.get(cls, cls)
            side_zh = SIDE_ZH.get(det.get("side"), det.get("side", ""))
            side_en = SIDE_EN.get(det.get("side"), det.get("side", ""))
            if lang == "zh":
                parts.append(f"{cls_zh} {det['dist_m']}公尺 {side_zh} (置信 {det['conf']:.2f})")
            else:
                parts.append(f"{cls} {det['dist_m']}m on {side_en} (conf {det['conf']:.2f})")
        prefix = f"偵測到{len(detections)}項：" if lang == "zh" else f"Detected {len(detections)}: "
        sep = "； " if lang == "zh" else "; "
        return prefix + sep.join(parts)

    def format_nearest(self, detections: List[dict], lang: str) -> str:
        if not detections:
            return None
        # Only consider high-confidence detections for speech
        strong = [d for d in detections if d.get("conf", 0) >= SPEECH_CONF_MIN]
        if not strong:
            return None
        nearest = min(strong, key=lambda d: d.get("dist_m", 1e9))
        cls = nearest["id"]
        cls_zh = CLASS_NAME_ZH.get(cls, cls)
        side_zh = SIDE_ZH.get(nearest.get("side"), nearest.get("side", ""))
        side_en = SIDE_EN.get(nearest.get("side"), nearest.get("side", ""))
        dist = nearest.get("dist_m")
        dist_zh = f"{dist:.2f}公尺" if isinstance(dist, (int, float)) else ""
        dist_en = f"{dist:.2f}m" if isinstance(dist, (int, float)) else ""
        side_phrase_zh = (
            "前方左側" if side_zh == "左側" else "正前方" if side_zh == "正前" else "前方右側" if side_zh == "右側" else "前方"
        )
        side_phrase_en = (
            "ahead on your left" if side_en == "left" else "straight ahead" if side_en == "center" else "ahead on your right"
            if side_en == "right" else "ahead"
        )
        if lang == "zh":
            return f"{side_phrase_zh}有{cls_zh}，距離{dist_zh}" if dist_zh else f"{side_phrase_zh}有{cls_zh}"
        return f"{cls} {dist_en} {side_phrase_en}".strip()


if __name__ == "__main__":
    FruitDetector().run()

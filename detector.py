"""
Detector node (YOLOv8):
- Subscribes to assist/cam/raw (JPEG base64 or data URL)
- Runs YOLOv8 (default yolov8n.pt) via Ultralytics
- Publishes detections to assist/detections (JSON)
- Publishes annotated JPEGs to ntut/ProcessImage (data URL only)
- Publishes detection text to ntut/ProcessInfoZh / ntut/ProcessInfoEn
- Publishes nearest-object text (for TTS) to ntut/ProcessSpeechZh / ntut/ProcessSpeechEn
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
import torch

# Allow safe unpickling for ultralytics DetectionModel on newer torch versions (2.6+)
try:
    from torch.serialization import add_safe_globals
    from ultralytics.nn.tasks import DetectionModel

    add_safe_globals([DetectionModel])
except Exception as e:
    # Older torch versions may not have add_safe_globals; proceed silently.
    print(f"Safe globals registration skipped: {e}")


BROKER = os.getenv("MQTT_BROKER", "localhost")
PORT = int(os.getenv("MQTT_PORT", "1883"))
USERNAME = os.getenv("MQTT_USER")
PASSWORD = os.getenv("MQTT_PASS")
USE_TLS = os.getenv("MQTT_TLS", "0") == "1"
TOPIC_RAW = os.getenv("TOPIC_RAW", "assist/cam/raw")
TOPIC_DET = os.getenv("TOPIC_DET", "assist/detections")
TOPIC_ANN = os.getenv("TOPIC_ANN", "assist/cam/annotated")
TOPIC_ANN_ALT = os.getenv("TOPIC_ANN_ALT", "ntut/ProcessImage")  # annotated image data URL
TOPIC_ANN_ALT_RAW_ONLY = os.getenv("TOPIC_ANN_ALT_RAW_ONLY", "0") == "1"  # unused but kept for compat
TOPIC_INFO = os.getenv("TOPIC_INFO", "ntut/ProcessInfo")  # JSON detections passthrough
TOPIC_INFO_ZH = os.getenv("TOPIC_INFO_ZH", "ntut/ProcessInfoZh")  # Chinese text topic
TOPIC_INFO_EN = os.getenv("TOPIC_INFO_EN", "ntut/ProcessInfoEn")  # English text topic
TOPIC_SPEECH_ZH = os.getenv("TOPIC_SPEECH_ZH", "ntut/ProcessSpeechZh")  # nearest object text for TTS (Chinese)
TOPIC_SPEECH_EN = os.getenv("TOPIC_SPEECH_EN", "ntut/ProcessSpeechEn")  # nearest object text for TTS (English)
PUBLISH_ANN = os.getenv("PUBLISH_ANN", "0") == "1"

MODEL_PATH = os.getenv("YOLO_MODEL", "yolov8n.pt")
CONF_THRESH = float(os.getenv("CONF_THRESH", "0.25"))
FOCAL_PX = float(os.getenv("FOCAL_PX", "900"))  # calibrate for your camera
DEFAULT_HEIGHT_M = float(os.getenv("OBJ_HEIGHT_M", "1.6"))  # default person height

QOS_SUB = 1
QOS_PUB = 1


def make_jpeg_data_url(b64: str) -> str:
    return f"data:image/jpeg;base64,{b64}"


def class_color(name: str) -> Tuple[int, int, int]:
    palette = [
        (0, 255, 0),
        (255, 0, 0),
        (0, 128, 255),
        (255, 128, 0),
        (255, 0, 255),
        (0, 255, 255),
        (128, 0, 255),
        (128, 255, 0),
        (0, 0, 255),
        (255, 255, 0),
    ]
    h = abs(hash(name))
    return palette[h % len(palette)]


CLASS_NAME_ZH = {
    "person": "人",
    "umbrella": "雨傘",
    "kite": "風箏",
    "car": "車",
    "truck": "卡車",
    "bus": "公車",
    "train": "火車",
    "motorcycle": "機車",
    "bicycle": "腳踏車",
    "cat": "貓",
    "dog": "狗",
    "bird": "鳥",
    "horse": "馬",
    "sheep": "羊",
    "cow": "牛",
    "bear": "熊",
    "zebra": "斑馬",
    "giraffe": "長頸鹿",
    "traffic light": "紅綠燈",
    "fire hydrant": "消防栓",
    "stop sign": "停止標誌",
    "bench": "長椅",
    "chair": "椅子",
    "sofa": "沙發",
    "bed": "床",
    "dining table": "餐桌",
    "potted plant": "盆栽",
    "tv": "電視",
    "laptop": "筆電",
    "mouse": "滑鼠",
    "keyboard": "鍵盤",
    "cell phone": "手機",
    "remote": "遙控器",
    "microwave": "微波爐",
    "oven": "烤箱",
    "toaster": "烤麵包機",
    "sink": "洗手槽",
    "refrigerator": "冰箱",
    "book": "書",
    "clock": "時鐘",
    "vase": "花瓶",
    "scissors": "剪刀",
    "teddy bear": "泰迪熊",
    "toothbrush": "牙刷",
}

SIDE_ZH = {"left": "左側", "center": "正前", "right": "右側"}
SIDE_EN = {"left": "left", "center": "center", "right": "right"}


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


class Detector:
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
        self.client.subscribe(TOPIC_RAW, qos=QOS_SUB)
        print(f"Detector (YOLOv8) subscribed to {TOPIC_RAW}, publishing detections to {TOPIC_DET}")
        if PUBLISH_ANN:
            print(f"Annotated frames will be published to {TOPIC_ANN}")

    def run(self):
        self.client.loop_forever()

    def on_message(self, _cli, _userdata, msg):
        try:
            try:
                raw = json.loads(msg.payload)
            except json.JSONDecodeError:
                raw = msg.payload.decode("ascii", errors="ignore")
            payload = {"data": raw} if isinstance(raw, str) else raw
            frame = self.decode_frame(payload)
            if frame is None:
                print("Frame decode failed; skipping message")
                return
            dets, ann = self.detect(frame)
            out_msg = {
                "frame_id": payload.get("frame_id"),
                "ts": int(time.time() * 1000),
                "objects": dets,
            }
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
            if ann is not None:
                ann_payload = {
                    "ts": out_msg["ts"],
                    "frame_id": out_msg["frame_id"],
                    "encoding": "jpg",
                    "data": base64.b64encode(ann).decode("ascii"),
                }
                if PUBLISH_ANN:
                    self.client.publish(TOPIC_ANN, json.dumps(ann_payload), qos=QOS_PUB)
                if TOPIC_ANN_ALT:
                    data_url = make_jpeg_data_url(ann_payload["data"])
                    # ProcessImage sends data URL only
                    self.client.publish(TOPIC_ANN_ALT, data_url, qos=QOS_PUB)
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

    def detect(self, frame):
        h, w = frame.shape[:2]
        result = self.model(frame, verbose=False)[0]
        detections = []

        for box in result.boxes:
            conf = float(box.conf)
            if conf < CONF_THRESH:
                continue
            cls_id = int(box.cls)
            x1, y1, x2, y2 = box.xyxy[0].cpu().numpy().astype(int).tolist()
            bbox = [x1, y1, x2, y2]
            cls_name = self.class_names.get(cls_id, str(cls_id)) if isinstance(self.class_names, dict) else (
                self.class_names[cls_id] if cls_id < len(self.class_names) else str(cls_id)
            )
            dist_m = estimate_distance_m(bbox, DEFAULT_HEIGHT_M, FOCAL_PX)
            color = class_color(cls_name)
            detections.append(
                {
                    "id": cls_name,
                    "conf": round(conf, 3),
                    "bbox": bbox,
                    "dist_m": round(dist_m, 2),
                    "side": side_of_frame(bbox, w),
                    "color_bgr": color,
                }
            )

        annotated = self.draw_annotations(frame, detections)
        return detections, annotated

    def draw_annotations(self, frame, detections):
        for det in detections:
            x1, y1, x2, y2 = det["bbox"]
            color = det.get("color_bgr", (0, 255, 0))
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            label = f"{det['id']} {det['conf']:.2f} {det['dist_m']}m"
            cv2.putText(frame, label, (x1, max(15, y1 - 5)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
        ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
        if not ok:
            return None
        return buf.tobytes()

    def format_text(self, detections: List[dict], lang: str) -> str:
        if not detections:
            return "沒有偵測到物件" if lang == "zh" else "No objects detected"
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
        nearest = min(detections, key=lambda d: d.get("dist_m", 1e9))
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
    Detector().run()

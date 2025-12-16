# Assistance for the Blind - MQTT Vision Pipeline

English | [中文](#中文說明)

## Overview
AIoT vision pipeline using MQTT + YOLOv8. Frames come from video, webcam, or ESP32-CAM (data URL or binary JPEG). Detectors publish detections, annotated images, multilingual summaries, and speech-friendly text for the nearest object.

## Components
- `detector.py` — General YOLOv8 detector for all COCO classes. Subscribes to `ntut/SourceImage` (data URL) and `ntut/CAM/SourceImage` (ESP32 bytes). Publishes detections, annotated images, info text, and speech text.
- `fruit_detector.py` — Fruit-focused detector (apple/banana/orange/broccoli/carrot). Subscribes to the same topics; publishes to the same downstream topics. Speech only uses high-confidence detections (`SPEECH_CONF_MIN`, default 0.8).
- `video_pub.py` / `camera_pub.py` — Publish video/webcam frames. Send data URL to `ntut/SourceImage` and metadata JSON to `ntut/SourceMeta`.
- `send_fruit_image.py` — Send a local image to MQTT (data URL string by default; set `USE_JSON=1` for JSON).
- `sub_source_image.py` — Subscribe to `ntut/SourceImage` for debugging; can save received JPEG.
- `alerts_node.py`, `testToMQTT.py` — Auxiliary MQTT tools.

## Default MQTT topics
- Input:
  - `ntut/SourceImage` — Raw image as data URL string (preferred by detectors).
  - `ntut/CAM/SourceImage` — ESP32-CAM raw JPEG bytes (detectors accept and re-publish as data URL).
  - `ntut/SourceMeta` — Frame metadata JSON.
- Detector outputs (both detectors):
  - `assist/detections` — JSON detections.
  - `assist/cam/annotated` — Annotated JPEG (when `PUBLISH_ANN=1`).
  - `ntut/ProcessImage` — Annotated image as data URL.
  - `ntut/ProcessInfoZh` / `ntut/ProcessInfoEn` — Text summary.
  - `ntut/ProcessSpeechZh` / `ntut/ProcessSpeechEn` — Nearest-object speech text (only high-conf for fruit_detector when `SPEECH_CONF_MIN` is set).

## Setup
```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

## Publish video/webcam
```powershell
$env:MQTT_BROKER="jetsion.com"
$env:MQTT_PORT="1883"
$env:TOPIC_RAW_ALT="ntut/SourceImage"      # data URL
$env:TOPIC_RAW_ALT_META="ntut/SourceMeta"  # metadata JSON
python video_pub.py   # or: python camera_pub.py
```
Useful vars: `VIDEO_PATH`, `SLEEP_SEC`, `LOOP_VIDEO`, `FRAME_ID`, `CAM_INDEX`, `CAM_WIDTH`, `CAM_HEIGHT`, `CAM_FPS`, `JPEG_QUALITY`.

## Run general detector
```powershell
$env:MQTT_BROKER="jetsion.com"
$env:MQTT_PORT="1883"
$env:TOPIC_RAW="ntut/SourceImage"
$env:TOPIC_RAW_ESP="ntut/CAM/SourceImage"
$env:PUBLISH_ANN="1"
python detector.py
```
Key tunables: `YOLO_MODEL` (default `yolov8n.pt`), `CONF_THRESH`, `FOCAL_PX`, `OBJ_HEIGHT_M`, `DIST_MULTIPLIER_ESP` (default 0.1 for ESP32 wide-FOV), `TOPIC_*` for outputs.

## Run fruit detector
```powershell
$env:MQTT_BROKER="jetsion.com"
$env:MQTT_PORT="1883"
$env:TOPIC_RAW="ntut/SourceImage"
$env:TOPIC_RAW_ESP="ntut/CAM/SourceImage"
$env:PUBLISH_ANN="1"
$env:SPEECH_CONF_MIN="0.8"   # only speak nearest fruit if conf >= 0.8
python fruit_detector.py
```
Fruit classes: apple, banana, orange, broccoli, carrot. Tunables: `CONF_THRESH`, `IMGSZ` (default 1280), `FOCAL_PX`, `FRUIT_HEIGHT_M` (default 0.08m), `DIST_MULTIPLIER_ESP`, `SPEECH_CONF_MIN`.

## Send a single test image
```powershell
# data URL payload (default), QoS0 recommended
$env:QOS="0"
python send_fruit_image.py

# JSON payload instead
$env:USE_JSON="1"
python send_fruit_image.py
```
If subscribers join later, set `$env:RETAIN="1"` to keep the last message.

## Subscribe for debugging
```powershell
python sub_source_image.py           # waits 30s on ntut/SourceImage
$env:SAVE_JPG="1"; python sub_source_image.py   # also saves recv.jpg
```

## Distance calibration
- For people (detector.py): tune `FOCAL_PX` and `OBJ_HEIGHT_M`; `DIST_MULTIPLIER_ESP` scales ESP32 distances (default 0.1 = divide by 10).
- For fruits (fruit_detector.py): tune `FOCAL_PX`, `FRUIT_HEIGHT_M`, and `DIST_MULTIPLIER_ESP`. Use `pix_h` and `dist_m` in detections to calibrate.

## 中文說明
- `detector.py`：一般物件偵測，訂閱 `ntut/SourceImage` / `ntut/CAM/SourceImage`，輸出偵測 JSON、標註圖、中文/英文摘要與最近物件語音文字。
- `fruit_detector.py`：水果偵測（蘋果/香蕉/橘子/花椰菜/紅蘿蔔），同樣訂閱上述來源並輸出相同 topics；語音僅播報信心度 ≥ `SPEECH_CONF_MIN` 的最近水果。
- 影像來源：`video_pub.py`/`camera_pub.py`（發 data URL + metadata），ESP32-CAM 直傳二進位 JPEG 走 `ntut/CAM/SourceImage`。
- 測試與除錯：`send_fruit_image.py`（送單張）、`sub_source_image.py`（訂閱檢查，可存圖）。
- 重要環境變數：`MQTT_BROKER`、`MQTT_PORT`、`TOPIC_RAW`、`TOPIC_RAW_ESP`、`PUBLISH_ANN`、`YOLO_MODEL`、`CONF_THRESH`、`FOCAL_PX`、`OBJ_HEIGHT_M`、`FRUIT_HEIGHT_M`、`DIST_MULTIPLIER_ESP`、`SPEECH_CONF_MIN`。

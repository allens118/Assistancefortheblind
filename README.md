# Assistance for the Blind - MQTT Vision Pipeline

English | [中文](#中文說明)

## Overview
This project builds an AIoT-based assistive vision pipeline. It captures camera/video frames via MQTT, runs YOLOv8 to detect objects, and simulates assistive responses: annotated images, multilingual summaries, and speech-friendly nearest-object cues. It enables real-time analysis and interaction-oriented feedback for accessibility scenarios.

## Features
- JPEG frames → MQTT (`assist/cam/raw` by default or `ntut/SourceImage` for data-URL only)
- YOLOv8 detection with per-class colors
- Annotated image out as data URL (`ntut/ProcessImage`)
- Text summaries (EN/ZH) and nearest-object speech text (EN/ZH)
- Metadata separated from image payloads (e.g., `ntut/SourceMeta`)

## MQTT Topics (current defaults)
- Input:
  - `ntut/SourceImage`: data URL string of the raw JPEG (from camera_pub/video_pub)
  - `ntut/SourceMeta`: JSON metadata for the raw frame (ts, w, h, frame_id, encoding, data as base64)
- Detector outputs:
  - `assist/detections`: JSON of all detections
  - `ntut/ProcessImage`: annotated image as data URL
  - `ntut/ProcessInfoZh`: Chinese text summary of all detections
  - `ntut/ProcessInfoEn`: English text summary of all detections
  - `ntut/ProcessSpeechZh`: Chinese sentence for the nearest object (for TTS)
  - `ntut/ProcessSpeechEn`: English sentence for the nearest object (for TTS)
  - (Optional) `assist/cam/annotated` when `PUBLISH_ANN=1`

## Quick start
```bash
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

### Publish video or camera
```powershell
$env:MQTT_BROKER="jetsion.com"
$env:MQTT_PORT="1883"
$env:TOPIC_RAW_ALT="ntut/SourceImage"   # image as data URL
$env:TOPIC_RAW_ALT_META="ntut/SourceMeta"  # metadata JSON
python video_pub.py   # or python camera_pub.py
```
Useful vars: `VIDEO_PATH`, `SLEEP_SEC`, `LOOP_VIDEO`, `FRAME_ID`, `CAM_INDEX`, `CAM_WIDTH`, `CAM_HEIGHT`, `CAM_FPS`.

### Run detector
```powershell
$env:MQTT_BROKER="jetsion.com"
$env:MQTT_PORT="1883"
$env:TOPIC_RAW="ntut/SourceImage"
$env:TOPIC_ANN_ALT="ntut/ProcessImage"
$env:TOPIC_INFO_ZH="ntut/ProcessInfoZh"
$env:TOPIC_INFO_EN="ntut/ProcessInfoEn"
$env:TOPIC_SPEECH_ZH="ntut/ProcessSpeechZh"
$env:TOPIC_SPEECH_EN="ntut/ProcessSpeechEn"
$env:PUBLISH_ANN="1"   # if you also want assist/cam/annotated
python detector.py
```
Useful vars: `YOLO_MODEL` (default `yolov8n.pt`), `CONF_THRESH`, `FOCAL_PX`, `OBJ_HEIGHT_M`.

## File roles
- `video_pub.py` / `camera_pub.py`: publish frames; data URL to `ntut/SourceImage`, metadata to `ntut/SourceMeta`.
- `detector.py`: YOLOv8 inference, annotated images to `ntut/ProcessImage`, detection JSON to `assist/detections`, text to `ntut/ProcessInfoZh/En`, nearest-object speech text to `ntut/ProcessSpeechZh/En`.
- `alerts_node.py` / `testToMQTT.py`: auxiliary MQTT tools.

## Stack (current usage)
- Software: Python 3.9+, OpenCV, paho-mqtt, Ultralytics YOLOv8, NumPy; Django platform subscribes to MQTT and renders UI (live/processed images, multilingual text, speech).
- Firmware/Devices: ESP32-CAM for live image publish to MQTT; optionally video files for simulation.
- Messaging: MQTT broker (tested `jetsion.com:1883`), topics listed above.
- Platform: Django-based web front-end subscribing to MQTT to show raw/processed streams, text summaries (multi-language), and play speech prompts.
- Optional media: `.mp4` clips used for simulation; YOLO weight `.pt` files.

## Ignore list
`.gitignore` excludes `.venv/`, pycache, `.pt`, `.mp4`, logs, etc. Keep large weights/videos out of git.

---

## 中文說明

### 簡介
本專案是一套 AIoT 式的助盲視覺管線：透過 MQTT 收集相機/影片影格，使用 YOLOv8 即時偵測，並輸出標註圖片、多語摘要與最近物件的語音化提示，模擬不同場景下的輔助回饋。

### 功能
- JPEG 影格發佈；`ntut/SourceImage` 只送 data URL 圖片，`ntut/SourceMeta` 分送中繼資料
- YOLOv8 偵測，類別顏色區分
- 標註圖以 data URL 發到 `ntut/ProcessImage`
- 偵測摘要文字：中文 `ntut/ProcessInfoZh`、英文 `ntut/ProcessInfoEn`
- 最近物件語音句：中文 `ntut/ProcessSpeechZh`、英文 `ntut/ProcessSpeechEn`

### MQTT 主題（預設）
- 輸入：`ntut/SourceImage`（圖片 data URL）、`ntut/SourceMeta`（JSON 中繼資料）
- 偵測輸出：`assist/detections`（JSON）、`ntut/ProcessImage`（標註圖 data URL）、`ntut/ProcessInfoZh` / `ntut/ProcessInfoEn`（摘要文字）、`ntut/ProcessSpeechZh` / `ntut/ProcessSpeechEn`（最近物件語音句）
- 若 `PUBLISH_ANN=1`：同時發 `assist/cam/annotated`

### 快速啟動
```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

發佈端（影片/相機）：
```powershell
$env:MQTT_BROKER="jetsion.com"
$env:MQTT_PORT="1883"
$env:TOPIC_RAW_ALT="ntut/SourceImage"
$env:TOPIC_RAW_ALT_META="ntut/SourceMeta"
python video_pub.py   # 或 python camera_pub.py
```

偵測端：
```powershell
$env:MQTT_BROKER="jetsion.com"
$env:MQTT_PORT="1883"
$env:TOPIC_RAW="ntut/SourceImage"
$env:TOPIC_ANN_ALT="ntut/ProcessImage"
$env:TOPIC_INFO_ZH="ntut/ProcessInfoZh"
$env:TOPIC_INFO_EN="ntut/ProcessInfoEn"
$env:TOPIC_SPEECH_ZH="ntut/ProcessSpeechZh"
$env:TOPIC_SPEECH_EN="ntut/ProcessSpeechEn"
$env:PUBLISH_ANN="1"
python detector.py
```

常用變數：`VIDEO_PATH`、`SLEEP_SEC`、`FRAME_ID`、`CAM_INDEX`/`CAM_WIDTH`/`CAM_HEIGHT`/`CAM_FPS`、`YOLO_MODEL`、`CONF_THRESH`、`FOCAL_PX`、`OBJ_HEIGHT_M`。

### 檔案說明
- `video_pub.py` / `camera_pub.py`：發佈影格；`ntut/SourceImage` 為 data URL 圖，`ntut/SourceMeta` 為中繼資料 JSON。
- `detector.py`：YOLOv8 偵測，輸出標註圖與文字/語音描述。
- 其餘為輔助 MQTT 範例工具。

### 軟硬體/平台
- 軟體：Python 3.9+、OpenCV、paho-mqtt、Ultralytics YOLOv8、NumPy；Django 物聯網平台訂閱 MQTT，顯示即時/處理後影像、多國語文字描述並播放語音。
- 硬體/韌體：ESP32-CAM 作為即時影像傳輸到 MQTT；亦可用影片檔模擬。
- 通訊：MQTT broker（測試 `jetsion.com:1883`），主題同上。
- 平台：Django 架構的前端訂閱 MQTT，呈現原始/標註影像、中文/英文解析文字與語音播放。
- 媒體：`.mp4` 影片用於模擬；YOLO `.pt` 權重檔。

### Git 忽略
`.gitignore` 已排除 `.venv/`、暫存檔、`.pt`、`.mp4` 等大型檔案，避免推上遠端。

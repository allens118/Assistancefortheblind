# Assistance for the Blind - MQTT Vision Pipeline

這裡提供最小可行的程式骨架，透過 MQTT 串接攝影機、YOLOv3-tiny 偵測、危險警示：

- `assist/cam/raw`：來源影像 (JPEG base64)
- `assist/cam/annotated`：畫框後影像 (選用，環境變數 `PUBLISH_ANN=1`)
- `assist/detections`：偵測清單 (含距離、方位)
- `assist/alerts`：精簡危險提示 (給語音/震動)

## 安裝
```bash
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

## 準備 YOLOv3-tiny 權重
下載官方檔案並放到 `models/`：
```
models/yolov3-tiny.cfg
models/yolov3-tiny.weights
models/coco.names
```
可由 https://pjreddie.com/darknet/yolo/ 取得。若路徑不同，可用環境變數 `YOLO_CFG`, `YOLO_WEIGHTS`, `YOLO_NAMES` 指定。

## 執行流程
開三個終端機 (或用 tmux)：

1) 發佈攝影機影像
```bash
set MQTT_BROKER=jetsion.com
python camera_pub.py
```
環境參數：
- `CAM_INDEX` (預設 0)、`CAM_WIDTH`/`CAM_HEIGHT`、`CAM_FPS`、`FRAME_ID`

若要用影片模擬攝影機、每 10 秒送一張：
```bash
set MQTT_BROKER=jetsion.com
set VIDEO_PATH=14881231_3840_2160_24fps.mp4
set SLEEP_SEC=10   # 發布間隔秒數
python video_pub.py
```
環境參數：
- `VIDEO_PATH`：影片路徑
- `SLEEP_SEC`：每張影像的發布間隔（牆鐘時間）
- `LOOP_VIDEO`：預設 1，播完重頭；設為 0 到尾即停
- `FRAME_ID`、`JPEG_QUALITY`、`TOPIC_RAW`

2) 偵測節點（YOLOv8，預設 yolov8n.pt）
```bash
set MQTT_BROKER=jetsion.com
set PUBLISH_ANN=1
python detector.py
```
環境參數：
- `YOLO_MODEL`：預設 `yolov8n.pt`（可換 yolov8s.pt 或自行訓練的 .pt）
- `CONF_THRESH` (預設 0.25)、`FOCAL_PX` (依相機校正)、`OBJ_HEIGHT_M` (預設 1.6m)
- `TOPIC_RAW`/`TOPIC_DET`/`TOPIC_ANN`

3) 危險提示節點
```bash
set MQTT_BROKER=jetsion.com
python alerts_node.py
```
環境參數：
- `ALERT_DIST_M` (預設 2.5m)、`SUPPRESS_MS` (預設 800ms 節流)
- `IMPORTANT_CLASSES` (逗號分隔，預設 person,car,bus,truck,bicycle,motorbike)

## 節點說明
- `camera_pub.py`：抓攝影機影像、JPEG、base64，上傳到 `assist/cam/raw`
- `detector.py`：YOLOv3-tiny 推論，發布 `assist/detections`，可選擇發布 `assist/cam/annotated`
- `alerts_node.py`：從偵測結果挑最近的重要類別，產生 `assist/alerts`（level/reason/side/dist_m/action）

## 診斷與調教
- FOCAL_PX 校正：用已知高度的物體 (如 1.6m) 站在已知距離 d，量測 bbox 像素高度 h，`focal_px = d * h / H_real`
- 若頻寬吃緊，降低 `CAM_FPS` 或 JPEG 品質（在 `camera_pub.py` 內可調 IMWRITE_JPEG_QUALITY）
- 若要壓低延遲，可將 MQTT QoS 調為 0（影像類別）

## 安全與隱私
- 若影像含個資，盡量使用本地 broker；或僅傳送偵測結果 (`assist/detections`/`assist/alerts`)

## 待辦/可擴充
- 加入語音/TTS 節點訂閱 `assist/alerts`
- 支援雙鏡頭或深度資訊，以提高距離估計可靠度
- 將 `FOCAL_PX`/`OBJ_HEIGHT_M` 配置化 (retain 至 `assist/config`) 供遠端更新

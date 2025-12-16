"""
Send a local fruit image to MQTT as base64 JPEG for testing fruit_detector.
"""

import base64
import json
import os
import cv2
from paho.mqtt import client as mqtt


def main():
    broker = os.getenv("MQTT_BROKER", "jetsion.com")
    port = int(os.getenv("MQTT_PORT", "1883"))
    topic = os.getenv("TOPIC_RAW", "ntut/SourceImage")
    img_path = os.getenv("IMG_PATH", "fruit000.png")
    frame_id = os.getenv("FRAME_ID", "fruit01")
    qos = int(os.getenv("QOS", "1"))
    retain = os.getenv("RETAIN", "0") == "1"
    use_json = os.getenv("USE_JSON", "0") == "1"  # default: send plain data URL string

    img = cv2.imread(img_path)
    if img is None:
        raise SystemExit(f"Cannot read image: {img_path}")

    ok, buf = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
    if not ok:
        raise SystemExit("JPEG encode failed")

    b64 = base64.b64encode(buf).decode("ascii")
    if use_json:
        payload = json.dumps({"data": b64, "frame_id": frame_id})
    else:
        payload = f"data:image/jpeg;base64,{b64}"

    cli = mqtt.Client()
    cli.connect(broker, port, keepalive=30)
    info = cli.publish(topic, payload, qos=qos, retain=retain)
    info.wait_for_publish(timeout=5)
    cli.loop(0.1)  # flush network buffers
    cli.disconnect()
    print(
        f"Published {img_path} to {broker}:{port} topic {topic} "
        f"frame_id={frame_id} qos={qos} retain={retain} delivered={info.is_published()}"
    )


if __name__ == "__main__":
    main()

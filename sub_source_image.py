"""
Subscribe to a topic (default ntut/SourceImage) and print message size.
Useful to verify MQTT is receiving the published fruit images.
"""

import os
import time
import json
import base64
import cv2
from paho.mqtt import client as mqtt


def main():
    broker = os.getenv("MQTT_BROKER", "jetsion.com")
    port = int(os.getenv("MQTT_PORT", "1883"))
    topic = os.getenv("TOPIC_RAW", "ntut/SourceImage")
    save_jpg = os.getenv("SAVE_JPG", "0") == "1"
    jpg_path = os.getenv("JPG_PATH", "recv.jpg")
    timeout = float(os.getenv("TIMEOUT_SEC", "30"))

    got = []

    def on_message(_c, _u, msg):
        print(f"[sub] topic={msg.topic} bytes={len(msg.payload)}")
        try:
            data = msg.payload
            try:
                obj = json.loads(data)
                if isinstance(obj, dict) and "data" in obj:
                    b64 = obj["data"]
                    if isinstance(b64, str):
                        raw = base64.b64decode(b64.split(",", 1)[-1])
                        print(f"[sub] decoded base64 len={len(raw)}")
                        if save_jpg:
                            with open(jpg_path, "wb") as f:
                                f.write(raw)
                            print(f"[sub] saved {jpg_path}")
                        arr = cv2.imdecode(
                            np.frombuffer(raw, dtype="uint8"), cv2.IMREAD_COLOR
                        )
                        if arr is not None:
                            print(f"[sub] image shape {arr.shape}")
            except Exception as e:
                print(f"[sub] decode error: {e}")
        finally:
            got.append(True)
            _c.disconnect()

    cli = mqtt.Client()
    cli.on_message = on_message
    cli.connect(broker, port, keepalive=10)
    cli.subscribe(topic)
    cli.loop_start()
    t0 = time.time()
    while time.time() - t0 < timeout and not got:
        time.sleep(0.5)
    cli.loop_stop()
    cli.disconnect()
    if not got:
        print(f"[sub] no message within {timeout}s on {topic}")


if __name__ == "__main__":
    import numpy as np

    main()

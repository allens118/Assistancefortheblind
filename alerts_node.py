"""
Alerts node:
- Subscribes to assist/detections
- Applies simple threat rules and publishes to assist/alerts
"""

import json
import os
import time
from typing import Dict, List

from paho.mqtt import client as mqtt


BROKER = os.getenv("MQTT_BROKER", "localhost")
PORT = int(os.getenv("MQTT_PORT", "1883"))
USERNAME = os.getenv("MQTT_USER")
PASSWORD = os.getenv("MQTT_PASS")
USE_TLS = os.getenv("MQTT_TLS", "0") == "1"
TOPIC_DET = os.getenv("TOPIC_DET", "assist/detections")
TOPIC_ALERT = os.getenv("TOPIC_ALERT", "assist/alerts")

ALERT_DIST_M = float(os.getenv("ALERT_DIST_M", "2.5"))
SUPPRESS_MS = int(os.getenv("SUPPRESS_MS", "800"))  # rate limit alerts
IMPORTANT_CLASSES = set(os.getenv("IMPORTANT_CLASSES", "person,car,bus,truck,bicycle,motorbike").split(","))

last_alert_ts = 0


def choose_alert(objects: List[Dict]):
    # Pick nearest important object
    important = [o for o in objects if o.get("id") in IMPORTANT_CLASSES]
    if not important:
        return None
    nearest = min(important, key=lambda o: o.get("dist_m", 999))
    if nearest.get("dist_m", 999) > ALERT_DIST_M:
        return None
    return nearest


def connect_mqtt() -> mqtt.Client:
    client = mqtt.Client()
    if USERNAME:
        client.username_pw_set(USERNAME, PASSWORD or "")
    if USE_TLS:
        client.tls_set()
    client.connect(BROKER, PORT, keepalive=30)
    client.subscribe(TOPIC_DET, qos=1)
    return client


def on_message(client: mqtt.Client, _u, msg):
    global last_alert_ts
    try:
        payload = json.loads(msg.payload)
        objs = payload.get("objects", [])
        cand = choose_alert(objs)
        now_ms = int(time.time() * 1000)
        if cand and now_ms - last_alert_ts > SUPPRESS_MS:
            alert = {
                "level": "danger" if cand.get("dist_m", 999) < (ALERT_DIST_M / 2) else "warn",
                "reason": cand.get("id"),
                "side": cand.get("side", "center"),
                "dist_m": cand.get("dist_m"),
                "action": "stop" if cand.get("dist_m", 999) < 1.0 else "slow",
                "ttl_ms": SUPPRESS_MS,
                "ts": now_ms,
            }
            client.publish(TOPIC_ALERT, json.dumps(alert), qos=1)
            last_alert_ts = now_ms
    except Exception as e:
        print(f"Alert error: {e}")


def main():
    client = connect_mqtt()
    client.on_message = on_message
    print(f"Alerts listening on {TOPIC_DET}, publishing to {TOPIC_ALERT}")
    client.loop_forever()


if __name__ == "__main__":
    main()

import os
from paho.mqtt import client as mqtt
host=os.getenv("MQTT_BROKER","jetsion.com")
port=int(os.getenv("MQTT_PORT","1883"))
user=os.getenv("MQTT_USER")
pwd=os.getenv("MQTT_PASS")
tls=os.getenv("MQTT_TLS","0")=="1"
c=mqtt.Client()
if user: c.username_pw_set(user, pwd or "")
if tls: c.tls_set()
print("Connecting...", host, port, "TLS" if tls else "no TLS")
c.connect(host, port, 30)
print("Connected OK")
c.loop_start()
c.subscribe("assist/test", qos=1)
c.publish("assist/test", "hello", qos=1)
import time; time.sleep(1)
c.loop_stop()
c.disconnect()


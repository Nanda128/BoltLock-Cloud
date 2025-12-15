"""
MQTT Client Module for BoltLock
Handles all MQTT communication with the ESP32 device
"""

import json
from datetime import datetime

import paho.mqtt.client as mqtt


class BoltLockMQTTClient:
    def __init__(self, broker, port, username=None, password=None):
        self.broker = broker
        self.port = port
        self.username = username
        self.password = password
        self.client = None
        self.connected = False
        self.callbacks = {
            "on_status": None,
            "on_event": None,
            "on_connect": None,
            "on_disconnect": None,
        }

    def set_callback(self, event_type, callback):
        """Set callback function for specific event types"""
        if event_type in self.callbacks:
            self.callbacks[event_type] = callback

    def _parse_event(self, payload):
        """
        Parse event message from device.
        Supports both formats:
        1. JSON: {"event_type": "LOCK", "description": "...", "device_id": "..."}
        2. Text: *BoltLock Alert*\n*Event:* LOCK\n*Details:* [...]\n*Time:* [timestamp]
        """
        try:
            # Try JSON format first
            data = json.loads(payload)
            if "event_type" in data:
                return data
        except (json.JSONDecodeError, ValueError):
            pass

        # Try text format
        try:
            lines = payload.split("\n")
            event_type = None
            description = None
            
            for line in lines:
                if "*Event:*" in line:
                    event_type = line.split("*Event:*")[1].strip()
                elif "*Details:*" in line:
                    description = line.split("*Details:*")[1].strip()
            
            if event_type:
                return {
                    "event_type": event_type,
                    "description": description or "",
                    "device_id": None
                }
        except Exception as e:
            print(f"[MQTT] Error parsing event message: {e}")

        return None

    def on_connect(self, client, userdata, flags, rc):
        """MQTT connection callback"""
        if rc == 0:
            print(f"[MQTT] Connected to broker at {self.broker}:{self.port}")
            self.connected = True
            # Subscribe to topics
            from config import MQTT_TOPIC_EVENTS, MQTT_TOPIC_STATUS

            client.subscribe(MQTT_TOPIC_STATUS)
            client.subscribe(MQTT_TOPIC_EVENTS)
            print("[MQTT] Subscribed to topics")

            if self.callbacks["on_connect"]:
                self.callbacks["on_connect"]()
        else:
            print(f"[MQTT] Connection failed with code {rc}")
            self.connected = False

    def on_disconnect(self, client, userdata, rc):
        """MQTT disconnection callback"""
        self.connected = False
        print(f"[MQTT] Disconnected from broker (code: {rc})")

        if self.callbacks["on_disconnect"]:
            self.callbacks["on_disconnect"]()

    def on_message(self, client, userdata, msg):
        """MQTT message callback"""
        try:
            payload = msg.payload.decode("utf-8")
            topic = msg.topic

            print(f"[MQTT] Received on {topic}: {payload}")

            from config import MQTT_TOPIC_EVENTS, MQTT_TOPIC_STATUS

            if topic == MQTT_TOPIC_STATUS:
                # Handle status format: {"status": "online"} or with state info
                data = json.loads(payload)
                if self.callbacks["on_status"]:
                    self.callbacks["on_status"](data)

            elif topic == MQTT_TOPIC_EVENTS:
                # Parse event - support both JSON and text formats
                event = self._parse_event(payload)
                if event and self.callbacks["on_event"]:
                    self.callbacks["on_event"](event)

        except Exception as e:
            print(f"[MQTT] Error processing message: {e}")

    def connect(self):
        """Connect to MQTT broker"""
        try:
            self.client = mqtt.Client()
            self.client.on_connect = self.on_connect
            self.client.on_disconnect = self.on_disconnect
            self.client.on_message = self.on_message

            if self.username and self.password:
                self.client.username_pw_set(self.username, self.password)

            self.client.connect(self.broker, self.port, 60)
            self.client.loop_start()
            print(f"[MQTT] Connecting to {self.broker}:{self.port}...")
            return True
        except Exception as e:
            print(f"[MQTT] Failed to connect: {e}")
            return False

    def disconnect(self):
        """Disconnect from MQTT broker"""
        if self.client:
            self.client.loop_stop()
            self.client.disconnect()

    def publish_command(self, action, **kwargs):
        """Publish a command to the ESP32"""
        if not self.connected:
            print("[MQTT] Cannot publish - not connected")
            return False

        from config import MQTT_TOPIC_COMMAND

        command = {"action": action, "timestamp": datetime.now().isoformat(), **kwargs}

        try:
            self.client.publish(MQTT_TOPIC_COMMAND, json.dumps(command))
            print(f"[MQTT] Published command: {command}")
            return True
        except Exception as e:
            print(f"[MQTT] Failed to publish command: {e}")
            return False

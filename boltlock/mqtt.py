"""
MQTT Client Module for BoltLock
Handles all MQTT communication with the ESP32 device
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Callable, Dict, Optional

import paho.mqtt.client as mqtt


class BoltLockMQTTClient:
    def __init__(self, broker: str, port: int, username: str | None = None, password: str | None = None):
        self.broker = broker
        self.port = port
        self.username = username
        self.password = password
        self.client: mqtt.Client | None = None
        self.connected = False
        self.callbacks: Dict[str, Optional[Callable[..., None]]] = {
            "on_status": None,
            "on_event": None,
            "on_connect": None,
            "on_disconnect": None,
        }

    def set_callback(self, event_type: str, callback: Callable[..., None]) -> None:
        """Set callback function for specific event types"""
        if event_type in self.callbacks:
            self.callbacks[event_type] = callback

    @staticmethod
    def _normalise_event_type(value: Any) -> str:
        if value is None:
            return ""
        return str(value).strip().upper()

    @staticmethod
    def _safe_json_loads(payload: str) -> Optional[dict]:
        try:
            data = json.loads(payload)
            return data if isinstance(data, dict) else None
        except (json.JSONDecodeError, ValueError):
            return None

    def _parse_event(self, payload: str) -> Optional[dict]:
        """
        Parse event message from device.

        Accepts:
          - JSON: {"event":"lock","trigger":"button"}
          - JSON: {"event_type":"LOCK","description":"...","device_id":"..."}
          - Telegram-ish text:
                *BoltLock Alert*
                *Event:* LOCK
                *Details:* ...
        """
        data = self._safe_json_loads(payload)
        if data is not None:
            # Most common ESP format: {"event":"lock","trigger":"button"}
            if "event" in data:
                event_type = self._normalise_event_type(data.get("event"))
                trigger = str(data.get("trigger", "unknown")).strip()
                description = data.get("description") or f"Event triggered by: {trigger}"
                return {
                    "event_type": event_type,
                    "description": str(description),
                    "device_id": data.get("device_id") or data.get("device") or None,
                    "timestamp": data.get("timestamp") or None,
                    "raw": data,
                }

            # Alternate JSON format
            if "event_type" in data:
                return {
                    "event_type": self._normalise_event_type(data.get("event_type")),
                    "description": str(data.get("description", "")),
                    "device_id": data.get("device_id") or data.get("device") or None,
                    "timestamp": data.get("timestamp") or None,
                    "raw": data,
                }

            # If someone accidentally publishes {"action":"lock"} to events
            if "action" in data and str(data.get("action")).lower() in {"lock", "unlock"}:
                action = str(data.get("action")).lower()
                return {
                    "event_type": action.upper(),
                    "description": str(data.get("description") or "Event received from action field"),
                    "device_id": data.get("device_id") or data.get("device") or None,
                    "timestamp": data.get("timestamp") or None,
                    "raw": data,
                }

        # Text formats (from event_logger.c)
        try:
            # Strip some markdown noise and look for Event / Details lines
            lines = payload.splitlines()
            event_type = None
            description = ""

            # Match "*Event:* LOCK" or "Event: LOCK" etc
            event_re = re.compile(r"(?:\*?Event\*?:)\s*(.+)", re.IGNORECASE)
            details_re = re.compile(r"(?:\*?Details\*?:)\s*(.+)", re.IGNORECASE)

            for line in lines:
                line = line.strip()
                m1 = event_re.search(line)
                if m1:
                    event_type = m1.group(1).strip()
                    continue

                m2 = details_re.search(line)
                if m2:
                    description = m2.group(1).strip()
                    continue

            if event_type:
                return {
                    "event_type": self._normalise_event_type(event_type),
                    "description": description,
                    "device_id": None,
                    "timestamp": None,
                    "raw": payload,
                }
        except Exception as e:
            print(f"[MQTT] Error parsing event message: {e}")

        return None

    def _parse_status(self, payload: str) -> Optional[dict]:
        """
        Parse status/state messages from device.

        Accepts:
          - {"status":"online"}
          - {"state":"locked","method":"button"}
          - {"lock_state":"LOCKED","door_state":"CLOSED","device_id":"..."}
        """
        data = self._safe_json_loads(payload)
        if data is None:
            return None

        out: Dict[str, Any] = {"raw": data}

        # Online/offline
        if "status" in data:
            out["wifi_connected"] = str(data.get("status")).lower() == "online"

        if "wifi_connected" in data:
            out["wifi_connected"] = bool(data.get("wifi_connected"))

        # Lock state
        if "lock_state" in data:
            out["lock_state"] = str(data.get("lock_state"))
        elif "state" in data:
            state = str(data.get("state")).strip().lower()
            if state in {"locked", "unlocked", "unlocking"}:
                # Normalise to the same style your backend UI expects
                out["lock_state"] = state.upper()

        # Door state if present
        if "door_state" in data:
            out["door_state"] = str(data.get("door_state"))
        elif "door" in data:
            out["door_state"] = str(data.get("door"))

        # Optional fields
        if "method" in data:
            out["method"] = str(data.get("method"))

        out["device_id"] = data.get("device_id") or data.get("device") or None

        return out

    @staticmethod
    def _topic_eq(a: str, b: str) -> bool:
        return a.strip().lower() == b.strip().lower()

    def _topic_kind(self, topic: str) -> str:
        """
        Decide if a topic is status/event.
        We do not trust case. We also accept anything that ends with /status or /events.
        """
        from config.settings import MQTT_TOPIC_EVENTS, MQTT_TOPIC_STATUS

        t = topic.strip().lower()
        if self._topic_eq(topic, MQTT_TOPIC_STATUS) or t.endswith("/status"):
            return "status"
        if self._topic_eq(topic, MQTT_TOPIC_EVENTS) or t.endswith("/events"):
            return "events"
        return "unknown"

    def _subscribe_all(self, client: mqtt.Client) -> None:
        from config.settings import MQTT_TOPIC_EVENTS, MQTT_TOPIC_STATUS

        # Subscribe to configured topics plus wildcard bases for case differences
        topics = set()

        topics.add(MQTT_TOPIC_STATUS)
        topics.add(MQTT_TOPIC_EVENTS)
        topics.add(MQTT_TOPIC_STATUS.lower())
        topics.add(MQTT_TOPIC_EVENTS.lower())

        # Subscribe to both bases, eg "BoltLock/#" and "boltlock/#"
        base = MQTT_TOPIC_STATUS.split("/")[0] if "/" in MQTT_TOPIC_STATUS else MQTT_TOPIC_STATUS
        if base:
            topics.add(f"{base}/#")
            topics.add(f"{base.lower()}/#")

        for t in sorted(topics):
            try:
                client.subscribe(t)
            except Exception as e:
                print(f"[MQTT] Failed to subscribe to {t}: {e}")

        print(f"[MQTT] Subscribed to topics: {', '.join(sorted(topics))}")

    def on_connect(self, client: mqtt.Client, userdata: Any, flags: Any, rc: int) -> None:
        """MQTT connection callback"""
        if rc == 0:
            print(f"[MQTT] Connected to broker at {self.broker}:{self.port}")
            self.connected = True
            self._subscribe_all(client)

            cb = self.callbacks.get("on_connect")
            if cb:
                cb()
        else:
            print(f"[MQTT] Connection failed with code {rc}")
            self.connected = False

    def on_disconnect(self, client: mqtt.Client, userdata: Any, rc: int) -> None:
        """MQTT disconnection callback"""
        self.connected = False
        print(f"[MQTT] Disconnected from broker (code: {rc})")

        cb = self.callbacks.get("on_disconnect")
        if cb:
            cb()

    def on_message(self, client: mqtt.Client, userdata: Any, msg: Any) -> None:
        """MQTT message callback"""
        try:
            payload = msg.payload.decode("utf-8", errors="replace")
            topic = msg.topic

            print(f"[MQTT] Received on {topic}: {payload}")

            kind = self._topic_kind(topic)

            # If topic is unknown, try to infer from payload
            if kind == "unknown":
                data = self._safe_json_loads(payload)
                if isinstance(data, dict):
                    if "event" in data or "event_type" in data:
                        kind = "events"
                    elif "status" in data or "state" in data or "lock_state" in data:
                        kind = "status"

            if kind == "status":
                status = self._parse_status(payload)
                if status and self.callbacks.get("on_status"):
                    self.callbacks["on_status"](status)

            elif kind == "events":
                event = self._parse_event(payload)
                if event and self.callbacks.get("on_event"):
                    self.callbacks["on_event"](event)

        except Exception as e:
            print(f"[MQTT] Error processing message: {e}")

    def connect(self) -> bool:
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
            print(f"[MQTT] Connecting to {self.broker}:{self.port}.")
            return True
        except Exception as e:
            print(f"[MQTT] Failed to connect: {e}")
            return False

    def disconnect(self) -> None:
        """Disconnect from MQTT broker"""
        if self.client:
            self.client.loop_stop()
            self.client.disconnect()

    def publish_command(self, action: str, **kwargs: Any) -> bool:
        """Publish a command to the ESP32"""
        if not self.connected or not self.client:
            print("[MQTT] Cannot publish - not connected")
            return False

        from config.settings import MQTT_TOPIC_COMMAND

        command = {"action": action, "timestamp": datetime.now().isoformat(), **kwargs}

        try:
            self.client.publish(MQTT_TOPIC_COMMAND, json.dumps(command))
            print(f"[MQTT] Published command: {command}")
            return True
        except Exception as e:
            print(f"[MQTT] Failed to publish command: {e}")
            return False

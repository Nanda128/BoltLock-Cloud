"""
BoltLock Cloud Backend
MQTT-only smart door lock management system
"""

import json
from datetime import datetime

from config.settings import (
    MQTT_BROKER_HOST,
    MQTT_PORT,
    MQTT_USERNAME,
    MQTT_PASSWORD,
    MQTT_TOPIC_STATUS,
    MQTT_TOPIC_COMMAND,
    MQTT_TOPIC_EVENTS,
)
from boltlock.models import Event, Device, StateHistory
from boltlock.mqtt import BoltLockMQTTClient
from boltlock.database import (
    init_db,
    log_event as db_log_event,
    register_device,
    update_device_last_seen,
    log_state_change,
)

# Device state (in-memory snapshot for /api/status)
device_state = {
    "lock_state": "LOCKED",
    "door_state": "CLOSED",
    "wifi_connected": False,
    "last_update": None,
    "device_id": None,
}

events_buffer = []
MAX_EVENTS = 100

mqtt_client = None
mqtt_connected = False


def _parse_event_message(payload: str):
    """
    Parse event message from device.
    Supports multiple formats:
    1. JSON: {"event": "LOCK", "trigger": "button"} or {"event_type": "LOCK", "description": "..."}
    2. Text: *BoltLock Alert*\n*Event:* LOCK\n*Details:* [...]\n*Time:* [timestamp]
    """
    try:
        data = json.loads(payload)
        
        # Handle BoltLock firmware format: {"event": "lock", "trigger": "button"}
        if "event" in data:
            event_type = data.get("event", "").upper()
            trigger = data.get("trigger", "unknown")
            description = f"Event triggered by: {trigger}"
            return event_type, description, data.get("device_id")
        
        # Handle alternative format: {"event_type": "LOCK", "description": "..."}
        if "event_type" in data:
            return (
                data.get("event_type"),
                data.get("description", ""),
                data.get("device_id"),
            )
    except (json.JSONDecodeError, ValueError):
        pass

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
            return event_type, description or "", None
    except Exception as e:
        print(f"[MQTT] Error parsing event message: {e}")

    return None, None, None


def on_mqtt_status(data):
    """Handle MQTT status messages"""
    global device_state
    
    # Update in-memory state
    if "status" in data:
        device_state["wifi_connected"] = (data.get("status") == "online")

    for k in ["lock_state", "door_state", "device_id", "wifi_connected"]:
        if k in data:
            device_state[k] = data[k]

    device_state["last_update"] = datetime.now().isoformat()

    # Persist status to DB
    device_id = data.get("device_id")
    lock_state = data.get("lock_state")
    door_state = data.get("door_state")

    if device_id:
        register_device(device_id, device_id)
        if lock_state or door_state:
            log_state_change(device_id, lock_state, door_state)


def on_mqtt_event(event_data):
    """Handle MQTT event messages"""
    event_type = event_data.get("event_type")
    description = event_data.get("description", "")
    device_id = event_data.get("device_id")
    
    if event_type:
        log_event(event_type, description, device_id)


def log_event(event_type, description, device_id=None):
    """Log an event to the database and buffer"""
    timestamp = datetime.now().isoformat()
    event = Event(
        timestamp=timestamp,
        event_type=event_type,
        description=description,
        device_id=device_id,
    )

    events_buffer.append(event.to_dict())
    if len(events_buffer) > MAX_EVENTS:
        events_buffer.pop(0)

    try:
        if device_id:
            register_device(device_id, device_id)
        db_log_event(event_type, description, device_id)
    except Exception as e:
        print(f"[DB] Error saving event: {e}")


def init_mqtt():
    """Initialize MQTT client"""
    global mqtt_client, mqtt_connected
    
    mqtt_client = BoltLockMQTTClient(
        MQTT_BROKER_HOST,
        MQTT_PORT,
        MQTT_USERNAME,
        MQTT_PASSWORD,
    )
    
    def on_connect():
        global mqtt_connected
        mqtt_connected = True
        print(f"[MQTT] Connected to broker at {MQTT_BROKER_HOST}:{MQTT_PORT}")

    def on_disconnect():
        global mqtt_connected
        mqtt_connected = False
        print("[MQTT] Disconnected from broker")

    mqtt_client.set_callback("on_connect", on_connect)
    mqtt_client.set_callback("on_disconnect", on_disconnect)
    mqtt_client.set_callback("on_status", on_mqtt_status)
    mqtt_client.set_callback("on_event", on_mqtt_event)

    if mqtt_client.connect():
        print("[MQTT] MQTT client initialized successfully")
    else:
        print("[MQTT] Failed to initialize MQTT client")
        print("[MQTT] Check broker configuration.")


if __name__ == "__main__":
    print("[SERVER] Initializing BoltLock Cloud Backend (MQTT-only)...")
    init_db()
    init_mqtt()
    print("[MQTT] Server running. Listening for messages on topics...")
    
    # Keep the application running
    try:
        while True:
            pass
    except KeyboardInterrupt:
        print("\n[SERVER] Shutting down...")
        if mqtt_client:
            mqtt_client.disconnect()
        print("[SERVER] Goodbye!")


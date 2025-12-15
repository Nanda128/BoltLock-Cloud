"""
BoltLock Cloud Backend
MQTT-only smart door lock management system
"""

from __future__ import annotations

import time
from datetime import datetime

from config.settings import (
    MQTT_BROKER_HOST,
    MQTT_PORT,
    MQTT_USERNAME,
    MQTT_PASSWORD,
)
from boltlock.models import Event
from boltlock.mqtt import BoltLockMQTTClient
from boltlock.database import (
    init_db,
    log_event as db_log_event,
    register_device,
    log_state_change,
)

# Device state (in-memory snapshot for /api/status if you later add an API)
device_state = {
    "lock_state": "LOCKED",
    "door_state": "CLOSED",
    "wifi_connected": False,
    "last_update": None,
    "device_id": None,
}

events_buffer: list[dict] = []
MAX_EVENTS = 100

mqtt_client: BoltLockMQTTClient | None = None
mqtt_connected = False


def on_mqtt_status(data: dict) -> None:
    """Handle MQTT status/state messages"""
    global device_state

    # The MQTT client now normalises a lot of this, but keep extra guards anyway.
    if "status" in data and "wifi_connected" not in data:
        device_state["wifi_connected"] = (str(data.get("status")).lower() == "online")

    if "wifi_connected" in data:
        device_state["wifi_connected"] = bool(data.get("wifi_connected"))

    # Accept either lock_state or state
    if "lock_state" in data:
        device_state["lock_state"] = data["lock_state"]
    elif "state" in data:
        state = str(data["state"]).strip().lower()
        if state in {"locked", "unlocked", "unlocking"}:
            device_state["lock_state"] = state.upper()

    if "door_state" in data:
        device_state["door_state"] = data["door_state"]

    if "device_id" in data:
        device_state["device_id"] = data["device_id"]

    device_state["last_update"] = datetime.now().isoformat()

    # Persist status to DB (do not require device_id)
    device_id = data.get("device_id")
    lock_state = device_state.get("lock_state")
    door_state = device_state.get("door_state")

    if device_id:
        # Safe to register device if we have an id
        register_device(device_id, str(device_id))

    # Log state changes even if device_id is None so you still see history
    if lock_state or door_state:
        try:
            log_state_change(device_id, lock_state, door_state)
        except Exception as e:
            print(f"[DB] Error logging state change: {e}")


def on_mqtt_event(event_data: dict) -> None:
    """Handle MQTT event messages"""
    event_type = event_data.get("event_type")
    description = event_data.get("description", "")
    device_id = event_data.get("device_id")

    if event_type:
        log_event(str(event_type), str(description), device_id)


def log_event(event_type: str, description: str, device_id: str | None = None) -> None:
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
            register_device(device_id, str(device_id))
        db_log_event(event_type, description, device_id)
    except Exception as e:
        print(f"[DB] Error saving event: {e}")


def init_mqtt() -> None:
    """Initialise MQTT client"""
    global mqtt_client, mqtt_connected

    mqtt_client = BoltLockMQTTClient(
        MQTT_BROKER_HOST,
        MQTT_PORT,
        MQTT_USERNAME,
        MQTT_PASSWORD,
    )

    def on_connect() -> None:
        global mqtt_connected
        mqtt_connected = True
        print(f"[MQTT] Connected to broker at {MQTT_BROKER_HOST}:{MQTT_PORT}")

    def on_disconnect() -> None:
        global mqtt_connected
        mqtt_connected = False
        print("[MQTT] Disconnected from broker")

    mqtt_client.set_callback("on_connect", on_connect)
    mqtt_client.set_callback("on_disconnect", on_disconnect)
    mqtt_client.set_callback("on_status", on_mqtt_status)
    mqtt_client.set_callback("on_event", on_mqtt_event)

    if mqtt_client.connect():
        print("[MQTT] MQTT client initialised successfully")
    else:
        print("[MQTT] Failed to initialise MQTT client")
        print("[MQTT] Check broker configuration.")


if __name__ == "__main__":
    print("[SERVER] Initialising BoltLock Cloud Backend (MQTT-only).")
    init_db()
    init_mqtt()
    print("[MQTT] Server running. Listening for messages.")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[SERVER] Shutting down.")
        if mqtt_client:
            mqtt_client.disconnect()
        print("[SERVER] Goodbye.")

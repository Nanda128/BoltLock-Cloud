import hashlib
import json
import secrets
from datetime import datetime
from functools import wraps

import paho.mqtt.client as mqtt
from flask import Flask, jsonify, request, render_template, send_from_directory
from flask_cors import CORS

from config import (
    MQTT_BROKER_HOST,
    MQTT_PORT,
    MQTT_USERNAME,
    MQTT_PASSWORD,
    MQTT_TOPIC_STATUS,
    MQTT_TOPIC_COMMAND,
    MQTT_TOPIC_EVENTS,
    SERVER_HOST,
    SERVER_PORT,
    SQLALCHEMY_DATABASE_URI,
)
from models import db, Event, User, Device, StateHistory

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = SQLALCHEMY_DATABASE_URI
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# SQLite tends to lock under concurrent writes; these options reduce pain.
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "connect_args": {"check_same_thread": False},
    "pool_pre_ping": True,
}

db.init_app(app)
CORS(app)

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


def init_db():
    with app.app_context():
        db.create_all()
        print("[DB] Database initialised")


def require_auth(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        api_key = request.headers.get("X-API-Key")
        if not api_key:
            return jsonify({"error": "Missing API key"}), 401

        user = User.query.filter_by(api_key=api_key).first()
        if not user:
            return jsonify({"error": "Invalid API key"}), 401

        return f(*args, **kwargs)

    return decorated_function


def on_connect(client, userdata, flags, rc):
    global mqtt_connected
    if rc == 0:
        mqtt_connected = True
        print(f"[MQTT] Connected to broker at {MQTT_BROKER_HOST}:{MQTT_PORT}")
        client.subscribe(MQTT_TOPIC_STATUS)
        client.subscribe(MQTT_TOPIC_EVENTS)
        print(f"[MQTT] Subscribed to {MQTT_TOPIC_STATUS} and {MQTT_TOPIC_EVENTS}")
    else:
        mqtt_connected = False
        print(f"[MQTT] Connection failed with code {rc}")


def on_disconnect(client, userdata, rc):
    global mqtt_connected
    mqtt_connected = False
    print(f"[MQTT] Disconnected from broker (code: {rc})")


def _register_or_touch_device(device_id: str):
    ts = datetime.now().isoformat()
    device = Device.query.filter_by(id=device_id).first()
    if device:
        device.last_seen = ts
    else:
        device = Device(id=device_id, name=device_id, registered_at=ts, last_seen=ts)
        db.session.add(device)


def _log_state_history(device_id: str | None, lock_state: str | None, door_state: str | None):
    if not device_id:
        return
    ts = datetime.now().isoformat()
    db.session.add(
        StateHistory(
            timestamp=ts,
            device_id=device_id,
            lock_state=lock_state,
            door_state=door_state,
        )
    )


def on_message(client, userdata, msg):
    try:
        payload = msg.payload.decode("utf-8", errors="replace")
        topic = msg.topic

        print(f"[MQTT] Received on {topic}: {payload}")

        if topic == MQTT_TOPIC_STATUS:
            try:
                data = json.loads(payload)

                # Update in-memory state
                if "status" in data:
                    device_state["wifi_connected"] = (data.get("status") == "online")

                for k in ["lock_state", "door_state", "device_id", "wifi_connected"]:
                    if k in data:
                        device_state[k] = data[k]

                device_state["last_update"] = datetime.now().isoformat()

                # Persist status to DB
                with app.app_context():
                    device_id = data.get("device_id")
                    lock_state = data.get("lock_state")
                    door_state = data.get("door_state")

                    if device_id:
                        _register_or_touch_device(device_id)
                        _log_state_history(device_id, lock_state, door_state)
                        db.session.commit()

            except json.JSONDecodeError:
                print("[MQTT] Invalid JSON in status message")

        elif topic == MQTT_TOPIC_EVENTS:
            event_type, description, device_id = _parse_event_message(payload)
            if event_type:
                log_event(event_type, description, device_id)

    except Exception as e:
        print(f"[MQTT] Error processing message: {e}")


def log_event(event_type, description, device_id=None):
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
        with app.app_context():
            if device_id:
                _register_or_touch_device(device_id)
            db.session.add(event)
            db.session.commit()
    except Exception as e:
        print(f"[DB] Error saving event: {e}")
        with app.app_context():
            db.session.rollback()


def init_mqtt():
    global mqtt_client
    mqtt_client = mqtt.Client()
    mqtt_client.on_connect = on_connect
    mqtt_client.on_disconnect = on_disconnect
    mqtt_client.on_message = on_message

    if MQTT_USERNAME and MQTT_PASSWORD:
        mqtt_client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)

    try:
        mqtt_client.connect(MQTT_BROKER_HOST, MQTT_PORT, 60)
        mqtt_client.loop_start()
        print(f"[MQTT] Connecting to {MQTT_BROKER_HOST}:{MQTT_PORT}...")
    except Exception as e:
        print(f"[MQTT] Failed to connect: {e}")
        print("[MQTT] Server will run without MQTT. Check broker configuration.")


@app.route("/")
def index():
    return jsonify(
        {
            "service": "BoltLock Cloud Backend",
            "version": "1.0.0",
            "mqtt_connected": mqtt_connected,
            "device_connected": device_state["last_update"] is not None,
        }
    )


@app.route("/api/status", methods=["GET"])
@require_auth
def get_status():
    return jsonify(
        {"success": True, "data": device_state, "mqtt_connected": mqtt_connected}
    )


@app.route("/api/lock", methods=["POST"])
@require_auth
def lock_door():
    if not mqtt_connected:
        return jsonify({"success": False, "error": "MQTT not connected"}), 503

    command = {"action": "lock"}
    mqtt_client.publish(MQTT_TOPIC_COMMAND, json.dumps(command))
    log_event("REMOTE_LOCK", "Lock command sent via API")

    return jsonify({"success": True, "message": "Lock command sent"})


@app.route("/api/unlock", methods=["POST"])
@require_auth
def unlock_door():
    if not mqtt_connected:
        return jsonify({"success": False, "error": "MQTT not connected"}), 503

    command = {"action": "unlock"}
    mqtt_client.publish(MQTT_TOPIC_COMMAND, json.dumps(command))
    log_event("REMOTE_UNLOCK", "Unlock command sent via API")

    return jsonify({"success": True, "message": "Unlock command sent"})


@app.route("/api/events", methods=["GET"])
@require_auth
def get_events():
    limit = request.args.get("limit", 50, type=int)
    events = Event.query.order_by(Event.id.desc()).limit(limit).all()
    return jsonify({"success": True, "data": [e.to_dict() for e in events]})


@app.route("/api/auth/register", methods=["POST"])
def register():
    data = request.get_json() or {}
    username = data.get("username")
    password = data.get("password")

    if not username or not password:
        return jsonify({"success": False, "error": "Username and password required"}), 400

    password_hash = hashlib.sha256(password.encode()).hexdigest()
    api_key = secrets.token_urlsafe(32)

    try:
        user = User(
            username=username,
            password_hash=password_hash,
            api_key=api_key,
            created_at=datetime.now().isoformat(),
        )
        db.session.add(user)
        db.session.commit()
        return jsonify({"success": True, "api_key": api_key})
    except Exception as e:
        db.session.rollback()
        if "username" in str(e).lower():
            return jsonify({"success": False, "error": "Username already exists"}), 409
        return jsonify({"success": False, "error": str(e)}), 400


@app.route("/api/auth/login", methods=["POST"])
def login():
    data = request.get_json() or {}
    username = data.get("username")
    password = data.get("password")

    if not username or not password:
        return jsonify({"success": False, "error": "Username and password required"}), 400

    password_hash = hashlib.sha256(password.encode()).hexdigest()
    user = User.query.filter_by(username=username, password_hash=password_hash).first()

    if user:
        return jsonify({"success": True, "api_key": user.api_key})
    return jsonify({"success": False, "error": "Invalid credentials"}), 401


@app.route("/dashboard")
def dashboard():
    """Main dashboard page"""
    return render_template("dashboard.html")


@app.route("/api/dashboard/status")
def api_dashboard_status():
    """Get current system status for dashboard (no auth required for basic view)"""
    return jsonify({
        "success": True,
        "device_state": device_state,
        "mqtt_connected": mqtt_connected,
        "events_buffered": len(events_buffer),
    })


@app.route("/api/dashboard/events", methods=["GET"])
def api_dashboard_events():
    """Get recent events for dashboard display"""
    limit = request.args.get("limit", 20, type=int)
    events = Event.query.order_by(Event.id.desc()).limit(limit).all()
    return jsonify({
        "success": True,
        "data": [e.to_dict() for e in reversed(events)]
    })


@app.route("/api/dashboard/state-history", methods=["GET"])
def api_dashboard_state_history():
    """Get lock state history for dashboard"""
    device_id = request.args.get("device_id")
    limit = request.args.get("limit", 50, type=int)
    
    query = StateHistory.query.order_by(StateHistory.id.desc()).limit(limit)
    if device_id:
        query = query.filter_by(device_id=device_id)
    
    states = query.all()
    return jsonify({
        "success": True,
        "data": [s.to_dict() for s in reversed(states)]
    })


@app.route("/api/dashboard/devices", methods=["GET"])
def api_dashboard_devices():
    """Get registered devices"""
    devices = Device.query.all()
    return jsonify({
        "success": True,
        "data": [d.to_dict() for d in devices]
    })


if __name__ == "__main__":
    print("[SERVER] Initialising BoltLock Cloud Backend...")
    init_db()
    init_mqtt()
    print(f"[SERVER] Starting Flask server on {SERVER_HOST}:{SERVER_PORT}...")
    app.run(host=SERVER_HOST, port=SERVER_PORT, debug=False)

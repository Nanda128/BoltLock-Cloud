import hashlib
import json
import secrets
import sqlite3
from datetime import datetime
from functools import wraps

import paho.mqtt.client as mqtt
from flask import Flask, jsonify, request
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# Configuration
MQTT_BROKER = "localhost"  # Change to your MQTT broker
MQTT_PORT = 1883
MQTT_TOPIC_STATUS = "boltlock/status"
MQTT_TOPIC_COMMAND = "boltlock/command"
MQTT_TOPIC_EVENTS = "boltlock/events"

# Device state
device_state = {
    "lock_state": "LOCKED",
    "door_state": "CLOSED",
    "wifi_connected": False,
    "last_update": None,
    "device_id": None,
}

events_buffer = []
MAX_EVENTS = 100

# MQTT Client
mqtt_client = None
mqtt_connected = False


# Database initialization
def init_db():
    conn = sqlite3.connect("boltlock.db")
    c = conn.cursor()

    # Events table
    c.execute("""CREATE TABLE IF NOT EXISTS events
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  timestamp TEXT,
                  event_type TEXT,
                  description TEXT,
                  device_id TEXT)""")

    # Users table for authentication
    c.execute("""CREATE TABLE IF NOT EXISTS users
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  username TEXT UNIQUE,
                  password_hash TEXT,
                  api_key TEXT UNIQUE)""")

    # Device table
    c.execute("""CREATE TABLE IF NOT EXISTS devices
                 (id TEXT PRIMARY KEY,
                  name TEXT,
                  registered_at TEXT,
                  last_seen TEXT)""")

    conn.commit()
    conn.close()


# Authentication decorator
def require_auth(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        api_key = request.headers.get("X-API-Key")
        if not api_key:
            return jsonify({"error": "Missing API key"}), 401

        conn = sqlite3.connect("boltlock.db")
        c = conn.cursor()
        c.execute("SELECT id FROM users WHERE api_key = ?", (api_key,))
        user = c.fetchone()
        conn.close()

        if not user:
            return jsonify({"error": "Invalid API key"}), 401

        return f(*args, **kwargs)

    return decorated_function


# MQTT Callbacks
def on_connect(client, userdata, flags, rc):
    global mqtt_connected
    if rc == 0:
        print(f"[MQTT] Connected to broker at {MQTT_BROKER}:{MQTT_PORT}")
        mqtt_connected = True
        # Subscribe to device topics
        client.subscribe(MQTT_TOPIC_STATUS)
        client.subscribe(MQTT_TOPIC_EVENTS)
        print(f"[MQTT] Subscribed to {MQTT_TOPIC_STATUS} and {MQTT_TOPIC_EVENTS}")
    else:
        print(f"[MQTT] Connection failed with code {rc}")
        mqtt_connected = False


def on_disconnect(client, userdata, rc):
    global mqtt_connected
    mqtt_connected = False
    print(f"[MQTT] Disconnected from broker (code: {rc})")


def on_message(client, userdata, msg):
    try:
        payload = msg.payload.decode("utf-8")
        topic = msg.topic

        print(f"[MQTT] Received on {topic}: {payload}")

        if topic == MQTT_TOPIC_STATUS:
            # Update device state
            data = json.loads(payload)
            device_state.update(
                {
                    "lock_state": data.get("lock_state", device_state["lock_state"]),
                    "door_state": data.get("door_state", device_state["door_state"]),
                    "wifi_connected": data.get("wifi_connected", True),
                    "device_id": data.get("device_id"),
                    "last_update": datetime.now().isoformat(),
                }
            )

        elif topic == MQTT_TOPIC_EVENTS:
            # Log event
            event = json.loads(payload)
            log_event(
                event.get("event_type", "UNKNOWN"),
                event.get("description", ""),
                event.get("device_id"),
            )

    except Exception as e:
        print(f"[MQTT] Error processing message: {e}")


def log_event(event_type, description, device_id=None):
    timestamp = datetime.now().isoformat()
    event = {
        "timestamp": timestamp,
        "event_type": event_type,
        "description": description,
        "device_id": device_id,
    }

    # Add to buffer
    events_buffer.append(event)
    if len(events_buffer) > MAX_EVENTS:
        events_buffer.pop(0)

    # Save to database
    try:
        conn = sqlite3.connect("boltlock.db")
        c = conn.cursor()
        c.execute(
            "INSERT INTO events (timestamp, event_type, description, device_id) VALUES (?, ?, ?, ?)",
            (timestamp, event_type, description, device_id),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[DB] Error saving event: {e}")


def init_mqtt():
    global mqtt_client
    mqtt_client = mqtt.Client()
    mqtt_client.on_connect = on_connect
    mqtt_client.on_disconnect = on_disconnect
    mqtt_client.on_message = on_message

    try:
        mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
        mqtt_client.loop_start()
        print(f"[MQTT] Connecting to {MQTT_BROKER}:{MQTT_PORT}...")
    except Exception as e:
        print(f"[MQTT] Failed to connect: {e}")
        print("[MQTT] Server will run without MQTT. Check broker configuration.")


# REST API Routes


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

    conn = sqlite3.connect("boltlock.db")
    c = conn.cursor()
    c.execute(
        "SELECT timestamp, event_type, description, device_id FROM events ORDER BY id DESC LIMIT ?",
        (limit,),
    )
    events = [
        {
            "timestamp": row[0],
            "event_type": row[1],
            "description": row[2],
            "device_id": row[3],
        }
        for row in c.fetchall()
    ]
    conn.close()

    return jsonify({"success": True, "data": events})


@app.route("/api/auth/register", methods=["POST"])
def register():
    data = request.get_json()
    username = data.get("username")
    password = data.get("password")

    if not username or not password:
        return jsonify(
            {"success": False, "error": "Username and password required"}
        ), 400

    password_hash = hashlib.sha256(password.encode()).hexdigest()
    api_key = secrets.token_urlsafe(32)

    try:
        conn = sqlite3.connect("boltlock.db")
        c = conn.cursor()
        c.execute(
            "INSERT INTO users (username, password_hash, api_key) VALUES (?, ?, ?)",
            (username, password_hash, api_key),
        )
        conn.commit()
        conn.close()

        return jsonify({"success": True, "api_key": api_key})
    except sqlite3.IntegrityError:
        return jsonify({"success": False, "error": "Username already exists"}), 409


@app.route("/api/auth/login", methods=["POST"])
def login():
    data = request.get_json()
    username = data.get("username")
    password = data.get("password")

    if not username or not password:
        return jsonify(
            {"success": False, "error": "Username and password required"}
        ), 400

    password_hash = hashlib.sha256(password.encode()).hexdigest()

    conn = sqlite3.connect("boltlock.db")
    c = conn.cursor()
    c.execute(
        "SELECT api_key FROM users WHERE username = ? AND password_hash = ?",
        (username, password_hash),
    )
    result = c.fetchone()
    conn.close()

    if result:
        return jsonify({"success": True, "api_key": result[0]})
    else:
        return jsonify({"success": False, "error": "Invalid credentials"}), 401


if __name__ == "__main__":
    print("[SERVER] Initializing BoltLock Cloud Backend...")
    init_db()
    print("[DB] Database initialized")
    init_mqtt()
    print("[SERVER] Starting Flask server on port 5000...")
    app.run(host="0.0.0.0", port=5000, debug=False)

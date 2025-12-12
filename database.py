"""
Database Module for BoltLock
Handles all database operations
"""

import sqlite3
from datetime import datetime

from config import DATABASE_PATH


def init_db():
    """Initialize the database with required tables"""
    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()

    # Events table
    c.execute("""CREATE TABLE IF NOT EXISTS events
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  timestamp TEXT NOT NULL,
                  event_type TEXT NOT NULL,
                  description TEXT,
                  device_id TEXT)""")

    # Users table for authentication
    c.execute("""CREATE TABLE IF NOT EXISTS users
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  username TEXT UNIQUE NOT NULL,
                  password_hash TEXT NOT NULL,
                  api_key TEXT UNIQUE NOT NULL,
                  created_at TEXT NOT NULL)""")

    # Devices table
    c.execute("""CREATE TABLE IF NOT EXISTS devices
                 (id TEXT PRIMARY KEY,
                  name TEXT,
                  registered_at TEXT NOT NULL,
                  last_seen TEXT)""")

    # Device state history
    c.execute("""CREATE TABLE IF NOT EXISTS state_history
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  timestamp TEXT NOT NULL,
                  device_id TEXT,
                  lock_state TEXT,
                  door_state TEXT)""")

    conn.commit()
    conn.close()
    print("[DB] Database initialized")


def log_event(event_type, description, device_id=None):
    """Log an event to the database"""
    timestamp = datetime.now().isoformat()

    try:
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute(
            "INSERT INTO events (timestamp, event_type, description, device_id) VALUES (?, ?, ?, ?)",
            (timestamp, event_type, description, device_id),
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"[DB] Error saving event: {e}")
        return False


def get_events(limit=50, device_id=None):
    """Retrieve recent events from the database"""
    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()

    if device_id:
        c.execute(
            "SELECT timestamp, event_type, description, device_id FROM events WHERE device_id = ? ORDER BY id DESC LIMIT ?",
            (device_id, limit),
        )
    else:
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

    return events


def create_user(username, password_hash, api_key):
    """Create a new user"""
    timestamp = datetime.now().isoformat()

    try:
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute(
            "INSERT INTO users (username, password_hash, api_key, created_at) VALUES (?, ?, ?, ?)",
            (username, password_hash, api_key, timestamp),
        )
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        return False


def get_user_by_api_key(api_key):
    """Get user by API key"""
    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()
    c.execute("SELECT id, username FROM users WHERE api_key = ?", (api_key,))
    result = c.fetchone()
    conn.close()

    if result:
        return {"id": result[0], "username": result[1]}
    return None


def get_user_by_credentials(username, password_hash):
    """Get user by username and password"""
    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()
    c.execute(
        "SELECT id, api_key FROM users WHERE username = ? AND password_hash = ?",
        (username, password_hash),
    )
    result = c.fetchone()
    conn.close()

    if result:
        return {"id": result[0], "api_key": result[1]}
    return None


def register_device(device_id, name):
    """Register a new device"""
    timestamp = datetime.now().isoformat()

    try:
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute(
            "INSERT OR REPLACE INTO devices (id, name, registered_at, last_seen) VALUES (?, ?, ?, ?)",
            (device_id, name, timestamp, timestamp),
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"[DB] Error registering device: {e}")
        return False


def update_device_last_seen(device_id):
    """Update device last seen timestamp"""
    timestamp = datetime.now().isoformat()

    try:
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute(
            "UPDATE devices SET last_seen = ? WHERE id = ?", (timestamp, device_id)
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"[DB] Error updating device: {e}")
        return False


def log_state_change(device_id, lock_state, door_state):
    """Log a state change to history"""
    timestamp = datetime.now().isoformat()

    try:
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute(
            "INSERT INTO state_history (timestamp, device_id, lock_state, door_state) VALUES (?, ?, ?, ?)",
            (timestamp, device_id, lock_state, door_state),
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"[DB] Error logging state change: {e}")
        return False

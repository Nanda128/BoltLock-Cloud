# BoltLock Cloud Backend Configuration

from __future__ import annotations

import os
from pathlib import Path

# -----------------------------
# MQTT Broker Configuration
# -----------------------------
# Paho expects a hostname/IP here (NO mqtt:// prefix)
MQTT_BROKER_HOST = os.environ.get("BOLTLOCK_MQTT_HOST", "alderaan.software-engineering.ie")
MQTT_PORT = int(os.environ.get("BOLTLOCK_MQTT_PORT", "1883"))
MQTT_USERNAME = os.environ.get("BOLTLOCK_MQTT_USERNAME", "")
MQTT_PASSWORD = os.environ.get("BOLTLOCK_MQTT_PASSWORD", "")

# Use team-specific topics if needed
MQTT_TOPIC_STATUS = os.environ.get("BOLTLOCK_TOPIC_STATUS", "BoltLock/status")
MQTT_TOPIC_COMMAND = os.environ.get("BOLTLOCK_TOPIC_COMMAND", "BoltLock/command")
MQTT_TOPIC_EVENTS = os.environ.get("BOLTLOCK_TOPIC_EVENTS", "BoltLock/events")

# Database
# Store under the user's home directory
DB_DIR = Path(os.environ.get("BOLTLOCK_DB_DIR", Path.home() / ".local" / "share" / "boltlock"))
DB_DIR.mkdir(parents=True, exist_ok=True)

DATABASE_PATH = DB_DIR / "boltlock.db"
SQLALCHEMY_DATABASE_URI = f"sqlite:///{DATABASE_PATH}"


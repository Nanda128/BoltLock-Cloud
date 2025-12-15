# BoltLock Cloud Backend Configuration

# MQTT Broker Configuration
MQTT_BROKER = "mqtt://alderaan.software-engineering.ie"  # Change to your MQTT broker IP/hostname
MQTT_PORT = 1883  # Standard MQTT port (non-sudo accessible)
MQTT_USERNAME = None  # Optional: Set if your broker requires auth
MQTT_PASSWORD = None  # Optional: Set if your broker requires auth

# MQTT Topics (must match ESP32 firmware)
MQTT_TOPIC_STATUS = "BoltLock/status"
MQTT_TOPIC_COMMAND = "BoltLock/command"
MQTT_TOPIC_EVENTS = "BoltLock/events"

# Server Configuration
SERVER_HOST = "0.0.0.0"  # Bind to all interfaces
SERVER_PORT = 5000  # Non-sudo port

# Database
DATABASE_PATH = "boltlock.db"

# Security
SECRET_KEY = "change-this-to-a-random-secret-key"  # Change this!

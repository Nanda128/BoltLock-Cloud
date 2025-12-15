-- BoltLock Cloud Backend Database Schema
-- Compatible with SQLite and PostgreSQL

-- Devices table for registered devices
CREATE TABLE IF NOT EXISTS devices (
    id VARCHAR(255) PRIMARY KEY,
    name VARCHAR(255),
    registered_at VARCHAR(255) NOT NULL,
    last_seen VARCHAR(255)
);

-- Events table for lock/door events
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp VARCHAR(255) NOT NULL,
    event_type VARCHAR(255) NOT NULL,
    description VARCHAR(255),
    device_id VARCHAR(255)
);

-- State history table for tracking lock/door state changes
CREATE TABLE IF NOT EXISTS state_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp VARCHAR(255) NOT NULL,
    device_id VARCHAR(255),
    lock_state VARCHAR(255),
    door_state VARCHAR(255)
);

-- Create indices for better query performance
CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp);
CREATE INDEX IF NOT EXISTS idx_events_device_id ON events(device_id);
CREATE INDEX IF NOT EXISTS idx_state_history_timestamp ON state_history(timestamp);
CREATE INDEX IF NOT EXISTS idx_state_history_device_id ON state_history(device_id);
CREATE INDEX IF NOT EXISTS idx_devices_registered_at ON devices(registered_at);

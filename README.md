# BoltLock Cloud Backend (MQTT + Data Aggregation)

This repository is the **cloud back-end** for the BoltLock smart lock system. It runs on the **ISE Debian cloud server** (`alderaan.software-engineering.ie`) and uses the provided **Mosquitto MQTT broker** to aggregate device telemetry and events into a local SQLite database and to accept commands via an MQTT topic and publish them back to the ESP32. This is the cloud deliverable required by the CS4447 project spec (cloud back-end on alderaan, MQTT broker provided, data aggregation, command acceptance).

---

## Spec compliance checklist (cloud-side)

| Spec requirement | How BoltLock satisfies it | Where to look |
|---|---|---|
| Cloud back-end runs on ISE Debian cloud server | Runs as a Python service on `alderaan.software-engineering.ie` | `run.py`, `config/settings.py` |
| MQTT broker provided; publish team topics | Uses Mosquitto broker at `alderaan...` and team topics under `BoltLock/*` | `config/settings.py` |
| Accept commands by subscribing to a topic | Cloud publishes commands to `BoltLock/command` for the device to subscribe to | `boltlock/mqtt.py` |
| Data aggregation | Persists events, state history, and devices into SQLite | `boltlock/models.py`, `boltlock/database.py` |

---

## Architecture

ESP32 publishes status telemetry and events to MQTT topics. This cloud backend subscribes, normalises payloads, and writes them into SQLite for auditing and demo proof. For control, the cloud backend publishes a JSON command message to `BoltLock/command`, which the ESP32 subscribes to and executes.

---

## MQTT topics

Default topics (override via environment variables below):
- Status (device → cloud): `BoltLock/status`
- Events (device → cloud): `BoltLock/events`
- Commands (cloud → device): `BoltLock/command`

Where this is defined: `config/settings.py`.

---

## Quick start (ISE cloud server)

SSH into the ISE Debian cloud server:
```bash
ssh <username>@alderaan.software-engineering.ie
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python run.py
```
In a second terminal, monitor database writes in real time:
```bash
python watch_db.py --follow
```
This prints new events and state changes as they are received, providing live proof of data aggregation.

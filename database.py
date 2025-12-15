"""
Database Module for BoltLock
Handles all database operations using SQLAlchemy ORM
"""

from datetime import datetime

from config import DATABASE_PATH
from models import db, Event, User, Device, StateHistory


def init_db():
    """Initialize the database with required tables"""
    # This will be called from app.py context
    db.create_all()
    print("[DB] Database initialized")


def log_event(event_type, description, device_id=None):
    """Log an event to the database"""
    timestamp = datetime.now().isoformat()

    try:
        event = Event(
            timestamp=timestamp,
            event_type=event_type,
            description=description,
            device_id=device_id,
        )
        db.session.add(event)
        db.session.commit()
        return True
    except Exception as e:
        print(f"[DB] Error saving event: {e}")
        db.session.rollback()
        return False


def get_events(limit=50, device_id=None):
    """Retrieve recent events from the database"""
    query = Event.query.order_by(Event.id.desc())
    
    if device_id:
        query = query.filter_by(device_id=device_id)
    
    events = query.limit(limit).all()
    
    return [event.to_dict() for event in events]


def create_user(username, password_hash, api_key):
    """Create a new user"""
    timestamp = datetime.now().isoformat()

    try:
        user = User(
            username=username,
            password_hash=password_hash,
            api_key=api_key,
            created_at=timestamp,
        )
        db.session.add(user)
        db.session.commit()
        return True
    except Exception as e:
        print(f"[DB] Error creating user: {e}")
        db.session.rollback()
        return False


def get_user_by_api_key(api_key):
    """Get user by API key"""
    user = User.query.filter_by(api_key=api_key).first()

    if user:
        return {"id": user.id, "username": user.username}
    return None


def get_user_by_credentials(username, password_hash):
    """Get user by username and password"""
    user = User.query.filter_by(username=username, password_hash=password_hash).first()

    if user:
        return {"id": user.id, "api_key": user.api_key}
    return None


def register_device(device_id, name):
    """Register a new device"""
    timestamp = datetime.now().isoformat()

    try:
        device = Device.query.filter_by(id=device_id).first()
        if device:
            device.name = name
            device.last_seen = timestamp
        else:
            device = Device(
                id=device_id,
                name=name,
                registered_at=timestamp,
                last_seen=timestamp,
            )
            db.session.add(device)
        db.session.commit()
        return True
    except Exception as e:
        print(f"[DB] Error registering device: {e}")
        db.session.rollback()
        return False


def update_device_last_seen(device_id):
    """Update device last seen timestamp"""
    timestamp = datetime.now().isoformat()

    try:
        device = Device.query.filter_by(id=device_id).first()
        if device:
            device.last_seen = timestamp
            db.session.commit()
            return True
        return False
    except Exception as e:
        print(f"[DB] Error updating device: {e}")
        db.session.rollback()
        return False


def log_state_change(device_id, lock_state, door_state):
    """Log a state change to history"""
    timestamp = datetime.now().isoformat()

    try:
        state = StateHistory(
            timestamp=timestamp,
            device_id=device_id,
            lock_state=lock_state,
            door_state=door_state,
        )
        db.session.add(state)
        db.session.commit()
        return True
    except Exception as e:
        print(f"[DB] Error logging state change: {e}")
        db.session.rollback()
        return False

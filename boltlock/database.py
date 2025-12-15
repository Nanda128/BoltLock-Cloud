"""
Database Module for BoltLock
Handles all database operations using SQLAlchemy ORM
"""

from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from config.settings import SQLALCHEMY_DATABASE_URI
from boltlock.models import Base, Event, Device, StateHistory

# Create engine and session
engine = create_engine(SQLALCHEMY_DATABASE_URI, connect_args={"check_same_thread": False})
Session = sessionmaker(bind=engine)


def init_db():
    """Initialize the database with required tables"""
    Base.metadata.create_all(engine)
    print("[DB] Database initialized")


def log_event(event_type, description, device_id=None):
    """Log an event to the database"""
    timestamp = datetime.now().isoformat()
    session = Session()

    try:
        event = Event(
            timestamp=timestamp,
            event_type=event_type,
            description=description,
            device_id=device_id,
        )
        session.add(event)
        session.commit()
        return True
    except Exception as e:
        print(f"[DB] Error saving event: {e}")
        session.rollback()
        return False
    finally:
        session.close()


def get_events(limit=50, device_id=None):
    """Retrieve recent events from the database"""
    session = Session()
    try:
        query = session.query(Event).order_by(Event.id.desc())
        
        if device_id:
            query = query.filter_by(device_id=device_id)
        
        events = query.limit(limit).all()
        return [event.to_dict() for event in events]
    finally:
        session.close()

def register_device(device_id, name):
    """Register a new device"""
    timestamp = datetime.now().isoformat()
    session = Session()

    try:
        device = session.query(Device).filter_by(id=device_id).first()
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
            session.add(device)
        session.commit()
        return True
    except Exception as e:
        print(f"[DB] Error registering device: {e}")
        session.rollback()
        return False
    finally:
        session.close()


def update_device_last_seen(device_id):
    """Update device last seen timestamp"""
    timestamp = datetime.now().isoformat()
    session = Session()

    try:
        device = session.query(Device).filter_by(id=device_id).first()
        if device:
            device.last_seen = timestamp
            session.commit()
            return True
        return False
    except Exception as e:
        print(f"[DB] Error updating device: {e}")
        session.rollback()
        return False
    finally:
        session.close()


def log_state_change(device_id, lock_state, door_state):
    """Log a state change to history"""
    timestamp = datetime.now().isoformat()
    session = Session()

    try:
        state = StateHistory(
            timestamp=timestamp,
            device_id=device_id,
            lock_state=lock_state,
            door_state=door_state,
        )
        session.add(state)
        session.commit()
        return True
    except Exception as e:
        print(f"[DB] Error logging state change: {e}")
        session.rollback()
        return False
    finally:
        session.close()

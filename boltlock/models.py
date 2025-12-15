"""
SQLAlchemy ORM Models for BoltLock
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, create_engine
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class Event(Base):
    """Event model for storing lock/door events"""
    __tablename__ = 'events'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(String, nullable=False)
    event_type = Column(String, nullable=False)
    description = Column(String)
    device_id = Column(String)
    
    def to_dict(self):
        return {
            'id': self.id,
            'timestamp': self.timestamp,
            'event_type': self.event_type,
            'description': self.description,
            'device_id': self.device_id,
        }


class Device(Base):
    """Device model for registered devices"""
    __tablename__ = 'devices'
    
    id = Column(String, primary_key=True)
    name = Column(String)
    registered_at = Column(String, nullable=False)
    last_seen = Column(String)
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'registered_at': self.registered_at,
            'last_seen': self.last_seen,
        }


class StateHistory(Base):
    """State history model for tracking lock/door state changes"""
    __tablename__ = 'state_history'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(String, nullable=False)
    device_id = Column(String)
    lock_state = Column(String)
    door_state = Column(String)
    
    def to_dict(self):
        return {
            'id': self.id,
            'timestamp': self.timestamp,
            'device_id': self.device_id,
            'lock_state': self.lock_state,
            'door_state': self.door_state,
        }

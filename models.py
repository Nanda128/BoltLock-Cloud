"""
SQLAlchemy ORM Models for BoltLock
"""

from datetime import datetime

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class Event(db.Model):
    """Event model for storing lock/door events"""
    __tablename__ = 'events'
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    timestamp = db.Column(db.String, nullable=False)
    event_type = db.Column(db.String, nullable=False)
    description = db.Column(db.String)
    device_id = db.Column(db.String)
    
    def to_dict(self):
        return {
            'id': self.id,
            'timestamp': self.timestamp,
            'event_type': self.event_type,
            'description': self.description,
            'device_id': self.device_id,
        }


class User(db.Model):
    """User model for authentication"""
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username = db.Column(db.String, unique=True, nullable=False)
    password_hash = db.Column(db.String, nullable=False)
    api_key = db.Column(db.String, unique=True, nullable=False)
    created_at = db.Column(db.String, nullable=False)
    
    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'api_key': self.api_key,
            'created_at': self.created_at,
        }


class Device(db.Model):
    """Device model for registered devices"""
    __tablename__ = 'devices'
    
    id = db.Column(db.String, primary_key=True)
    name = db.Column(db.String)
    registered_at = db.Column(db.String, nullable=False)
    last_seen = db.Column(db.String)
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'registered_at': self.registered_at,
            'last_seen': self.last_seen,
        }


class StateHistory(db.Model):
    """State history model for tracking lock/door state changes"""
    __tablename__ = 'state_history'
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    timestamp = db.Column(db.String, nullable=False)
    device_id = db.Column(db.String)
    lock_state = db.Column(db.String)
    door_state = db.Column(db.String)
    
    def to_dict(self):
        return {
            'id': self.id,
            'timestamp': self.timestamp,
            'device_id': self.device_id,
            'lock_state': self.lock_state,
            'door_state': self.door_state,
        }

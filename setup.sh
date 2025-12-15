#!/bin/bash

# BoltLock Cloud Backend - Quick Start Script
# This script sets up the backend without requiring sudo

echo "=========================================="
echo "BoltLock Cloud Backend - Quick Setup"
echo "=========================================="

# Check Python version
python_version=$(python3 --version 2>&1 | awk '{print $2}')
echo "Python version: $python_version"

# Create virtual environment
echo ""
echo "Creating virtual environment..."
python3 -m venv venv

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo ""
echo "Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Configure
echo ""
echo "Configuration:"
echo "- Default MQTT broker: localhost:1883"
echo "- Default web server port: 5000"
echo ""
echo "To change configuration, edit config.py"
echo ""

# Initialize database
echo "Initializing database..."
python3 << 'EOF'
from database import init_db
init_db()
print("Database initialized successfully!")
EOF

# Create systemd user service (optional)
echo ""
read -p "Do you want to create a systemd user service? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]
then
    echo "Creating systemd user service..."
    mkdir -p ~/.config/systemd/user/
    
    cat > ~/.config/systemd/user/boltlock.service << EOF
[Unit]
Description=BoltLock Cloud Backend
After=network.target

[Service]
Type=simple
WorkingDirectory=$(pwd)
ExecStart=$(pwd)/venv/bin/python app.py
Restart=always
RestartSec=10

[Install]
WantedBy=default.target
EOF

    systemctl --user daemon-reload
    systemctl --user enable boltlock.service
    
    echo ""
    echo "Systemd service created!"
    echo "Start with: systemctl --user start boltlock.service"
    echo "Check status: systemctl --user status boltlock.service"
fi

echo ""
echo "=========================================="
echo "Setup Complete!"
echo "=========================================="
echo ""
echo "To start the server manually:"
echo "  source venv/bin/activate"
echo "  python app.py"
echo ""
echo "To run in background with screen:"
echo "  screen -S boltlock"
echo "  source venv/bin/activate"
echo "  python app.py"
echo "  # Press Ctrl+A then D to detach"
echo ""
echo "To test the server:"
echo "  curl http://localhost:5000/"
echo ""
echo "Next steps:"
echo "1. Configure MQTT broker in config.py"
echo "2. Update ESP32 firmware with MQTT credentials"
echo ""

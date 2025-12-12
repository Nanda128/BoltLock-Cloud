@echo off
REM BoltLock Cloud Backend - Quick Start Script for Windows

echo ==========================================
echo BoltLock Cloud Backend - Quick Setup
echo ==========================================

REM Check Python version
python --version
if errorlevel 1 (
    echo Python is not installed or not in PATH
    exit /b 1
)

REM Create virtual environment
echo.
echo Creating virtual environment...
python -m venv venv

REM Activate virtual environment
echo Activating virtual environment...
call venv\Scripts\activate.bat

REM Install dependencies
echo.
echo Installing dependencies...
python -m pip install --upgrade pip
pip install -r requirements.txt

REM Configure
echo.
echo Configuration:
echo - Default MQTT broker: localhost:1883
echo - Default web server port: 5000
echo.
echo To change configuration, edit config.py
echo.

REM Initialize database
echo Initializing database...
python -c "from database import init_db; init_db(); print('Database initialized successfully!')"

echo.
echo ==========================================
echo Setup Complete!
echo ==========================================
echo.
echo To start the server:
echo   venv\Scripts\activate.bat
echo   python app.py
echo.
echo To test the server:
echo   curl http://localhost:5000/
echo.
echo Next steps:
echo 1. Configure MQTT broker in config.py
echo 2. Register a user via API
echo 3. Update ESP32 firmware with MQTT credentials
echo.
pause

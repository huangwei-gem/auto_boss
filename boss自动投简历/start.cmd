@echo off
title Boss Auto Apply - Resume Bot
cd /d "%~dp0"

:: Activate virtual environment
call .venv\Scripts\activate.bat

:: Launch GUI
echo Starting Boss Auto Apply Tool...
python main.py

:: Pause if error
if %errorlevel% neq 0 (
    echo.
    echo An error occurred. Press any key to exit.
    pause >nul
)

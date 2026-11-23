@echo off
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
    py -3 start.py
) else (
    python start.py
)
if errorlevel 1 (
    echo.
    echo MeetPoint did not start. Install Python 3.11 or newer and read README.md.
    pause
)

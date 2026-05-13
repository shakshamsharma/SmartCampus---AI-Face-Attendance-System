@echo off
title SmartCampus AI - Real Face Recognition Attendance
color 0A
cls

echo.
echo ============================================================
echo    SmartCampus AI - Real Face Recognition Attendance
echo ============================================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found! Install from https://python.org
    echo TICK "Add Python to PATH" during install
    pause
    exit /b 1
)
for /f "tokens=*" %%i in ('python --version 2^>^&1') do echo [OK] %%i
echo.

echo [1/4] Installing dependencies (1-2 min first time)...
pip install fastapi uvicorn "python-jose[cryptography]" passlib sqlalchemy python-multipart pillow reportlab openpyxl opencv-contrib-python --quiet --no-warn-script-location 2>nul
echo [OK] Dependencies installed
echo.

echo [2/4] Setting up database...
cd /d "%~dp0backend"
python -c "from seed import seed; seed()" 2>nul
echo [OK] Database ready
echo.

echo [3/4] Starting Backend on port 8001...
start "SmartCampus BACKEND - Keep Open" cmd /k "cd /d "%~dp0backend" && python -m uvicorn main:app --host 127.0.0.1 --port 8001 --reload"
timeout /t 6 /nobreak >nul
echo [OK] Backend started
echo.

echo [4/4] Starting Frontend on port 3000...
start "SmartCampus FRONTEND - Keep Open" cmd /k "cd /d "%~dp0frontend" && python -m http.server 3000"
timeout /t 3 /nobreak >nul
echo [OK] Frontend started
echo.

start "" "chrome.exe" "http://localhost:3000" 2>nul
if errorlevel 1 start "" "http://localhost:3000"

echo.
echo ============================================================
echo  Open in browser: http://localhost:3000
echo.
echo  LOGINS:
echo  Admin:    admin001   / password123
echo  Faculty:  faculty001 / password123
echo  Saksham:  2023CSE001 / password123
echo  Ashish:   2023CSE002 / password123
echo  Ashutosh: 2023CSE003 / password123
echo  Vishal:   2023CSE004 / password123
echo.
echo  CAMERA FIX FOR BRAVE BROWSER:
echo  1. Click lock icon in address bar
echo  2. Site Settings - set Camera to ALLOW
echo  3. Reload page
echo  OR open Chrome and go to http://localhost:3000
echo ============================================================
echo.
pause

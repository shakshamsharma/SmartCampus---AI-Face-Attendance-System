@echo off
echo ========================================
echo SmartCampus AI - Starting Server
echo ========================================
echo.

cd backend

echo [1/3] Checking Python installation...
python --version
if errorlevel 1 (
    echo ERROR: Python not found!
    echo Please install Python 3.11 or higher
    pause
    exit /b 1
)

echo.
echo [2/3] Checking dependencies...
python -c "import cv2, numpy, fastapi" 2>nul
if errorlevel 1 (
    echo Installing dependencies...
    pip install -r requirements.txt
)

echo.
echo [3/3] Starting server...
echo.
echo ========================================
echo Server will start at: http://localhost:8001
echo Frontend URL: http://localhost:8001/frontend/index.html
echo ========================================
echo.
echo Press Ctrl+C to stop the server
echo.

uvicorn main:app --reload --port 8001 --host 0.0.0.0

pause

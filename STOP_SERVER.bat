@echo off
echo ========================================
echo SmartCampus AI - Stopping Server
echo ========================================
echo.

echo Killing all Python processes running uvicorn...
taskkill /F /IM python.exe /FI "WINDOWTITLE eq *uvicorn*" 2>nul

echo.
echo Server stopped!
echo.
pause

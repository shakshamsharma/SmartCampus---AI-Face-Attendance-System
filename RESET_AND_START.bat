@echo off
REM ============================================================================
REM SmartCampus Production Reset - Windows Batch Script
REM ============================================================================
REM This script will:
REM 1. Reset the database to production state
REM 2. Clear all demo data
REM 3. Remove face recognition models
REM 4. Clean unknown face images
REM 5. Verify the clean state
REM ============================================================================

echo.
echo ============================================================================
echo SmartCampus Production Reset
echo ============================================================================
echo.
echo This will DELETE ALL demo data and reset to production state.
echo.
echo Press Ctrl+C to cancel, or
pause

echo.
echo [1/3] Navigating to backend directory...
cd backend

echo.
echo [2/3] Running production reset script...
python reset_to_production.py

echo.
echo [3/3] Returning to root directory...
cd ..

echo.
echo ============================================================================
echo Reset Complete!
echo ============================================================================
echo.
echo Next steps:
echo 1. Start the backend server: cd backend ^&^& uvicorn main:app --reload
echo 2. Open frontend in browser: frontend/index.html
echo 3. Login as admin: admin001 / admin123
echo 4. Change admin password immediately
echo 5. Add real students and faculty
echo.
echo ============================================================================
echo.
pause

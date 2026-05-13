#!/bin/bash
clear
echo ""
echo "============================================================"
echo "   SmartCampus AI - Real Face Recognition Attendance"
echo "   OpenCV LBPH | FastAPI | SQLite | React"
echo "============================================================"
echo ""

# Check Python
if ! command -v python3 &>/dev/null; then
  echo "ERROR: Python3 not found. Install from https://python.org"
  exit 1
fi
echo "[OK] $(python3 --version)"

# Install dependencies
echo ""
echo "[1/4] Installing dependencies..."
pip3 install fastapi uvicorn "python-jose[cryptography]" passlib sqlalchemy \
  python-multipart pillow reportlab openpyxl opencv-contrib-python -q
echo "[OK] Dependencies installed"

# Setup DB
echo ""
echo "[2/4] Setting up database..."
cd "$(dirname "$0")/backend"
python3 -c "from seed import seed; seed()"
echo "[OK] Database ready"

# Start backend
echo ""
echo "[3/4] Starting backend on port 8001..."
python3 -m uvicorn main:app --host 127.0.0.1 --port 8001 --reload &
BACKEND_PID=$!
sleep 4
echo "[OK] Backend running at http://127.0.0.1:8001"

# Start frontend
echo ""
echo "[4/4] Starting frontend on port 3000..."
cd "$(dirname "$0")/frontend"
python3 -m http.server 3000 &
FRONTEND_PID=$!
sleep 2
echo "[OK] Frontend running at http://localhost:3000"

echo ""
echo "============================================================"
echo "  Open Chrome: http://localhost:3000"
echo "  API Docs:    http://127.0.0.1:8001/docs"
echo ""
echo "  Admin:   admin001   / password123"
echo "  Faculty: faculty001 / password123"
echo "  Student: 2023CSE001 / password123"
echo "============================================================"
echo ""

# Open browser
if command -v open &>/dev/null; then
  open "http://localhost:3000"
elif command -v xdg-open &>/dev/null; then
  xdg-open "http://localhost:3000"
fi

echo "Press Ctrl+C to stop all servers"
wait

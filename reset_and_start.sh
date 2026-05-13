#!/bin/bash

# ============================================================================
# SmartCampus Production Reset - Linux/Mac Shell Script
# ============================================================================
# This script will:
# 1. Reset the database to production state
# 2. Clear all demo data
# 3. Remove face recognition models
# 4. Clean unknown face images
# 5. Verify the clean state
# ============================================================================

echo ""
echo "============================================================================"
echo "SmartCampus Production Reset"
echo "============================================================================"
echo ""
echo "This will DELETE ALL demo data and reset to production state."
echo ""
read -p "Press Enter to continue or Ctrl+C to cancel..."

echo ""
echo "[1/3] Navigating to backend directory..."
cd backend || exit 1

echo ""
echo "[2/3] Running production reset script..."
python3 reset_to_production.py

echo ""
echo "[3/3] Returning to root directory..."
cd ..

echo ""
echo "============================================================================"
echo "Reset Complete!"
echo "============================================================================"
echo ""
echo "Next steps:"
echo "1. Start the backend server: cd backend && uvicorn main:app --reload"
echo "2. Open frontend in browser: frontend/index.html"
echo "3. Login as admin: admin001 / admin123"
echo "4. Change admin password immediately"
echo "5. Add real students and faculty"
echo ""
echo "============================================================================"
echo ""

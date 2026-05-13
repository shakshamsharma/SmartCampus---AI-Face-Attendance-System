# SmartCampus AI — Real Face Recognition Attendance

## Run on Windows
Double-click: start_windows.bat

## Run on Mac/Linux
bash start.sh

## Login
Admin:   admin001   / password123
Faculty: faculty001 / password123
Student: 2023CSE001 / password123  (Saksham Sharma)
Student: 2023CSE002 / password123  (Ashish Chandel)
Student: 2023CSE003 / password123  (Ashutosh Sharma)
Student: 2023CSE004 / password123  (Vishal Thakur)

## How it works
1. Each student logs in and registers face (5 angles via webcam)
2. Faculty starts session, places laptop facing students
3. Click Scan - OpenCV LBPH AI scans classroom
4. Recognized students auto-marked Present
5. Not detected = Absent
6. All records saved to database

## Project Structure
SmartCampus_RealAI/
├── start_windows.bat     <- Double click this on Windows
├── start.sh              <- Run this on Mac/Linux
├── README.md
├── backend/
│   ├── main.py           <- FastAPI (50+ endpoints)
│   ├── face_engine.py    <- Real OpenCV LBPH face recognition
│   ├── database.py       <- SQLAlchemy database models
│   ├── auth.py           <- JWT authentication
│   ├── seed.py           <- Demo data (30 days attendance)
│   ├── reports.py        <- PDF / Excel / CSV reports
│   └── requirements.txt  <- Python packages
└── frontend/
    └── index.html        <- React SPA (all UI)


Author By Saksham Sharma

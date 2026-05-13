# SmartCampus AI — Complete Project Overview

## What Is This Project?

SmartCampus AI is an AI-powered campus attendance management system built for universities and colleges. It automates the entire attendance workflow using real-time face recognition via webcam, replacing manual roll calls. Faculty scan the classroom, the system identifies students, marks attendance, and notifies everyone — all without any manual input.

The system also includes an AI chat assistant (powered by OpenAI GPT-4) that lets students check their attendance, apply for leave, and get predictions, while faculty can query analytics, generate reports, and manage their class — all through natural language.

---

## Tech Stack

### Backend
| Technology | Version | Purpose |
|---|---|---|
| Python | 3.10+ | Core language |
| FastAPI | 0.104.1 | REST API framework |
| Uvicorn | 0.24.0 | ASGI server |
| SQLAlchemy | 2.0.23 | ORM / database layer |
| SQLite | built-in | Database (dev); PostgreSQL recommended for production |
| OpenCV (`opencv-contrib-python`) | 4.13+ | Face detection and LBPH recognition |
| NumPy | 2.3+ | Image array processing |
| python-jose | 3.3.0 | JWT token creation and validation |
| passlib + argon2 | 1.7.4 | Password hashing |
| slowapi | 0.1.9+ | API rate limiting |
| Pydantic v2 + pydantic-settings | 2.0+ | Request validation and config management |
| ReportLab | 4.0.7 | PDF report generation |
| openpyxl | 3.1.2 | Excel report generation |
| OpenAI SDK | latest | GPT-4 AI assistant integration |
| WebSockets | built-in (FastAPI) | Real-time live scanning |

### Frontend
| Technology | Purpose |
|---|---|
| Vanilla HTML/CSS/JS | Single-file SPA (`frontend/index.html`) |
| React 18 (CDN, minified) | UI rendering, bundled inline |
| WebSocket API | Live face scan streaming |
| MediaDevices API (`getUserMedia`) | Webcam access |
| Canvas API | Frame capture from video stream |
| Fetch API | REST API calls |

### Infrastructure / Config
| Tool | Purpose |
|---|---|
| `.env` file | Environment-specific secrets and settings |
| Redis (optional) | Rate limiting and session store in production |
| Sentry (optional) | Error monitoring in production |
| Alembic | Database migrations |

---

## Project Structure

```
SmartCampus_RealAI/
├── frontend/
│   └── index.html              # Entire frontend — single HTML file with inline React + CSS
│
├── backend/
│   ├── main.py                 # FastAPI app, all REST + WebSocket routes
│   ├── database.py             # SQLAlchemy models and DB session
│   ├── auth.py                 # JWT auth, password hashing, account lockout
│   ├── auth_secure.py          # Extended auth with token blacklist and refresh tokens
│   ├── config.py               # Centralized settings via pydantic-settings
│   ├── face_engine.py          # Core face registration and recognition (LBPH)
│   ├── face_engine_realtime.py # Real-time frame-by-frame recognition engine
│   ├── realtime_attendance_api.py  # WebSocket router for live scanning
│   ├── reports.py              # PDF, CSV, Excel report generators
│   ├── seed.py                 # DB schema init (demo data disabled in production)
│   ├── requirements.txt        # Python dependencies
│   ├── .env                    # Environment variables (secrets)
│   ├── .env.example            # Template for .env
│   │
│   ├── face_data/              # Persisted face model files
│   │   ├── face_model_v2.pkl   # Pickled training data (face arrays + labels)
│   │   ├── label_map_v2.json   # Maps integer labels → student reg numbers
│   │   ├── lbph_model_v2.yml   # Trained OpenCV LBPH model
│   │   └── unknown_faces/      # Snapshots of unrecognized faces (security alerts)
│   │
│   ├── ai_assistant/
│   │   ├── core/
│   │   │   ├── llm_engine.py         # OpenAI API wrapper (chat, streaming, embeddings)
│   │   │   ├── intent_classifier.py  # Keyword + regex intent detection
│   │   │   ├── function_registry.py  # Maps AI function names to Python handlers
│   │   │   ├── context_manager.py    # Conversation history management
│   │   │   └── response_generator.py # Formats AI responses for the UI
│   │   ├── actions/
│   │   │   ├── attendance_actions.py # DB queries for attendance data
│   │   │   └── leave_actions.py      # DB queries for leave management
│   │   └── prompts/
│   │       └── system_prompts.py     # Role-specific GPT system prompts
│   │
│   └── tests/                  # Test suite (pytest)
│
├── smartcampus.db              # Root-level SQLite database
├── README.md                   # Basic setup instructions
├── START_SERVER.bat            # Windows: start backend server
├── STOP_SERVER.bat             # Windows: stop server
├── RESET_AND_START.bat         # Windows: reset DB and restart
├── start_windows.bat           # Alternative Windows start script
├── start.sh                    # Linux/Mac start script
└── reset_and_start.sh          # Linux/Mac reset and start
```

---

## Database Models

All models are defined in `database.py` using SQLAlchemy ORM with SQLite.

### `users`
Central auth table. Every student, faculty, and admin has a row here.
- `id` (PK, String) — registration number or employee ID
- `name`, `email`, `role` (student / faculty / admin)
- `password_hash` — argon2 hashed
- `last_login`, `created_at`

### `students`
Extended profile for students.
- `reg_no` (PK) — links to `users.id`
- `dept`, `semester`, `section`
- `face_registered` (Boolean) — whether face model is trained
- `face_registered_at` (DateTime)

### `faculty`
Extended profile for faculty.
- `faculty_id` (PK) — links to `users.id`
- `dept`, `subjects` (JSON array of subject names)

### `attendance_sessions`
One row per class session started by faculty.
- `faculty_id`, `subject`, `dept`, `semester`, `section`
- `date`, `period`, `status` (active / ended)
- `started_at`, `ended_at`
- `total_present`, `total_students`

### `attendance_records`
One row per student per session.
- `session_id` → FK to `attendance_sessions`
- `student_reg` → FK to `students`
- `subject`, `date`, `status` (present / absent / late)
- `marked_by_ai` (Boolean), `ai_confidence` (Float)
- `verified`, `marked_by`

### `notifications`
In-app notifications for all users.
- `user_id`, `title`, `message`, `icon`
- `is_read`, `created_at`

### `leave_requests`
Student leave applications.
- `student_reg`, `from_date`, `to_date`, `reason`, `leave_type`
- `status` (pending / approved / rejected)

### `disputes`
Students can dispute incorrect attendance records.
- `student_reg`, `record_id`, `subject`, `date`, `claim`
- `ai_confidence`, `status`, `resolution`

### `unknown_face_alerts`
Security alerts when an unrecognized face is detected in a session.
- `session_id`, `alert_id` (unique)
- `snapshot_b64` — base64 image of the unknown face
- `confidence`, `distance`, `closest_match`
- `is_read`, `resolved`, `notes`

### `audit_logs`
Full audit trail of all significant actions.
- `user_id`, `user_name`, `role`, `action`, `details`

---

## How the System Works — Full Workflow

### 1. Authentication Flow

```
User enters ID + password + role on login page
    → POST /api/auth/login
    → Rate limited: 5 attempts/minute per IP
    → Account lockout after 5 failed attempts (15 min)
    → Password verified against argon2 hash
    → JWT token issued (24h expiry, HS256)
    → Token stored in browser memory
    → All subsequent requests use Bearer token header
```

### 2. Face Registration (Student)

```
Student opens "Register Face" page
    → Browser requests webcam access (MediaDevices API)
    → Student captures 5 photos at different angles
      (front, left, right, up, down)
    → Each frame captured via Canvas API → base64 encoded
    → POST /api/student/register-face  { images: [base64, ...] }
    → Backend: face_engine.register_face()
        → Decodes each base64 image
        → Runs Haar Cascade face detection (3 strategies, aggressive)
        → Extracts face ROI, resizes to 150×150 grayscale
        → Assigns integer label to student reg_no
        → Trains/retrains OpenCV LBPH model with all students
        → Saves: face_model_v2.pkl, lbph_model_v2.yml, label_map_v2.json
    → DB: student.face_registered = True
    → Notification sent to student
```

### 3. Attendance Session — Faculty Workflow

```
Step 1: Faculty starts session
    → POST /api/faculty/session/start
    → Creates AttendanceSession row (status: active)
    → Returns session_id

Step 2: Faculty scans classroom
    → Browser opens webcam
    → Captures multiple frames (typically 10–30) over a few seconds
    → All frames base64 encoded
    → POST /api/faculty/session/scan-frames  { frames: [...], session_id: N }
    → Backend: face_engine.recognize_faces_multi_frame()
        → For each frame:
            → Aggressive face detection (3 cascade strategies)
            → For each detected face:
                → LBPH recognizer.predict() → (label, distance)
                → distance ≤ 100 → matched student
                → Tracks detections per student across all frames
        → Final decision per student:
            → avg_score ≥ 20% AND detection_rate ≥ 10% → PRESENT (auto)
            → avg_score ≥ 15% AND detection_rate ≥ 5%  → LOW CONFIDENCE (needs verify)
            → Otherwise → ABSENT
        → Unknown faces (distance > threshold) → saved as alerts
    → Returns: { detected, low_confidence, not_detected, unknown_faces }

Step 3: Faculty reviews results
    → Sees present/verify/absent list with confidence scores
    → Can manually toggle any student's status
    → Can view unknown face snapshots

Step 4: Faculty ends session
    → POST /api/faculty/session/end
    → AttendanceRecord created for every student (present or absent)
    → Notifications sent to all students
    → Low attendance warnings triggered if student drops below 75%
    → Session status → ended
```

### 4. Real-Time Live Scanning (WebSocket)

An alternative to batch scanning — for continuous live recognition:

```
Faculty connects: WebSocket /ws/realtime-scan/{session_id}?token=JWT
    → Server: get_engine() initializes real-time engine
    → Client sends frames continuously:
        { "type": "frame", "frame": "base64..." }
    → Server responds per frame:
        { "type": "update", "data": { recognized: [...], confidence: ... } }
    → Client sends final request:
        { "type": "get_final" }
    → Server returns cumulative attendance summary
    → POST /api/faculty/session/end-realtime/{session_id} saves records
```

### 5. AI Assistant

```
User opens chat widget (floating button, bottom-right)
    → POST /api/ai/chat  { message: "...", role: "student" }
    → IntentClassifier: keyword + regex matching → intent + confidence
    → FunctionRegistry: maps intent to available functions for this role
    → LLMEngine: sends to OpenAI GPT-4 with:
        - Role-specific system prompt
        - Conversation history
        - Available function schemas (OpenAI function calling)
    → GPT-4 decides to call a function or respond directly
    → If function call:
        → FunctionRegistry.execute() → real DB query
        → Result injected back into GPT-4 context
        → GPT-4 generates natural language response
    → Response streamed back to user
```

### 6. Reports

```
Faculty/Admin requests report
    → GET /api/faculty/reports/attendance?format=pdf&subject=DSA
    → Backend queries AttendanceRecord table
    → reports.py generates:
        PDF  → ReportLab (styled with SmartCampus branding)
        CSV  → Python csv module
        Excel → openpyxl (with colored headers and formatting)
    → File returned as binary response with correct Content-Type
```

---

## API Endpoints Reference

### Auth
| Method | Endpoint | Access | Description |
|---|---|---|---|
| POST | `/api/auth/login` | Public | Login, returns JWT |

### Student
| Method | Endpoint | Access | Description |
|---|---|---|---|
| GET | `/api/student/dashboard` | Student | Overall + subject-wise attendance stats |
| GET | `/api/student/attendance-logs` | Student | Paginated attendance history |
| GET | `/api/student/monthly-trend` | Student | Month-by-month attendance chart data |
| POST | `/api/student/register-face` | Student | Register face (5 angle images) |
| POST | `/api/student/re-register-face` | Student | Re-register face (replaces old) |
| POST | `/api/student/leave` | Student | Submit leave request |
| POST | `/api/student/dispute` | Student | Raise attendance dispute |

### Faculty
| Method | Endpoint | Access | Description |
|---|---|---|---|
| POST | `/api/faculty/session/start` | Faculty | Start attendance session |
| POST | `/api/faculty/session/scan-frames` | Faculty | Batch scan (multi-frame recognition) |
| POST | `/api/faculty/session/scan-single` | Faculty | Single frame live preview |
| POST | `/api/faculty/session/end` | Faculty | End session, save all records |
| POST | `/api/faculty/session/start-realtime` | Faculty | Start real-time WebSocket session |
| POST | `/api/faculty/session/end-realtime/{id}` | Faculty | End real-time session |
| GET | `/api/faculty/sessions` | Faculty | List all sessions |
| GET | `/api/faculty/students` | Faculty | List all students with attendance |
| GET | `/api/faculty/leave-requests` | Faculty | View pending leave requests |
| POST | `/api/faculty/leave/{id}/approve` | Faculty | Approve leave |
| POST | `/api/faculty/leave/{id}/reject` | Faculty | Reject leave |
| GET | `/api/faculty/unknown-faces` | Faculty | Security alerts (unknown faces) |
| POST | `/api/faculty/unknown-faces/{id}/mark-read` | Faculty | Mark alert as read |
| POST | `/api/faculty/unknown-faces/{id}/resolve` | Faculty | Resolve alert with notes |
| GET | `/api/faculty/reports/attendance` | Faculty | Download attendance report (PDF/CSV/Excel) |

### Admin
| Method | Endpoint | Access | Description |
|---|---|---|---|
| GET | `/api/admin/dashboard` | Admin | System-wide stats |
| GET | `/api/admin/students` | Admin | All students |
| POST | `/api/admin/students` | Admin | Add new student |
| GET | `/api/admin/sessions` | Admin | All attendance sessions |
| POST | `/api/admin/attendance/manual` | Admin | Manually mark attendance |
| GET | `/api/admin/disputes` | Admin | All disputes |
| POST | `/api/admin/disputes/{id}/resolve` | Admin | Resolve dispute |
| GET | `/api/admin/audit-logs` | Admin | Full audit trail |
| GET | `/api/admin/security-dashboard` | Admin | Unknown face analytics |

### Shared
| Method | Endpoint | Access | Description |
|---|---|---|---|
| GET | `/api/notifications` | All | Get user notifications |
| POST | `/api/notifications/{id}/read` | All | Mark notification read |
| GET | `/api/face/stats` | All | Face registration stats |
| POST | `/api/ai/chat` | All | AI assistant chat |
| GET | `/api/health` | Public | Health check |

### WebSockets
| Endpoint | Description |
|---|---|
| `WS /ws/scan/{session_id}` | Batch scan WebSocket (send frames, get results) |
| `WS /ws/realtime-scan/{session_id}?token=JWT` | Live continuous recognition stream |

---

## Face Recognition — Technical Details

The face recognition system is built entirely on OpenCV, with no external face recognition APIs.

### Algorithm: LBPH (Local Binary Pattern Histogram)
- Divides face image into a grid of cells
- Computes LBP (texture descriptor) for each cell
- Concatenates histograms → feature vector
- Comparison: Chi-squared distance between histograms
- Lower distance = better match

### Configuration
```python
recognizer = cv2.face.LBPHFaceRecognizer_create(
    radius=1,
    neighbors=8,
    grid_x=8,
    grid_y=8,
    threshold=150   # Accept distances up to 150
)

LBPH_DISTANCE_THRESHOLD = 100   # Match threshold
MIN_MATCH_SCORE = 20            # Minimum 20% match score
MIN_DETECTION_RATE = 0.10       # Detected in at least 10% of frames
```

### Detection Pipeline (Aggressive Mode)
Three parallel strategies run on every frame:
1. Standard Haar Cascade (`scaleFactor=1.1, minNeighbors=3`)
2. Histogram-equalized image (`scaleFactor=1.05, minNeighbors=2`)
3. Very aggressive (`scaleFactor=1.03, minNeighbors=1`)

Duplicate detections (>50% overlap) are merged. All unique faces are then passed to the LBPH recognizer.

### Model Persistence
- `face_model_v2.pkl` — raw face arrays + integer labels (for retraining)
- `lbph_model_v2.yml` — trained LBPH model (OpenCV format)
- `label_map_v2.json` — `{ "0": "2023CSE001", "1": "2023CSE002", ... }`

When a new student registers, the model is retrained from scratch with all existing + new samples.

---

## Security Features

### Authentication
- JWT tokens (HS256, 24h expiry)
- Argon2 password hashing (more secure than bcrypt)
- Token blacklist support (in-memory; Redis in production)
- Refresh token support (7-day expiry)

### Rate Limiting
- Global: 60 requests/minute per IP
- Login endpoint: 5 requests/minute per IP (via slowapi)

### Account Protection
- Account lockout after 5 failed login attempts
- 15-minute lockout duration (configurable)
- Per-user + per-IP tracking

### Input Validation
- All request bodies validated via Pydantic v2
- User ID: alphanumeric only (regex validation, SQL injection prevention)
- Role field: enum-constrained (`student | faculty | admin`)
- Password strength policy: min 8 chars, uppercase, lowercase, digit, special char

### CORS
- Restricted to configured origins (no wildcard in production)
- Configurable via `ALLOWED_ORIGINS` env variable

### Unknown Face Security
- Any face detected during a scan that doesn't match any registered student is flagged
- Snapshot saved to `face_data/unknown_faces/`
- Alert stored in `unknown_face_alerts` table
- Faculty notified immediately via in-app notification
- Admin security dashboard shows analytics on unknown face incidents

### Audit Logging
Every significant action (login, session start/end, face registration, report generation, dispute resolution) is logged to `audit_logs` with user ID, role, action, and details.

---

## AI Assistant — Technical Details

### Architecture
```
User message
    → IntentClassifier (keyword + regex, 13 intent categories)
    → FunctionRegistry (role-based function filtering)
    → LLMEngine → OpenAI GPT-4 Turbo
        → Function calling (OpenAI tools API)
        → Real DB queries via action handlers
    → Response back to user
```

### Intent Categories
`attendance_query`, `attendance_prediction`, `leave_application`, `timetable_query`, `report_generation`, `student_query`, `notification_send`, `eligibility_check`, `campus_search`, `analytics_query`, `greeting`, `help`, `general_query`

### Role-Based Behavior
Each role gets a different system prompt and different available functions:

- **Student**: Can check own attendance, apply leave, check eligibility, view timetable
- **Faculty**: Can view class analytics, identify low-attendance students, approve/reject leave, generate reports, send notifications
- **Admin**: Full access to all functions, system-wide analytics, security dashboard

### Function Calling (OpenAI Tools API)
The AI can call real database functions mid-conversation:
- `get_attendance(student_id, subject)` → live DB query
- `predict_attendance(student_id, days_ahead)` → linear regression on historical data
- `check_eligibility(student_id)` → 75% threshold check
- `apply_leave(from_date, to_date, reason, leave_type)` → inserts LeaveRequest row
- `get_low_attendance_students(threshold, subject)` → faculty analytics
- `send_notification(recipients, title, message)` → bulk notifications
- `generate_report(report_type, filters, format)` → triggers report generation

---

## Configuration (`.env`)

Key environment variables:

```env
# App
ENVIRONMENT=development          # development | production
DEBUG=True                       # False in production
SECRET_KEY=your-secret-key       # JWT signing key

# Database
DATABASE_URL=sqlite:///./smartcampus.db   # Use PostgreSQL in production

# CORS
ALLOWED_ORIGINS=http://localhost:3000,http://localhost:5173

# Face Recognition
FACE_RECOGNITION_THRESHOLD=60
UNKNOWN_FACE_THRESHOLD=75

# Rate Limiting
LOGIN_RATE_LIMIT_PER_MINUTE=5
RATE_LIMIT_PER_MINUTE=60

# AI Assistant
OPENAI_API_KEY=sk-...
AI_MODEL=gpt-4-turbo-preview

# Security
MAX_LOGIN_ATTEMPTS=5
LOCKOUT_DURATION_MINUTES=15
ACCESS_TOKEN_EXPIRE_HOURS=24

# Optional
REDIS_ENABLED=False
SENTRY_ENABLED=False
SMTP_ENABLED=False
```

---

## How to Run

### Prerequisites
- Python 3.10+
- pip

### Install dependencies
```bash
cd backend
pip install -r requirements.txt
```

### Start the server
```bash
# Windows
START_SERVER.bat

# Linux/Mac
./start.sh

# Manual
cd backend
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### Access
- Frontend: open `frontend/index.html` in a browser (or serve via any static server)
- API docs (dev only): `http://localhost:8000/api/docs`
- Health check: `http://localhost:8000/api/health`

### Default Accounts (demo data — only if seed is re-enabled)
| Role | ID | Password |
|---|---|---|
| Admin | admin001 | password123 |
| Faculty | faculty001 | password123 |
| Student | 2023CSE001 | password123 |
| Student | 2023CSE002 | password123 |

---

## Key Design Decisions

**Single-file frontend** — The entire UI is one `index.html` with inline React (CDN), CSS variables for theming, and vanilla JS for API calls. No build step, no npm, no bundler. Easy to deploy anywhere.

**OpenCV LBPH over cloud APIs** — Face recognition runs entirely on-device. No data sent to external services, no API costs, works offline. The tradeoff is lower accuracy compared to deep learning models, mitigated by aggressive multi-frame scanning and lenient thresholds.

**Multi-frame scanning** — Instead of relying on a single frame, faculty capture 10–30 frames. A student is marked present only if detected consistently across frames, reducing false positives from partial face captures.

**SQLite for development** — Zero-config, file-based database. The config explicitly warns to switch to PostgreSQL for production.

**Role-based everything** — Auth, API endpoints, AI assistant behavior, and function access are all gated by role. The `require_role()` dependency in FastAPI makes this clean and consistent.

**Audit trail** — Every action is logged. This is important for a system that affects student academic records — disputes can always be traced back to who did what and when.

"""
SmartCampus AI - FastAPI Backend with REAL Face Recognition
Uses OpenCV LBPH for genuine face matching - no simulation
"""
from fastapi import FastAPI, Depends, HTTPException, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional, List
import json, random, asyncio, base64, logging

from database import (get_db, init_db, User, Student, Faculty,
                      AttendanceSession, AttendanceRecord,
                      Notification, LeaveRequest, Dispute, AuditLog, UnknownFaceAlert)
from auth import (hash_password, verify_password, create_access_token, get_current_user, require_role,
                  check_account_locked, record_failed_login, reset_login_attempts, validate_password_strength)
from reports import generate_attendance_pdf, generate_attendance_csv, generate_attendance_excel
from seed import seed
from face_engine import (register_face, recognize_faces_multi_frame,
                          recognize_faces_in_frame, delete_face,
                          check_face_registered, get_registration_stats)
from config import settings
from realtime_attendance_api import router as realtime_router
from pydantic import BaseModel, Field, field_validator
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import re

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize rate limiter
limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="AI-Powered Attendance Management System with Real Face Recognition",
    docs_url="/api/docs" if settings.DEBUG else None,  # Disable docs in production
    redoc_url="/api/redoc" if settings.DEBUG else None
)

# Add rate limiter to app
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS Configuration - Use settings instead of wildcard
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,  # Restricted origins from config
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    allow_headers=["*"],
    expose_headers=["X-Total-Count", "X-Page-Count"]
)

# ── Active WebSocket sessions for live scanning ──────────────────────────────
active_scan_sessions = {}  # session_id -> {"ws": websocket, "frames": []}

# ── INCLUDE REAL-TIME ATTENDANCE ROUTER ──────────────────────────────────────
app.include_router(realtime_router)


@app.on_event("startup")
def startup():
    seed()
    logger.info("SmartCampus AI v3.0 started with real face recognition")
    logger.info("Real-time face recognition engine loaded")


def log_action(db, user_id, user_name, role, action, details=""):
    db.add(AuditLog(user_id=user_id, user_name=user_name, role=role,
                    action=action, details=details))
    db.commit()


# ── SCHEMAS WITH VALIDATION ──────────────────────────────────────────────────
class LoginRequest(BaseModel):
    id: str = Field(..., min_length=3, max_length=50, description="User ID")
    password: str = Field(..., min_length=1, max_length=100, description="Password")
    role: str = Field(..., pattern="^(student|faculty|admin)$", description="User role")
    
    @field_validator('id')
    @classmethod
    def validate_id(cls, v):
        # Prevent SQL injection attempts
        if not re.match(r'^[a-zA-Z0-9_-]+$', v):
            raise ValueError("ID contains invalid characters")
        return v.strip()

class FaceRegisterRequest(BaseModel):
    images: List[str]  # list of base64 images (one per angle)

class FaceScanRequest(BaseModel):
    frames: List[str]  # base64 frames from classroom scan
    session_id: Optional[int] = None  # session ID for unknown face tracking

class SessionStartRequest(BaseModel):
    subject: str
    dept: str = "CSE"
    semester: int = 6
    section: str = "A"
    period: str = "1st"

class SessionEndRequest(BaseModel):
    session_id: int
    detected_students: List[str]
    manual_students: List[str] = []

class ManualMarkRequest(BaseModel):
    student_reg: str
    subject: str
    date: str
    status: str

class AddStudentRequest(BaseModel):
    reg_no: str
    name: str
    dept: str = "CSE"
    semester: int = 6
    section: str = "A"
    password: str = "password123"

class LeaveRequestModel(BaseModel):
    from_date: str
    to_date: str
    reason: str
    leave_type: str

class DisputeModel(BaseModel):
    record_id: Optional[int] = None
    subject: str
    date: str
    claim: str


# ── AUTH WITH SECURITY ───────────────────────────────────────────────────────
@app.post("/api/auth/login")
@limiter.limit(f"{settings.LOGIN_RATE_LIMIT_PER_MINUTE}/minute")
async def login(req: LoginRequest, request: Request, db: Session = Depends(get_db)):
    """
    Secure login with rate limiting and account lockout protection
    """
    # Check if account is locked
    is_locked, lock_message = check_account_locked(req.id)
    if is_locked:
        logger.warning(f"Login attempt for locked account: {req.id}")
        raise HTTPException(status_code=423, detail=lock_message)
    
    # Find user
    user = db.query(User).filter(User.id == req.id).first()
    
    # Verify credentials
    if not user or not verify_password(req.password, user.password_hash):
        record_failed_login(req.id)
        logger.warning(f"Failed login attempt for user: {req.id}")
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    # Verify role
    if user.role != req.role:
        logger.warning(f"Role mismatch for user {req.id}: expected {req.role}, got {user.role}")
        raise HTTPException(status_code=403, detail=f"This account is a {user.role} account")
    
    # Successful login - reset attempts
    reset_login_attempts(req.id)
    
    # Update last login
    user.last_login = datetime.utcnow()
    db.commit()
    
    # Log action
    log_action(db, user.id, user.name, user.role, "Login", f"Successful login from {request.client.host}")
    
    # Create token
    token = create_access_token({
        "sub": user.id,
        "role": user.role,
        "name": user.name
    })
    
    logger.info(f"User {user.id} ({user.role}) logged in successfully")
    
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_HOURS * 3600,
        "user": {
            "id": user.id,
            "name": user.name,
            "role": user.role,
            "last_login": user.last_login.isoformat() if user.last_login else None
        }
    }


# ── FACE REGISTRATION (REAL) ─────────────────────────────────────────────────
@app.post("/api/student/register-face")
def register_student_face(
    req: FaceRegisterRequest,
    current_user: User = Depends(require_role("student")),
    db: Session = Depends(get_db)
):
    """
    REAL face registration using OpenCV LBPH.
    Receives multiple base64 images (different angles),
    detects faces, trains LBPH model, saves to disk.
    """
    if len(req.images) < 3:
        raise HTTPException(400, "Need at least 3 face images for registration")

    result = register_face(current_user.id, req.images)

    if not result["success"]:
        raise HTTPException(400, result.get("error", "Face registration failed"))

    # Update database
    student = db.query(Student).filter(Student.reg_no == current_user.id).first()
    if student:
        student.face_registered = True
        student.face_registered_at = datetime.utcnow()
        db.commit()

    db.add(Notification(
        user_id=current_user.id, icon="🤖",
        title="Face Registered Successfully",
        message=f"Your face is now registered with {result['samples_captured']} samples. AI attendance is active."
    ))
    db.commit()
    log_action(db, current_user.id, current_user.name, "student",
               "Face Registered", f"{result['samples_captured']} face samples captured")

    return {
        "success": True,
        "samples_captured": result["samples_captured"],
        "message": "Face registered successfully! AI will now recognize you in class."
    }


@app.post("/api/student/re-register-face")
def re_register_face(
    req: FaceRegisterRequest,
    current_user: User = Depends(require_role("student")),
    db: Session = Depends(get_db)
):
    """Re-register face (appearance change)"""
    delete_face(current_user.id)
    return register_student_face(req, current_user, db)


@app.get("/api/face/stats")
def face_stats(current_user: User = Depends(get_current_user)):
    """Get face registration stats"""
    return get_registration_stats()


# ── ATTENDANCE SESSION WITH REAL FACE SCAN ───────────────────────────────────
@app.post("/api/faculty/session/start")
def start_session(
    req: SessionStartRequest,
    current_user: User = Depends(require_role("faculty")),
    db: Session = Depends(get_db)
):
    today = datetime.now().strftime("%Y-%m-%d")
    session = AttendanceSession(
        faculty_id=current_user.id, subject=req.subject, dept=req.dept,
        semester=req.semester, section=req.section, date=today,
        period=req.period, status="active", total_students=4
    )
    db.add(session)
    db.commit()
    log_action(db, current_user.id, current_user.name, "faculty",
               "Session Started", f"{req.subject} — {req.dept} {req.semester}th Sem {req.section}")
    return {
        "session_id": session.id,
        "subject": session.subject,
        "date": today,
        "started_at": session.started_at.isoformat(),
        "face_engine": "OpenCV LBPH Real Recognition"
    }


@app.post("/api/faculty/session/scan-frames")
def scan_classroom_frames(
    req: FaceScanRequest,
    current_user: User = Depends(require_role("faculty")),
    db: Session = Depends(get_db)
):
    """
    REAL face recognition from classroom frames.
    Faculty sends multiple frames captured from webcam,
    engine matches faces against registered embeddings.
    Detects unknown faces and triggers security alerts.
    """
    if not req.frames:
        raise HTTPException(400, "No frames provided")

    logger.info(f"Processing {len(req.frames)} frames for attendance scan (session: {req.session_id})")

    # Real face recognition across all frames with unknown face detection
    scan_result = recognize_faces_multi_frame(req.frames, session_id=req.session_id)

    # Get ALL students from database
    all_students = db.query(Student).all()
    students_map = {s.reg_no: s.name for s in all_students}
    
    # Track which students were detected
    detected_reg_nos = set()
    
    # Enrich detected students with names
    for item in scan_result.get("detected", []):
        item["name"] = students_map.get(item["reg_no"], item["reg_no"])
        detected_reg_nos.add(item["reg_no"])

    # Enrich low confidence students with names
    for item in scan_result.get("low_confidence", []):
        item["name"] = students_map.get(item["reg_no"], item["reg_no"])
        detected_reg_nos.add(item["reg_no"])

    # Enrich not detected students with names
    for item in scan_result.get("not_detected", []):
        item["name"] = students_map.get(item.get("reg_no", ""), "Unknown")
        detected_reg_nos.add(item.get("reg_no", ""))
    
    # CRITICAL FIX: Add students who are in database but not in face model
    # These are students who haven't registered their faces yet
    not_detected_list = scan_result.get("not_detected", [])
    for student in all_students:
        if student.reg_no not in detected_reg_nos:
            not_detected_list.append({
                "reg_no": student.reg_no,
                "name": student.name,
                "reason": "face_not_registered" if not student.face_registered else "not_detected_in_any_frame"
            })
            logger.info(f"[SCAN] {student.reg_no} ({student.name}): Added to not_detected - "
                       f"{'face not registered' if not student.face_registered else 'not detected in frames'}")
    
    scan_result["not_detected"] = not_detected_list

    # Save unknown face alerts to database
    unknown_faces = scan_result.get("unknown_faces", [])
    if unknown_faces and req.session_id:
        for unknown in unknown_faces:
            try:
                alert = UnknownFaceAlert(
                    session_id=req.session_id,
                    alert_id=unknown.get("alert_id"),
                    snapshot_path=unknown.get("snapshot_path", ""),
                    snapshot_b64=unknown.get("snapshot_b64", ""),
                    confidence=unknown.get("confidence", 0.0),
                    distance=unknown.get("distance", 0.0),
                    closest_match=unknown.get("closest_match"),
                    face_location=json.dumps(unknown.get("face_location", {})),
                    alert_time=datetime.fromisoformat(unknown.get("alert_time"))
                )
                db.add(alert)
                
                # Create notification for faculty
                session = db.query(AttendanceSession).filter(AttendanceSession.id == req.session_id).first()
                if session:
                    notif = Notification(
                        user_id=session.faculty_id,
                        title="⚠ Unknown Face Detected",
                        message=f"Unknown person detected in {session.subject} class at {datetime.now().strftime('%I:%M %p')}",
                        icon="⚠"
                    )
                    db.add(notif)
                
                logger.warning(f"[ALERT] Unknown face alert saved: {unknown.get('alert_id')}")
            except Exception as e:
                logger.error(f"[ALERT] Failed to save unknown face alert: {e}")
        
        db.commit()

    logger.info(f"Scan result: {len(scan_result.get('detected',[]))} auto-detected, "
                f"{len(scan_result.get('low_confidence',[]))} need verify, "
                f"{len(scan_result.get('not_detected',[]))} absent, "
                f"{len(unknown_faces)} unknown faces")

    return scan_result


@app.post("/api/faculty/session/scan-single")
def scan_single_frame(
    req: FaceScanRequest,
    current_user: User = Depends(require_role("faculty")),
    db: Session = Depends(get_db)
):
    """Scan a single frame - for live preview during scanning"""
    if not req.frames:
        raise HTTPException(400, "No frame provided")

    results = recognize_faces_in_frame(req.frames[0])
    students_map = {s.reg_no: s.name for s in db.query(Student).all()}

    for r in results:
        r["name"] = students_map.get(r["reg_no"], r["reg_no"])

    return {"faces_in_frame": results, "count": len(results)}


@app.post("/api/faculty/session/end")
def end_session(
    req: SessionEndRequest,
    current_user: User = Depends(require_role("faculty")),
    db: Session = Depends(get_db)
):
    session = db.query(AttendanceSession).filter(
        AttendanceSession.id == req.session_id).first()
    if not session:
        raise HTTPException(404, "Session not found")

    session.status = "ended"
    session.ended_at = datetime.utcnow()
    today = datetime.now().strftime("%Y-%m-%d")

    all_students = db.query(Student).all()
    present_set = set(req.detected_students + req.manual_students)

    # Save attendance records
    recs_added = 0
    for student in all_students:
        is_present = student.reg_no in req.detected_students
        is_manual = student.reg_no in req.manual_students
        status = "present" if (is_present or is_manual) else "absent"

        existing = db.query(AttendanceRecord).filter(
            AttendanceRecord.session_id == req.session_id,
            AttendanceRecord.student_reg == student.reg_no
        ).first()

        if not existing:
            db.add(AttendanceRecord(
                session_id=req.session_id, student_reg=student.reg_no,
                subject=session.subject, date=today, status=status,
                marked_by_ai=is_present, verified=True, marked_by=current_user.id
            ))
            recs_added += 1

        # Notify student
        if status == "present":
            db.add(Notification(
                user_id=student.reg_no, icon="✅",
                title=f"Attendance Marked — {session.subject}",
                message=f"You were recognized and marked present in {session.subject} on {today}."
            ))
        else:
            db.add(Notification(
                user_id=student.reg_no, icon="❌",
                title=f"Marked Absent — {session.subject}",
                message=f"You were not detected in {session.subject} session on {today}. Raise a dispute if incorrect."
            ))

    session.total_present = len(present_set)
    db.commit()

    # Check attendance thresholds and alert
    for student in all_students:
        records = db.query(AttendanceRecord).filter(
            AttendanceRecord.student_reg == student.reg_no).all()
        if records:
            pct = sum(1 for r in records if r.status in ("present", "late")) / len(records) * 100
            if pct < 75:
                db.add(Notification(
                    user_id=student.reg_no, icon="⚠️",
                    title="Low Attendance Warning",
                    message=f"Your attendance is now {round(pct, 1)}%. Attend upcoming classes urgently."
                ))
    db.commit()

    log_action(db, current_user.id, current_user.name, "faculty",
               "Session Ended",
               f"Session {req.session_id} — {len(present_set)}/{len(all_students)} present")

    return {
        "success": True,
        "present": len(present_set),
        "absent": len(all_students) - len(present_set),
        "total": len(all_students),
        "records_saved": recs_added
    }


# ── WEBSOCKET for Live Scanning ──────────────────────────────────────────────
@app.websocket("/ws/scan/{session_id}")
async def websocket_scan(websocket: WebSocket, session_id: int,
                          token: str = None):
    """
    WebSocket endpoint for live classroom scanning.
    Faculty frontend sends frames continuously,
    backend responds with real-time face detection results.
    """
    await websocket.accept()
    active_scan_sessions[session_id] = {"ws": websocket, "frames": [], "results": {}}
    logger.info(f"WebSocket scan session {session_id} opened")

    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)

            if msg.get("type") == "frame":
                b64_frame = msg.get("frame")
                if b64_frame:
                    # Real-time face detection on this single frame
                    faces = recognize_faces_in_frame(b64_frame)
                    await websocket.send_text(json.dumps({
                        "type": "frame_result",
                        "faces": faces,
                        "count": len(faces)
                    }))

            elif msg.get("type") == "final_scan":
                frames = msg.get("frames", [])
                if frames:
                    result = recognize_faces_multi_frame(frames)
                    await websocket.send_text(json.dumps({
                        "type": "final_result",
                        **result
                    }))

            elif msg.get("type") == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))

    except WebSocketDisconnect:
        logger.info(f"WebSocket session {session_id} closed")
        active_scan_sessions.pop(session_id, None)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        active_scan_sessions.pop(session_id, None)


# ── UNKNOWN FACE SECURITY ENDPOINTS ──────────────────────────────────────────
@app.get("/api/faculty/unknown-faces")
def get_unknown_faces(
    session_id: Optional[int] = None,
    limit: int = 50,
    current_user: User = Depends(require_role("faculty")),
    db: Session = Depends(get_db)
):
    """Get unknown face alerts for faculty security dashboard"""
    query = db.query(UnknownFaceAlert)
    
    if session_id:
        query = query.filter(UnknownFaceAlert.session_id == session_id)
    
    alerts = query.order_by(UnknownFaceAlert.alert_time.desc()).limit(limit).all()
    
    result = []
    for alert in alerts:
        session = db.query(AttendanceSession).filter(AttendanceSession.id == alert.session_id).first()
        result.append({
            "id": alert.id,
            "alert_id": alert.alert_id,
            "session_id": alert.session_id,
            "subject": session.subject if session else "Unknown",
            "date": session.date if session else "",
            "period": session.period if session else "",
            "snapshot_b64": alert.snapshot_b64,
            "confidence": alert.confidence,
            "distance": alert.distance,
            "closest_match": alert.closest_match,
            "alert_time": alert.alert_time.isoformat() if alert.alert_time else "",
            "is_read": alert.is_read,
            "resolved": alert.resolved,
            "notes": alert.notes
        })
    
    return {"alerts": result, "total": len(result)}


@app.post("/api/faculty/unknown-faces/{alert_id}/mark-read")
def mark_unknown_face_read(
    alert_id: int,
    current_user: User = Depends(require_role("faculty")),
    db: Session = Depends(get_db)
):
    """Mark unknown face alert as read"""
    alert = db.query(UnknownFaceAlert).filter(UnknownFaceAlert.id == alert_id).first()
    if not alert:
        raise HTTPException(404, "Alert not found")
    
    alert.is_read = True
    db.commit()
    
    return {"success": True, "message": "Alert marked as read"}


@app.post("/api/faculty/unknown-faces/{alert_id}/resolve")
def resolve_unknown_face(
    alert_id: int,
    notes: Optional[str] = None,
    current_user: User = Depends(require_role("faculty")),
    db: Session = Depends(get_db)
):
    """Resolve unknown face alert with notes"""
    alert = db.query(UnknownFaceAlert).filter(UnknownFaceAlert.id == alert_id).first()
    if not alert:
        raise HTTPException(404, "Alert not found")
    
    alert.resolved = True
    alert.is_read = True
    if notes:
        alert.notes = notes
    db.commit()
    
    return {"success": True, "message": "Alert resolved"}


@app.get("/api/admin/security-dashboard")
def admin_security_dashboard(
    current_user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db)
):
    """Admin security dashboard with unknown face analytics"""
    # Get all unknown face alerts
    all_alerts = db.query(UnknownFaceAlert).all()
    
    # Get recent alerts (last 7 days)
    from datetime import timedelta
    week_ago = datetime.now() - timedelta(days=7)
    recent_alerts = [a for a in all_alerts if a.alert_time and a.alert_time >= week_ago]
    
    # Group by session
    sessions_with_unknowns = {}
    for alert in all_alerts:
        if alert.session_id not in sessions_with_unknowns:
            sessions_with_unknowns[alert.session_id] = 0
        sessions_with_unknowns[alert.session_id] += 1
    
    # Get unresolved alerts
    unresolved = [a for a in all_alerts if not a.resolved]
    
    return {
        "total_alerts": len(all_alerts),
        "recent_alerts": len(recent_alerts),
        "unresolved_alerts": len(unresolved),
        "sessions_affected": len(sessions_with_unknowns),
        "alerts_by_session": sessions_with_unknowns,
        "recent_alerts_data": [
            {
                "id": a.id,
                "alert_id": a.alert_id,
                "session_id": a.session_id,
                "alert_time": a.alert_time.isoformat() if a.alert_time else "",
                "confidence": a.confidence,
                "resolved": a.resolved
            }
            for a in sorted(recent_alerts, key=lambda x: x.alert_time, reverse=True)[:10]
        ]
    }


# ── STUDENT ENDPOINTS ────────────────────────────────────────────────────────
@app.get("/api/student/dashboard")
def student_dashboard(current_user: User = Depends(require_role("student")),
                       db: Session = Depends(get_db)):
    student = db.query(Student).filter(Student.reg_no == current_user.id).first()
    if not student:
        raise HTTPException(404, "Student not found")

    records = db.query(AttendanceRecord).filter(
        AttendanceRecord.student_reg == current_user.id).all()

    subject_stats = {}
    for r in records:
        if r.subject not in subject_stats:
            subject_stats[r.subject] = {"present": 0, "total": 0, "late": 0}
        subject_stats[r.subject]["total"] += 1
        if r.status in ("present", "late"):
            subject_stats[r.subject]["present"] += 1
        if r.status == "late":
            subject_stats[r.subject]["late"] += 1

    subject_pct = {
        sub: {
            "percentage": round(v["present"] / v["total"] * 100, 1) if v["total"] > 0 else 0,
            "present": v["present"], "total": v["total"], "late": v["late"]
        }
        for sub, v in subject_stats.items()
    }

    total_present = sum(s["present"] for s in subject_stats.values())
    total_classes = sum(s["total"] for s in subject_stats.values())
    total_late = sum(s["late"] for s in subject_stats.values())
    overall_pct = round(total_present / total_classes * 100, 1) if total_classes > 0 else 0
    risk = "safe" if overall_pct >= 75 else "warning" if overall_pct >= 65 else "critical"

    return {
        "student": {
            "reg_no": student.reg_no, "name": student.name,
            "dept": student.dept, "semester": student.semester,
            "section": student.section, "face_registered": student.face_registered,
            "face_registered_at": student.face_registered_at.isoformat() if student.face_registered_at else None
        },
        "summary": {
            "overall_percentage": overall_pct, "total_present": total_present,
            "total_classes": total_classes, "total_absent": total_classes - total_present,
            "total_late": total_late, "risk": risk
        },
        "subjects": subject_pct
    }


@app.get("/api/student/attendance-logs")
def attendance_logs(subject: Optional[str] = None, limit: int = 60,
                    current_user: User = Depends(require_role("student")),
                    db: Session = Depends(get_db)):
    q = db.query(AttendanceRecord).filter(
        AttendanceRecord.student_reg == current_user.id)
    if subject:
        q = q.filter(AttendanceRecord.subject == subject)
    records = q.order_by(AttendanceRecord.date.desc()).limit(limit).all()
    return [{
        "id": r.id, "date": r.date, "subject": r.subject, "status": r.status,
        "marked_by_ai": r.marked_by_ai, "ai_confidence": r.ai_confidence,
        "verified": r.verified,
        "marked_at": r.marked_at.isoformat() if r.marked_at else None
    } for r in records]


@app.get("/api/student/monthly-trend")
def monthly_trend(current_user: User = Depends(require_role("student")),
                  db: Session = Depends(get_db)):
    records = db.query(AttendanceRecord).filter(
        AttendanceRecord.student_reg == current_user.id).all()
    monthly = {}
    for r in records:
        m = r.date[:7] if r.date else ""
        if not m: continue
        if m not in monthly:
            monthly[m] = {"present": 0, "total": 0}
        monthly[m]["total"] += 1
        if r.status in ("present", "late"):
            monthly[m]["present"] += 1
    return [{"month": m, "percentage": round(v["present"] / v["total"] * 100, 1) if v["total"] > 0 else 0,
             "present": v["present"], "total": v["total"]}
            for m in sorted(monthly.keys()) for v in [monthly[m]]]


@app.post("/api/student/leave")
def submit_leave(req: LeaveRequestModel,
                 current_user: User = Depends(require_role("student")),
                 db: Session = Depends(get_db)):
    leave = LeaveRequest(student_reg=current_user.id, from_date=req.from_date,
                         to_date=req.to_date, reason=req.reason, leave_type=req.leave_type)
    db.add(leave)
    db.commit()
    db.add(Notification(user_id="faculty001", icon="📝", title="Leave Request",
                        message=f"{current_user.name} submitted leave for {req.from_date} to {req.to_date}"))
    db.commit()
    return {"success": True, "id": leave.id}


@app.post("/api/student/dispute")
def raise_dispute(req: DisputeModel,
                  current_user: User = Depends(require_role("student")),
                  db: Session = Depends(get_db)):
    dispute = Dispute(student_reg=current_user.id, record_id=req.record_id,
                      subject=req.subject, date=req.date, claim=req.claim,
                      ai_confidence=random.uniform(30, 55))
    db.add(dispute)
    db.commit()
    db.add(Notification(user_id="admin001", icon="🚨", title="Dispute Raised",
                        message=f"{current_user.name} raised a dispute for {req.subject} on {req.date}"))
    db.commit()
    return {"success": True, "id": dispute.id}


# ── NOTIFICATIONS ─────────────────────────────────────────────────────────────
@app.get("/api/notifications")
def get_notifications(current_user: User = Depends(get_current_user),
                       db: Session = Depends(get_db)):
    notifs = db.query(Notification).filter(
        Notification.user_id == current_user.id
    ).order_by(Notification.created_at.desc()).limit(20).all()
    return [{"id": n.id, "title": n.title, "message": n.message, "icon": n.icon,
             "is_read": n.is_read, "created_at": n.created_at.isoformat()} for n in notifs]


@app.post("/api/notifications/{notif_id}/read")
def mark_read(notif_id: int, current_user: User = Depends(get_current_user),
              db: Session = Depends(get_db)):
    n = db.query(Notification).filter(Notification.id == notif_id,
                                       Notification.user_id == current_user.id).first()
    if n:
        n.is_read = True
        db.commit()
    return {"success": True}


# ── FACULTY ENDPOINTS ─────────────────────────────────────────────────────────
@app.get("/api/faculty/dashboard")
def faculty_dashboard(current_user: User = Depends(require_role("faculty")),
                       db: Session = Depends(get_db)):
    today = datetime.now().strftime("%Y-%m-%d")
    today_sessions = db.query(AttendanceSession).filter(
        AttendanceSession.faculty_id == current_user.id,
        AttendanceSession.date == today).all()
    all_records = db.query(AttendanceRecord).filter(
        AttendanceRecord.marked_by == current_user.id).all()

    students = db.query(Student).all()
    at_risk = []
    for student in students:
        records = db.query(AttendanceRecord).filter(
            AttendanceRecord.student_reg == student.reg_no).all()
        if not records: continue
        present = sum(1 for r in records if r.status in ("present", "late"))
        pct = round(present / len(records) * 100, 1)
        if pct < 75:
            at_risk.append({"reg_no": student.reg_no, "name": student.name,
                            "percentage": pct, "face_registered": student.face_registered})

    avg_att = 0
    if all_records:
        present_count = sum(1 for r in all_records if r.status in ("present", "late"))
        avg_att = round(present_count / len(all_records) * 100, 1)

    return {
        "today_sessions": len(today_sessions),
        "total_sessions": db.query(AttendanceSession).filter(
            AttendanceSession.faculty_id == current_user.id).count(),
        "avg_attendance": avg_att,
        "at_risk_students": at_risk,
        "pending_disputes": db.query(Dispute).filter(Dispute.status == "pending").count(),
        "face_engine_status": get_registration_stats()
    }


@app.get("/api/faculty/students")
def faculty_students(search: Optional[str] = None,
                     current_user: User = Depends(require_role("faculty")),
                     db: Session = Depends(get_db)):
    q = db.query(Student)
    if search:
        q = q.filter((Student.name.ilike(f"%{search}%")) |
                     (Student.reg_no.ilike(f"%{search}%")))
    students = q.all()
    result = []
    for s in students:
        records = db.query(AttendanceRecord).filter(
            AttendanceRecord.student_reg == s.reg_no).all()
        sub_stats = {}
        for r in records:
            if r.subject not in sub_stats:
                sub_stats[r.subject] = {"present": 0, "total": 0}
            sub_stats[r.subject]["total"] += 1
            if r.status in ("present", "late"):
                sub_stats[r.subject]["present"] += 1
        sub_pct = {sub: round(v["present"] / v["total"] * 100, 1) if v["total"] > 0 else 0
                   for sub, v in sub_stats.items()}
        overall = round(sum(sub_pct.values()) / len(sub_pct), 1) if sub_pct else 0
        result.append({
            "reg_no": s.reg_no, "name": s.name, "dept": s.dept,
            "semester": s.semester, "section": s.section,
            "face_registered": s.face_registered, "subjects": sub_pct, "overall": overall
        })
    return result


@app.post("/api/faculty/manual-mark")
def manual_mark(req: ManualMarkRequest,
                current_user: User = Depends(require_role("faculty")),
                db: Session = Depends(get_db)):
    existing = db.query(AttendanceRecord).filter(
        AttendanceRecord.student_reg == req.student_reg,
        AttendanceRecord.date == req.date,
        AttendanceRecord.subject == req.subject).first()
    if existing:
        existing.status = req.status
        existing.marked_by = current_user.id
        existing.marked_at = datetime.utcnow()
    else:
        db.add(AttendanceRecord(
            student_reg=req.student_reg, subject=req.subject, date=req.date,
            status=req.status, marked_by_ai=False, verified=True,
            marked_by=current_user.id))
    db.commit()
    log_action(db, current_user.id, current_user.name, "faculty",
               "Manual Mark", f"{req.student_reg} — {req.subject} — {req.status}")
    return {"success": True}


@app.get("/api/faculty/analytics")
def faculty_analytics(current_user: User = Depends(require_role("faculty")),
                       db: Session = Depends(get_db)):
    subjects = ["DSA", "Python", "English", "Networking", "System Designing"]
    subject_stats = {}
    for sub in subjects:
        recs = db.query(AttendanceRecord).filter(AttendanceRecord.subject == sub).all()
        if recs:
            p = sum(1 for r in recs if r.status in ("present", "late"))
            subject_stats[sub] = round(p / len(recs) * 100, 1)

    records = db.query(AttendanceRecord).all()
    monthly = {}
    for r in records:
        m = r.date[:7] if r.date else ""
        if not m: continue
        if m not in monthly:
            monthly[m] = {"present": 0, "total": 0}
        monthly[m]["total"] += 1
        if r.status in ("present", "late"):
            monthly[m]["present"] += 1
    monthly_trend = [{"month": m, "percentage": round(v["present"] / v["total"] * 100, 1)}
                     for m, v in sorted(monthly.items()) if v["total"] > 0]

    return {"subject_stats": subject_stats, "monthly_trend": monthly_trend}


# ── REPORTS ───────────────────────────────────────────────────────────────────
@app.get("/api/reports/attendance")
def report_attendance(format: str = "pdf", subject: Optional[str] = None,
                       date_from: Optional[str] = None, date_to: Optional[str] = None,
                       current_user: User = Depends(require_role("faculty", "admin")),
                       db: Session = Depends(get_db)):
    q = db.query(AttendanceRecord)
    if subject: q = q.filter(AttendanceRecord.subject == subject)
    if date_from: q = q.filter(AttendanceRecord.date >= date_from)
    if date_to: q = q.filter(AttendanceRecord.date <= date_to)
    records = q.order_by(AttendanceRecord.date.desc()).all()

    students_map = {s.reg_no: s.name for s in db.query(Student).all()}
    data = [{
        "Student": students_map.get(r.student_reg, r.student_reg),
        "Reg No": r.student_reg, "Date": r.date, "Subject": r.subject,
        "Status": r.status.upper(), "AI Marked": "Yes" if r.marked_by_ai else "No",
        "Confidence": f"{r.ai_confidence}%" if r.ai_confidence else "N/A"
    } for r in records]

    total = len(records)
    present = sum(1 for r in records if r.status in ("present", "late"))
    summary = {"Total": total, "Present": present, "Absent": total - present,
               "Attendance %": f"{round(present / total * 100, 1)}%" if total > 0 else "N/A"}

    title = f"Attendance Report — {subject or 'All Subjects'}"
    log_action(db, current_user.id, current_user.name, current_user.role,
               "Report Generated", f"{format.upper()} — {title}")

    if format == "csv":
        content = generate_attendance_csv(data)
        return Response(content=content, media_type="text/csv",
                        headers={"Content-Disposition": "attachment; filename=attendance.csv"})
    elif format == "excel":
        content = generate_attendance_excel(title, data, summary)
        return Response(content=content,
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": "attachment; filename=attendance.xlsx"})
    else:
        content = generate_attendance_pdf(title, data, summary)
        return Response(content=content, media_type="application/pdf",
                        headers={"Content-Disposition": "attachment; filename=attendance.pdf"})


# ── ADMIN ENDPOINTS ───────────────────────────────────────────────────────────
@app.get("/api/admin/dashboard")
def admin_dashboard(current_user: User = Depends(require_role("admin")),
                    db: Session = Depends(get_db)):
    all_records = db.query(AttendanceRecord).all()
    present = sum(1 for r in all_records if r.status in ("present", "late"))
    avg_att = round(present / len(all_records) * 100, 1) if all_records else 0

    at_risk = 0
    for s in db.query(Student).all():
        recs = [r for r in all_records if r.student_reg == s.reg_no]
        if recs and sum(1 for r in recs if r.status in ("present", "late")) / len(recs) * 100 < 75:
            at_risk += 1

    subjects = ["DSA", "Python", "English", "Networking", "System Designing"]
    subject_stats = {}
    for sub in subjects:
        recs = [r for r in all_records if r.subject == sub]
        subject_stats[sub] = round(
            sum(1 for r in recs if r.status in ("present", "late")) / len(recs) * 100, 1
        ) if recs else 0

    return {
        "total_students": db.query(Student).count(),
        "total_faculty": db.query(Faculty).count(),
        "active_sessions": db.query(AttendanceSession).filter(
            AttendanceSession.status == "active").count(),
        "pending_disputes": db.query(Dispute).filter(Dispute.status == "pending").count(),
        "avg_attendance": avg_att,
        "at_risk_students": at_risk,
        "subject_stats": subject_stats,
        "face_engine": get_registration_stats()
    }


@app.get("/api/admin/students")
def admin_students(search: Optional[str] = None,
                   current_user: User = Depends(require_role("admin")),
                   db: Session = Depends(get_db)):
    q = db.query(Student)
    if search:
        q = q.filter((Student.name.ilike(f"%{search}%")) |
                     (Student.reg_no.ilike(f"%{search}%")))
    students = q.all()
    all_records = db.query(AttendanceRecord).all()
    result = []
    for s in students:
        recs = [r for r in all_records if r.student_reg == s.reg_no]
        overall = round(
            sum(1 for r in recs if r.status in ("present", "late")) / len(recs) * 100, 1
        ) if recs else 0
        sub_stats = {}
        for r in recs:
            if r.subject not in sub_stats: sub_stats[r.subject] = {"present": 0, "total": 0}
            sub_stats[r.subject]["total"] += 1
            if r.status in ("present", "late"): sub_stats[r.subject]["present"] += 1
        sub_pct = {sub: round(v["present"] / v["total"] * 100, 1) if v["total"] > 0 else 0
                   for sub, v in sub_stats.items()}
        result.append({
            "reg_no": s.reg_no, "name": s.name, "dept": s.dept,
            "semester": s.semester, "section": s.section,
            "face_registered": s.face_registered, "subjects": sub_pct, "overall": overall
        })
    return result


@app.post("/api/admin/students")
def add_student(req: AddStudentRequest,
                current_user: User = Depends(require_role("admin")),
                db: Session = Depends(get_db)):
    if db.query(Student).filter(Student.reg_no == req.reg_no).first():
        raise HTTPException(400, "Student already exists")
    db.add(User(id=req.reg_no, name=req.name,
                password_hash=hash_password(req.password), role="student"))
    db.add(Student(reg_no=req.reg_no, name=req.name, dept=req.dept,
                   semester=req.semester, section=req.section, user_id=req.reg_no))
    db.commit()
    log_action(db, current_user.id, current_user.name, "admin",
               "Student Added", f"{req.name} ({req.reg_no})")
    return {"success": True}


@app.delete("/api/admin/students/{reg_no}")
def delete_student(reg_no: str, current_user: User = Depends(require_role("admin")),
                   db: Session = Depends(get_db)):
    s = db.query(Student).filter(Student.reg_no == reg_no).first()
    if not s: raise HTTPException(404, "Student not found")
    delete_face(reg_no)
    db.delete(s)
    db.commit()
    log_action(db, current_user.id, current_user.name, "admin", "Student Deleted", reg_no)
    return {"success": True}


@app.get("/api/admin/disputes")
def get_disputes(current_user: User = Depends(require_role("admin")),
                 db: Session = Depends(get_db)):
    disputes = db.query(Dispute).order_by(Dispute.created_at.desc()).all()
    students_map = {s.reg_no: s.name for s in db.query(Student).all()}
    return [{
        "id": d.id, "student_reg": d.student_reg,
        "student_name": students_map.get(d.student_reg, d.student_reg),
        "subject": d.subject, "date": d.date, "claim": d.claim,
        "ai_confidence": d.ai_confidence, "status": d.status,
        "resolution": d.resolution, "created_at": d.created_at.isoformat()
    } for d in disputes]


@app.post("/api/admin/disputes/{dispute_id}/resolve")
def resolve_dispute(dispute_id: int, action: str,
                    current_user: User = Depends(require_role("admin")),
                    db: Session = Depends(get_db)):
    dispute = db.query(Dispute).filter(Dispute.id == dispute_id).first()
    if not dispute: raise HTTPException(404, "Not found")
    dispute.status = "approved" if action == "approve" else "rejected"
    dispute.resolution = f"{'Approved' if action=='approve' else 'Rejected'} by Admin on {datetime.now().strftime('%Y-%m-%d')}"
    if action == "approve" and dispute.record_id:
        record = db.query(AttendanceRecord).filter(
            AttendanceRecord.id == dispute.record_id).first()
        if record:
            record.status = "present"
            record.verified = True
    db.add(Notification(
        user_id=dispute.student_reg, icon="✅" if action == "approve" else "❌",
        title=f"Dispute {'Approved' if action=='approve' else 'Rejected'}",
        message=f"Your dispute for {dispute.subject} on {dispute.date} has been {dispute.status}."))
    db.commit()
    log_action(db, current_user.id, current_user.name, "admin",
               f"Dispute {action.title()}d", f"Dispute {dispute_id}")
    return {"success": True}


@app.get("/api/admin/analytics")
def admin_analytics(current_user: User = Depends(require_role("admin")),
                    db: Session = Depends(get_db)):
    all_records = db.query(AttendanceRecord).all()
    subjects = ["DSA", "Python", "English", "Networking", "System Designing"]
    subject_stats = {}
    for sub in subjects:
        recs = [r for r in all_records if r.subject == sub]
        subject_stats[sub] = round(
            sum(1 for r in recs if r.status in ("present", "late")) / len(recs) * 100, 1
        ) if recs else 0

    monthly = {}
    for r in all_records:
        m = r.date[:7] if r.date else ""
        if not m: continue
        if m not in monthly: monthly[m] = {"present": 0, "total": 0}
        monthly[m]["total"] += 1
        if r.status in ("present", "late"): monthly[m]["present"] += 1
    monthly_trend = [{"month": m, "percentage": round(v["present"] / v["total"] * 100, 1)}
                     for m, v in sorted(monthly.items()) if v["total"] > 0]

    students = db.query(Student).all()
    risk_dist = {"safe": 0, "warning": 0, "critical": 0}
    for s in students:
        recs = [r for r in all_records if r.student_reg == s.reg_no]
        if not recs: continue
        pct = sum(1 for r in recs if r.status in ("present", "late")) / len(recs) * 100
        if pct >= 75: risk_dist["safe"] += 1
        elif pct >= 65: risk_dist["warning"] += 1
        else: risk_dist["critical"] += 1

    return {
        "subject_stats": subject_stats, "monthly_trend": monthly_trend,
        "risk_distribution": risk_dist,
        "total_sessions": db.query(AttendanceSession).count(),
        "total_records": len(all_records)
    }


@app.get("/api/admin/audit-logs")
def audit_logs(current_user: User = Depends(require_role("admin")),
               db: Session = Depends(get_db)):
    logs = db.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(50).all()
    return [{"id": l.id, "user_id": l.user_id, "user_name": l.user_name,
             "role": l.role, "action": l.action, "details": l.details,
             "created_at": l.created_at.isoformat()} for l in logs]


@app.get("/api/admin/attendance-records")
def all_attendance(subject: Optional[str] = None, date: Optional[str] = None,
                   current_user: User = Depends(require_role("admin")),
                   db: Session = Depends(get_db)):
    q = db.query(AttendanceRecord)
    if subject: q = q.filter(AttendanceRecord.subject == subject)
    if date: q = q.filter(AttendanceRecord.date == date)
    records = q.order_by(AttendanceRecord.date.desc()).limit(100).all()
    students_map = {s.reg_no: s.name for s in db.query(Student).all()}
    return [{
        "id": r.id, "student_reg": r.student_reg,
        "student_name": students_map.get(r.student_reg, r.student_reg),
        "subject": r.subject, "date": r.date, "status": r.status,
        "marked_by_ai": r.marked_by_ai, "ai_confidence": r.ai_confidence, "verified": r.verified
    } for r in records]


@app.put("/api/admin/attendance-records/{record_id}")
def update_record(record_id: int, status: str,
                  current_user: User = Depends(require_role("admin")),
                  db: Session = Depends(get_db)):
    r = db.query(AttendanceRecord).filter(AttendanceRecord.id == record_id).first()
    if not r: raise HTTPException(404, "Not found")
    r.status = status
    db.commit()
    log_action(db, current_user.id, current_user.name, "admin",
               "Record Updated", f"Record {record_id} set to {status}")
    return {"success": True}


@app.get("/api/health")
def health():
    stats = get_registration_stats()
    return {
        "status": "healthy",
        "version": "3.0.0",
        "face_engine": "OpenCV LBPH Real Recognition",
        "registered_students": stats["total_registered"],
        "timestamp": datetime.now().isoformat()
    }


@app.post("/api/auth/refresh")
def refresh_token(current_user: User = Depends(get_current_user)):
    """
    Refresh access token for current user
    Useful when token is about to expire
    """
    new_token = create_access_token({
        "sub": current_user.id,
        "role": current_user.role,
        "name": current_user.name
    })
    
    logger.info(f"Token refreshed for user {current_user.id}")
    
    return {
        "access_token": new_token,
        "token_type": "bearer",
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_HOURS * 3600,
        "user": {
            "id": current_user.id,
            "name": current_user.name,
            "role": current_user.role
        }
    }


@app.post("/api/auth/verify")
def verify_token(current_user: User = Depends(get_current_user)):
    """
    Verify if current token is valid
    Returns user info if valid, 401 if invalid/expired
    """
    return {
        "valid": True,
        "user": {
            "id": current_user.id,
            "name": current_user.name,
            "role": current_user.role,
            "last_login": current_user.last_login.isoformat() if current_user.last_login else None
        }
    }

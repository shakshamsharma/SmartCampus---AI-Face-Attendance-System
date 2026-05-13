"""
Real-Time Attendance API Endpoints
WebSocket-based live face tracking and recognition
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Dict, Optional
import json
import logging
import asyncio
from datetime import datetime

from database import get_db, Student, AttendanceSession, User
from auth import get_current_user, require_role
from face_engine_realtime import get_engine

logger = logging.getLogger(__name__)

router = APIRouter()

# Active WebSocket sessions
active_sessions: Dict[int, Dict] = {}


@router.websocket("/ws/realtime-scan/{session_id}")
async def realtime_scan_websocket(
    websocket: WebSocket,
    session_id: int,
    token: Optional[str] = None
):
    """
    Real-time face recognition WebSocket
    
    Client sends: {"type": "frame", "frame": "base64_image"}
    Server responds: {"type": "update", "data": {...recognition_state...}}
    """
    await websocket.accept()
    
    try:
        # Verify token (simplified - in production, decode JWT properly)
        if not token:
            await websocket.send_json({
                "type": "error",
                "message": "Authentication required"
            })
            await websocket.close()
            return
        
        logger.info(f"Real-time scan WebSocket opened for session {session_id}")
        
        # Get engine
        engine = get_engine()
        
        # Initialize session if not already active
        if session_id not in active_sessions:
            # Get student list from database (simplified)
            # In production, get from database based on session
            student_names = {
                "2023CSE001": "Saksham Sharma",
                "2023CSE002": "Ashish Chandel",
                "2023CSE003": "Ashutosh Sharma",
                "2023CSE004": "Vishal Thakur"
            }
            
            engine.start_session(student_names)
            active_sessions[session_id] = {
                "started_at": datetime.now(),
                "frame_count": 0
            }
            
            await websocket.send_json({
                "type": "session_started",
                "session_id": session_id,
                "students": student_names
            })
        
        # Main loop - process frames
        while True:
            # Receive message
            data = await websocket.receive_text()
            message = json.loads(data)
            
            if message.get("type") == "frame":
                # Process frame
                frame_b64 = message.get("frame")
                
                if frame_b64:
                    # Process with real-time engine
                    result = engine.process_frame(frame_b64)
                    
                    # Update frame count
                    active_sessions[session_id]["frame_count"] += 1
                    
                    # Send result back to client
                    await websocket.send_json({
                        "type": "update",
                        "data": result,
                        "frame_count": active_sessions[session_id]["frame_count"]
                    })
            
            elif message.get("type") == "get_final":
                # Get final attendance summary
                final = engine.get_final_attendance()
                
                await websocket.send_json({
                    "type": "final_result",
                    "data": final
                })
            
            elif message.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
            
            elif message.get("type") == "close":
                break
    
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for session {session_id}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        try:
            await websocket.send_json({
                "type": "error",
                "message": str(e)
            })
        except:
            pass
    finally:
        # Cleanup
        if session_id in active_sessions:
            del active_sessions[session_id]
        logger.info(f"WebSocket closed for session {session_id}")


@router.post("/api/faculty/session/start-realtime")
async def start_realtime_session(
    subject: str,
    dept: str = "CSE",
    semester: int = 6,
    section: str = "A",
    current_user: User = Depends(require_role("faculty")),
    db: Session = Depends(get_db)
):
    """
    Start a real-time attendance session
    Returns session_id and WebSocket URL
    """
    from database import AttendanceSession
    
    today = datetime.now().strftime("%Y-%m-%d")
    
    # Create session
    session = AttendanceSession(
        faculty_id=current_user.id,
        subject=subject,
        dept=dept,
        semester=semester,
        section=section,
        date=today,
        status="active",
        total_students=4  # TODO: Get from database
    )
    db.add(session)
    db.commit()
    
    # Get students for this class
    students = db.query(Student).filter(
        Student.dept == dept,
        Student.semester == semester,
        Student.section == section
    ).all()
    
    student_list = [
        {
            "reg_no": s.reg_no,
            "name": s.name,
            "face_registered": s.face_registered
        }
        for s in students
    ]
    
    logger.info(f"Started real-time session {session.id} for {subject}")
    
    return {
        "session_id": session.id,
        "subject": subject,
        "date": today,
        "students": student_list,
        "websocket_url": f"/ws/realtime-scan/{session.id}",
        "message": "Connect to WebSocket to start real-time scanning"
    }


@router.post("/api/faculty/session/end-realtime/{session_id}")
async def end_realtime_session(
    session_id: int,
    current_user: User = Depends(require_role("faculty")),
    db: Session = Depends(get_db)
):
    """
    End real-time session and save final attendance
    """
    from database import AttendanceSession, AttendanceRecord, Notification
    
    # Get session
    session = db.query(AttendanceSession).filter(
        AttendanceSession.id == session_id
    ).first()
    
    if not session:
        raise HTTPException(404, "Session not found")
    
    # Get final attendance from engine
    engine = get_engine()
    final = engine.get_final_attendance()
    
    # Update session
    session.status = "ended"
    session.ended_at = datetime.utcnow()
    session.total_present = final["total_confirmed"]
    
    # Save attendance records
    today = datetime.now().strftime("%Y-%m-%d")
    
    for student in final["detected"]:
        # Check if record exists
        existing = db.query(AttendanceRecord).filter(
            AttendanceRecord.session_id == session_id,
            AttendanceRecord.student_reg == student["reg_no"]
        ).first()
        
        if not existing:
            record = AttendanceRecord(
                session_id=session_id,
                student_reg=student["reg_no"],
                subject=session.subject,
                date=today,
                status="present",
                marked_by_ai=True,
                ai_confidence=student["confidence"],
                verified=True,
                marked_by=current_user.id
            )
            db.add(record)
            
            # Notify student
            db.add(Notification(
                user_id=student["reg_no"],
                icon="✅",
                title=f"Attendance Marked — {session.subject}",
                message=f"You were recognized and marked present (confidence: {student['confidence']}%)"
            ))
    
    for student in final["not_detected"]:
        existing = db.query(AttendanceRecord).filter(
            AttendanceRecord.session_id == session_id,
            AttendanceRecord.student_reg == student["reg_no"]
        ).first()
        
        if not existing:
            record = AttendanceRecord(
                session_id=session_id,
                student_reg=student["reg_no"],
                subject=session.subject,
                date=today,
                status="absent",
                marked_by_ai=False,
                verified=True,
                marked_by=current_user.id
            )
            db.add(record)
            
            # Notify student
            db.add(Notification(
                user_id=student["reg_no"],
                icon="❌",
                title=f"Marked Absent — {session.subject}",
                message=f"You were not detected in class. Raise a dispute if incorrect."
            ))
    
    db.commit()
    
    logger.info(f"Ended real-time session {session_id}: {final['total_confirmed']} present, {final['total_absent']} absent")
    
    return {
        "success": True,
        "session_id": session_id,
        "present": final["total_confirmed"],
        "absent": final["total_absent"],
        "total": final["total_confirmed"] + final["total_absent"],
        "session_duration": final["session_duration"]
    }

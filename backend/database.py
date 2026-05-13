from sqlalchemy import create_engine, Column, String, Integer, Float, Boolean, Text, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime

DATABASE_URL = "sqlite:///./smartcampus.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=False)
    email = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime)

class Student(Base):
    __tablename__ = "students"
    reg_no = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    dept = Column(String, default="CSE")
    semester = Column(Integer, default=6)
    section = Column(String, default="A")
    face_registered = Column(Boolean, default=False)
    face_embeddings = Column(Text)
    face_registered_at = Column(DateTime)
    user_id = Column(String, ForeignKey("users.id"))

class Faculty(Base):
    __tablename__ = "faculty"
    faculty_id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    dept = Column(String, default="CSE")
    subjects = Column(Text)
    user_id = Column(String, ForeignKey("users.id"))

class AttendanceSession(Base):
    __tablename__ = "attendance_sessions"
    id = Column(Integer, primary_key=True, autoincrement=True)
    faculty_id = Column(String)
    subject = Column(String, nullable=False)
    dept = Column(String)
    semester = Column(Integer)
    section = Column(String)
    date = Column(String, nullable=False)
    period = Column(String)
    started_at = Column(DateTime, default=datetime.utcnow)
    ended_at = Column(DateTime)
    status = Column(String, default="active")
    total_present = Column(Integer, default=0)
    total_students = Column(Integer, default=0)

class AttendanceRecord(Base):
    __tablename__ = "attendance_records"
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, ForeignKey("attendance_sessions.id"))
    student_reg = Column(String, ForeignKey("students.reg_no"))
    subject = Column(String)
    date = Column(String)
    status = Column(String, default="present")
    marked_by_ai = Column(Boolean, default=False)
    ai_confidence = Column(Float)
    verified = Column(Boolean, default=False)
    marked_at = Column(DateTime, default=datetime.utcnow)
    marked_by = Column(String)

class Notification(Base):
    __tablename__ = "notifications"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String)
    title = Column(String)
    message = Column(String)
    icon = Column(String, default="📢")
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class LeaveRequest(Base):
    __tablename__ = "leave_requests"
    id = Column(Integer, primary_key=True, autoincrement=True)
    student_reg = Column(String)
    from_date = Column(String)
    to_date = Column(String)
    reason = Column(Text)
    leave_type = Column(String)
    status = Column(String, default="pending")
    created_at = Column(DateTime, default=datetime.utcnow)

class Dispute(Base):
    __tablename__ = "disputes"
    id = Column(Integer, primary_key=True, autoincrement=True)
    student_reg = Column(String)
    record_id = Column(Integer)
    subject = Column(String)
    date = Column(String)
    claim = Column(Text)
    ai_confidence = Column(Float)
    status = Column(String, default="pending")
    resolution = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

class UnknownFaceAlert(Base):
    __tablename__ = "unknown_face_alerts"
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, ForeignKey("attendance_sessions.id"))
    alert_id = Column(String, unique=True)
    snapshot_path = Column(String)
    snapshot_b64 = Column(Text)
    confidence = Column(Float)
    distance = Column(Float)
    closest_match = Column(String)
    face_location = Column(Text)  # JSON string
    alert_time = Column(DateTime, default=datetime.utcnow)
    is_read = Column(Boolean, default=False)
    notes = Column(Text)
    resolved = Column(Boolean, default=False)

class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String)
    user_name = Column(String)
    role = Column(String)
    action = Column(String)
    details = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    Base.metadata.create_all(bind=engine)

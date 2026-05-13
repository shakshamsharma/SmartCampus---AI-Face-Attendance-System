import json
from datetime import datetime, timedelta
import random
from database import SessionLocal, init_db, User, Student, Faculty, AttendanceSession, AttendanceRecord, Notification, AuditLog
from auth import hash_password

def seed(force=False):
    """
    PRODUCTION MODE: Seed function disabled by default.
    Only initializes database schema, does NOT add demo data.
    
    To add demo data for testing, run: python seed.py --demo
    """
    init_db()
    db = SessionLocal()
    
    # Check if already seeded
    if db.query(User).count() > 0 and not force:
        # Database already has users, skip seeding
        db.close()
        return
    
    # PRODUCTION MODE: Do not seed demo data automatically
    # Database schema is initialized, but no demo data is added
    # This prevents demo data from appearing in production
    db.close()
    return
    
    # ═══════════════════════════════════════════════════════════════
    # DEMO DATA SECTION (DISABLED IN PRODUCTION)
    # ═══════════════════════════════════════════════════════════════
    # The code below is kept for reference but will not execute
    # To enable demo data, remove the return statement above
    # ═══════════════════════════════════════════════════════════════
    
    # Clear existing data if force re-seed
    if force:
        print("Force re-seeding: Clearing existing data...")
        db.query(AuditLog).delete()
        db.query(Notification).delete()
        db.query(AttendanceRecord).delete()
        db.query(AttendanceSession).delete()
        db.query(Faculty).delete()
        db.query(Student).delete()
        db.query(User).delete()
        db.commit()
    
    print("Seeding database with argon2 password hashes...")
    
    # Admin
    db.add(User(id="admin001", name="Saksham Sharma", password_hash=hash_password("password123"), role="admin", email="admin@smartcampus.edu"))
    
    # Faculty
    db.add(User(id="faculty001", name="Blake Blossom", password_hash=hash_password("password123"), role="faculty", email="blake@smartcampus.edu"))
    db.add(Faculty(faculty_id="faculty001", name="Blake Blossom", dept="CSE", subjects=json.dumps(["DSA", "Python", "English", "Networking", "System Designing"]), user_id="faculty001"))
    
    # Students
    students_data = [
        ("2023CSE001", "Saksham Sharma", {"DSA":82,"Python":77,"English":68,"Networking":90,"System Designing":74}),
        ("2023CSE002", "Ashish Chandel", {"DSA":88,"Python":65,"English":72,"Networking":85,"System Designing":90}),
        ("2023CSE003", "Ashutosh Sharma", {"DSA":60,"Python":70,"English":78,"Networking":65,"System Designing":55}),
        ("2023CSE004", "Vishal Thakur", {"DSA":95,"Python":92,"English":88,"Networking":91,"System Designing":94}),
    ]
    
    for reg_no, name, att in students_data:
        db.add(User(id=reg_no, name=name, password_hash=hash_password("password123"), role="student"))
        db.add(Student(reg_no=reg_no, name=name, dept="CSE", semester=6, section="A", face_registered=(reg_no!="2023CSE003"), user_id=reg_no))
    
    db.commit()
    
    # Create attendance sessions and records (last 30 days)
    subjects = ["DSA", "Python", "English", "Networking", "System Designing"]
    student_regs = ["2023CSE001", "2023CSE002", "2023CSE003", "2023CSE004"]
    student_attendance = {s[0]: s[2] for s in students_data}
    
    session_id = 1
    today = datetime.now()
    
    for days_ago in range(30, 0, -1):
        dt = today - timedelta(days=days_ago)
        if dt.weekday() >= 5:  # skip weekend
            continue
        date_str = dt.strftime("%Y-%m-%d")
        
        for i, subject in enumerate(subjects):
            # Create session
            sess = AttendanceSession(
                id=session_id, faculty_id="faculty001", subject=subject,
                dept="CSE", semester=6, section="A", date=date_str,
                period=f"{i+1}st", started_at=dt.replace(hour=9+i*2),
                ended_at=dt.replace(hour=10+i*2), status="ended",
                total_students=4
            )
            
            present_count = 0
            for reg_no in student_regs:
                target_pct = student_attendance[reg_no][subject]
                # Simulate attendance based on target %
                is_present = random.random() * 100 < target_pct
                status = "present" if is_present else "absent"
                if is_present and random.random() < 0.1:
                    status = "late"
                if is_present:
                    present_count += 1
                
                db.add(AttendanceRecord(
                    session_id=session_id, student_reg=reg_no, subject=subject,
                    date=date_str, status=status, marked_by_ai=is_present,
                    ai_confidence=round(85 + random.random()*14, 1) if is_present else None,
                    verified=is_present, marked_by="faculty001"
                ))
            
            sess.total_present = present_count
            db.add(sess)
            session_id += 1
    
    db.commit()
    
    # Notifications
    notifs = [
        ("2023CSE001", "📊", "Attendance marked in DSA", "Your attendance has been recorded for today's DSA class"),
        ("2023CSE001", "⚠️", "Low attendance warning", "You are below 75% in English. Please attend upcoming classes."),
        ("2023CSE001", "📅", "Tomorrow's schedule", "First lecture at 9:00 AM - DSA in CS-101"),
        ("faculty001", "⏰", "Session reminder", "DSA session starts in 10 minutes"),
        ("faculty001", "📄", "Report generated", "Monthly attendance report is ready to download"),
        ("admin001", "🚨", "Dispute raised", "Saksham Sharma raised an attendance dispute for English"),
        ("admin001", "🔍", "Anomaly detected", "Multiple unknown faces detected in CS-301"),
    ]
    for uid, icon, title, msg in notifs:
        db.add(Notification(user_id=uid, icon=icon, title=title, message=msg))
    
    # Audit logs
    logs = [
        ("faculty001", "Blake Blossom", "faculty", "Session Started", "DSA — 6th Sem A"),
        ("2023CSE001", "Saksham Sharma", "student", "Login", "Successful login"),
        ("admin001", "Saksham Sharma", "admin", "Record Edited", "Updated English attendance for Ashutosh"),
        ("faculty001", "Blake Blossom", "faculty", "Report Generated", "Monthly PDF report for CSE"),
    ]
    for uid, name, role, action, details in logs:
        db.add(AuditLog(user_id=uid, user_name=name, role=role, action=action, details=details))
    
    db.commit()
    db.close()
    print("✅ Database seeded successfully!")

if __name__ == "__main__":
    seed()

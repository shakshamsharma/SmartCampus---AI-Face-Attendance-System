"""
Attendance Actions - Real Database Integration
Implements attendance-related AI functions with actual database queries
"""
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

def get_attendance(
    student_id: str,
    subject: Optional[str] = None,
    db: Session = None
) -> Dict[str, Any]:
    """
    Get real attendance from database
    
    Args:
        student_id: Student registration number
        subject: Optional subject filter
        db: Database session
    
    Returns:
        Attendance data dict
    """
    if not db:
        return {"success": False, "error": "Database session not provided"}
    
    try:
        from database import AttendanceRecord, Student
        
        # Get student info
        student = db.query(Student).filter(Student.reg_no == student_id).first()
        if not student:
            return {"success": False, "error": f"Student {student_id} not found"}
        
        # Query attendance records
        query = db.query(AttendanceRecord).filter(
            AttendanceRecord.student_reg == student_id
        )
        
        if subject:
            query = query.filter(AttendanceRecord.subject == subject)
        
        records = query.all()
        
        if not records:
            return {
                "success": True,
                "overall_percentage": 0,
                "total_classes": 0,
                "present": 0,
                "absent": 0,
                "subjects": {},
                "message": "No attendance records found"
            }
        
        # Calculate overall statistics
        total = len(records)
        present = sum(1 for r in records if r.status in ("present", "late"))
        absent = total - present
        percentage = (present / total * 100) if total > 0 else 0
        
        # Group by subject
        subjects = {}
        for record in records:
            if record.subject not in subjects:
                subjects[record.subject] = {"present": 0, "total": 0, "absent": 0, "late": 0}
            subjects[record.subject]["total"] += 1
            if record.status == "present":
                subjects[record.subject]["present"] += 1
            elif record.status == "late":
                subjects[record.subject]["late"] += 1
                subjects[record.subject]["present"] += 1  # Late counts as present
            else:
                subjects[record.subject]["absent"] += 1
        
        # Calculate subject percentages
        for subj, data in subjects.items():
            data["percentage"] = round((data["present"] / data["total"] * 100), 1) if data["total"] > 0 else 0
        
        logger.info(f"Attendance retrieved for {student_id}: {percentage:.1f}%")
        
        return {
            "success": True,
            "student_id": student_id,
            "student_name": student.name,
            "overall_percentage": round(percentage, 1),
            "total_classes": total,
            "present": present,
            "absent": absent,
            "subjects": subjects
        }
        
    except Exception as e:
        logger.error(f"Error getting attendance: {e}")
        return {"success": False, "error": str(e)}


def predict_attendance(
    student_id: str,
    days_ahead: int = 14,
    db: Session = None
) -> Dict[str, Any]:
    """
    Predict future attendance using linear regression
    
    Args:
        student_id: Student registration number
        days_ahead: Number of days to predict ahead
        db: Database session
    
    Returns:
        Prediction data dict
    """
    if not db:
        return {"success": False, "error": "Database session not provided"}
    
    try:
        from database import AttendanceRecord
        
        # Get historical data (last 30 days)
        thirty_days_ago = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        
        records = db.query(AttendanceRecord).filter(
            AttendanceRecord.student_reg == student_id,
            AttendanceRecord.date >= thirty_days_ago
        ).order_by(AttendanceRecord.date).all()
        
        if len(records) < 5:
            return {
                "success": False,
                "error": "Not enough data for prediction (need at least 5 records)"
            }
        
        # Calculate cumulative attendance percentages
        dates = []
        percentages = []
        
        for i in range(len(records)):
            subset = records[:i+1]
            present = sum(1 for r in subset if r.status in ("present", "late"))
            pct = (present / len(subset) * 100) if subset else 0
            percentages.append(pct)
            
            # Calculate days from start
            date_obj = datetime.strptime(records[i].date, "%Y-%m-%d")
            start_date = datetime.strptime(records[0].date, "%Y-%m-%d")
            days_diff = (date_obj - start_date).days
            dates.append(days_diff)
        
        # Simple linear regression
        n = len(dates)
        sum_x = sum(dates)
        sum_y = sum(percentages)
        sum_xy = sum(x * y for x, y in zip(dates, percentages))
        sum_x2 = sum(x * x for x in dates)
        
        # Calculate slope and intercept
        if (n * sum_x2 - sum_x * sum_x) == 0:
            slope = 0
        else:
            slope = (n * sum_xy - sum_x * sum_y) / (n * sum_x2 - sum_x * sum_x)
        intercept = (sum_y - slope * sum_x) / n
        
        # Predict future
        future_day = dates[-1] + days_ahead
        predicted = slope * future_day + intercept
        predicted = max(0, min(100, predicted))  # Clamp to 0-100
        
        current = percentages[-1]
        
        # Determine risk level
        if predicted < 75:
            risk = "high"
            classes_needed = int((75 * len(records) - sum(1 for r in records if r.status in ("present", "late"))) / (1 - 0.75))
            recommendation = f"⚠️ URGENT: Attend all classes in next {days_ahead} days to avoid falling below 75%. You need {classes_needed} more present classes."
        elif predicted < 80:
            risk = "medium"
            classes_needed = int((80 * len(records) - sum(1 for r in records if r.status in ("present", "late"))) / (1 - 0.80))
            recommendation = f"⚠️ Attend next {classes_needed} classes to maintain safe margin above 75%."
        else:
            risk = "low"
            recommendation = "✅ You're on track. Keep attending regularly to maintain good attendance."
        
        logger.info(f"Attendance prediction for {student_id}: {current:.1f}% → {predicted:.1f}% (risk: {risk})")
        
        return {
            "success": True,
            "student_id": student_id,
            "current_percentage": round(current, 1),
            "predicted_percentage": round(predicted, 1),
            "days_ahead": days_ahead,
            "risk_level": risk,
            "trend": "increasing" if predicted > current else "decreasing" if predicted < current else "stable",
            "recommendation": recommendation,
            "data_points": len(records)
        }
        
    except Exception as e:
        logger.error(f"Error predicting attendance: {e}")
        return {"success": False, "error": str(e)}


def get_subject_attendance(
    student_id: str,
    subject: str,
    db: Session = None
) -> Dict[str, Any]:
    """
    Get detailed attendance for specific subject
    
    Args:
        student_id: Student registration number
        subject: Subject name
        db: Database session
    
    Returns:
        Subject attendance data
    """
    if not db:
        return {"success": False, "error": "Database session not provided"}
    
    try:
        from database import AttendanceRecord
        
        records = db.query(AttendanceRecord).filter(
            AttendanceRecord.student_reg == student_id,
            AttendanceRecord.subject == subject
        ).order_by(AttendanceRecord.date.desc()).all()
        
        if not records:
            return {
                "success": False,
                "error": f"No attendance records found for {subject}"
            }
        
        total = len(records)
        present = sum(1 for r in records if r.status in ("present", "late"))
        absent = total - present
        late = sum(1 for r in records if r.status == "late")
        percentage = (present / total * 100) if total > 0 else 0
        
        # Get absent dates
        absent_dates = [r.date for r in records if r.status == "absent"]
        
        # Get recent records
        recent_records = [
            {
                "date": r.date,
                "status": r.status,
                "marked_by_ai": r.marked_by_ai,
                "verified": r.verified
            }
            for r in records[:10]  # Last 10 records
        ]
        
        logger.info(f"Subject attendance for {student_id} in {subject}: {percentage:.1f}%")
        
        return {
            "success": True,
            "student_id": student_id,
            "subject": subject,
            "percentage": round(percentage, 1),
            "present": present,
            "absent": absent,
            "late": late,
            "total": total,
            "absent_dates": absent_dates,
            "recent_records": recent_records
        }
        
    except Exception as e:
        logger.error(f"Error getting subject attendance: {e}")
        return {"success": False, "error": str(e)}


def check_eligibility(
    student_id: str,
    db: Session = None
) -> Dict[str, Any]:
    """
    Check if student is eligible for exams (75% attendance required)
    
    Args:
        student_id: Student registration number
        db: Database session
    
    Returns:
        Eligibility data
    """
    if not db:
        return {"success": False, "error": "Database session not provided"}
    
    try:
        # Get overall attendance
        attendance_data = get_attendance(student_id, db=db)
        
        if not attendance_data.get("success"):
            return attendance_data
        
        overall_pct = attendance_data.get("overall_percentage", 0)
        eligible = overall_pct >= 75
        
        # Check subject-wise eligibility
        subjects = attendance_data.get("subjects", {})
        ineligible_subjects = []
        
        for subject, stats in subjects.items():
            if stats.get("percentage", 0) < 75:
                ineligible_subjects.append({
                    "subject": subject,
                    "percentage": stats.get("percentage", 0),
                    "classes_needed": int((75 * stats.get("total", 0) - stats.get("present", 0)) / (1 - 0.75))
                })
        
        if eligible and not ineligible_subjects:
            message = f"✅ You are eligible for exams with {overall_pct}% attendance."
        elif not eligible:
            classes_needed = int((75 * attendance_data.get("total_classes", 0) - attendance_data.get("present", 0)) / (1 - 0.75))
            message = f"❌ You are NOT eligible for exams. Current attendance: {overall_pct}%. You need {classes_needed} more present classes to reach 75%."
        else:
            message = f"⚠️ Overall eligible ({overall_pct}%), but ineligible in {len(ineligible_subjects)} subject(s)."
        
        logger.info(f"Eligibility check for {student_id}: {eligible} ({overall_pct:.1f}%)")
        
        return {
            "success": True,
            "student_id": student_id,
            "eligible": eligible,
            "overall_percentage": overall_pct,
            "required_percentage": 75,
            "ineligible_subjects": ineligible_subjects,
            "message": message
        }
        
    except Exception as e:
        logger.error(f"Error checking eligibility: {e}")
        return {"success": False, "error": str(e)}


def get_low_attendance_students(
    threshold: float = 75,
    subject: Optional[str] = None,
    db: Session = None
) -> Dict[str, Any]:
    """
    Get list of students with attendance below threshold (for faculty/admin)
    
    Args:
        threshold: Attendance percentage threshold
        subject: Optional subject filter
        db: Database session
    
    Returns:
        List of low attendance students
    """
    if not db:
        return {"success": False, "error": "Database session not provided"}
    
    try:
        from database import Student, AttendanceRecord
        
        all_students = db.query(Student).all()
        low_attendance_students = []
        
        for student in all_students:
            # Get attendance for this student
            query = db.query(AttendanceRecord).filter(
                AttendanceRecord.student_reg == student.reg_no
            )
            
            if subject:
                query = query.filter(AttendanceRecord.subject == subject)
            
            records = query.all()
            
            if not records:
                continue
            
            present = sum(1 for r in records if r.status in ("present", "late"))
            total = len(records)
            percentage = (present / total * 100) if total > 0 else 0
            
            if percentage < threshold:
                low_attendance_students.append({
                    "reg_no": student.reg_no,
                    "name": student.name,
                    "dept": student.dept,
                    "semester": student.semester,
                    "percentage": round(percentage, 1),
                    "present": present,
                    "total": total,
                    "absent": total - present,
                    "face_registered": student.face_registered
                })
        
        # Sort by percentage (lowest first)
        low_attendance_students.sort(key=lambda x: x["percentage"])
        
        logger.info(f"Found {len(low_attendance_students)} students below {threshold}%")
        
        return {
            "success": True,
            "threshold": threshold,
            "subject": subject,
            "count": len(low_attendance_students),
            "students": low_attendance_students
        }
        
    except Exception as e:
        logger.error(f"Error getting low attendance students: {e}")
        return {"success": False, "error": str(e)}

"""
Leave Actions - Real Database Integration
Implements leave management AI functions with actual database queries
"""
import logging
from typing import Dict, Any, Optional
from datetime import datetime
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

def apply_leave(
    student_id: str,
    from_date: str,
    to_date: str,
    reason: str,
    leave_type: str = "personal",
    db: Session = None
) -> Dict[str, Any]:
    """
    Apply for leave with real database insertion
    
    Args:
        student_id: Student registration number
        from_date: Start date (YYYY-MM-DD)
        to_date: End date (YYYY-MM-DD)
        reason: Reason for leave
        leave_type: Type of leave (sick, personal, emergency)
        db: Database session
    
    Returns:
        Leave application result
    """
    if not db:
        return {"success": False, "error": "Database session not provided"}
    
    try:
        from database import LeaveRequest, Notification, Student
        
        # Get student info
        student = db.query(Student).filter(Student.reg_no == student_id).first()
        if not student:
            return {"success": False, "error": f"Student {student_id} not found"}
        
        # Validate dates
        try:
            from_date_obj = datetime.strptime(from_date, "%Y-%m-%d")
            to_date_obj = datetime.strptime(to_date, "%Y-%m-%d")
            
            if to_date_obj < from_date_obj:
                return {"success": False, "error": "End date cannot be before start date"}
            
            if from_date_obj < datetime.now():
                return {"success": False, "error": "Cannot apply leave for past dates"}
            
        except ValueError:
            return {"success": False, "error": "Invalid date format. Use YYYY-MM-DD"}
        
        # Create leave request
        leave = LeaveRequest(
            student_reg=student_id,
            from_date=from_date,
            to_date=to_date,
            reason=reason,
            leave_type=leave_type,
            status="pending",
            created_at=datetime.now()
        )
        
        db.add(leave)
        db.commit()
        db.refresh(leave)
        
        # Send notification to faculty (get first faculty for now)
        from database import Faculty
        faculty = db.query(Faculty).first()
        if faculty:
            db.add(Notification(
                user_id=faculty.faculty_id,
                title="📝 New Leave Request",
                message=f"{student.name} ({student_id}) requested leave from {from_date} to {to_date}. Reason: {reason}",
                icon="📝",
                created_at=datetime.now()
            ))
        
        # Send confirmation to student
        db.add(Notification(
            user_id=student_id,
            title="✅ Leave Application Submitted",
            message=f"Your leave request for {from_date} to {to_date} has been submitted and is pending approval.",
            icon="✅",
            created_at=datetime.now()
        ))
        
        db.commit()
        
        logger.info(f"Leave application created: ID={leave.id}, Student={student_id}, Dates={from_date} to {to_date}")
        
        return {
            "success": True,
            "leave_id": leave.id,
            "student_id": student_id,
            "student_name": student.name,
            "from_date": from_date,
            "to_date": to_date,
            "reason": reason,
            "leave_type": leave_type,
            "status": "pending",
            "message": f"Leave application submitted successfully for {from_date} to {to_date}. Status: Pending approval."
        }
        
    except Exception as e:
        logger.error(f"Error applying leave: {e}")
        db.rollback()
        return {"success": False, "error": str(e)}


def get_leave_requests(
    student_id: Optional[str] = None,
    status: Optional[str] = None,
    db: Session = None
) -> Dict[str, Any]:
    """
    Get leave requests (for student or faculty)
    
    Args:
        student_id: Optional student ID filter
        status: Optional status filter (pending, approved, rejected)
        db: Database session
    
    Returns:
        List of leave requests
    """
    if not db:
        return {"success": False, "error": "Database session not provided"}
    
    try:
        from database import LeaveRequest, Student
        
        query = db.query(LeaveRequest)
        
        if student_id:
            query = query.filter(LeaveRequest.student_reg == student_id)
        
        if status:
            query = query.filter(LeaveRequest.status == status)
        
        requests = query.order_by(LeaveRequest.created_at.desc()).all()
        
        result = []
        for req in requests:
            student = db.query(Student).filter(Student.reg_no == req.student_reg).first()
            result.append({
                "id": req.id,
                "student_reg": req.student_reg,
                "student_name": student.name if student else req.student_reg,
                "from_date": req.from_date,
                "to_date": req.to_date,
                "reason": req.reason,
                "leave_type": req.leave_type,
                "status": req.status,
                "created_at": req.created_at.isoformat() if req.created_at else None
            })
        
        logger.info(f"Retrieved {len(result)} leave requests")
        
        return {
            "success": True,
            "count": len(result),
            "requests": result
        }
        
    except Exception as e:
        logger.error(f"Error getting leave requests: {e}")
        return {"success": False, "error": str(e)}


def approve_leave(
    leave_id: int,
    faculty_id: str,
    comments: Optional[str] = None,
    db: Session = None
) -> Dict[str, Any]:
    """
    Approve leave request (faculty only)
    
    Args:
        leave_id: Leave request ID
        faculty_id: Faculty ID approving the leave
        comments: Optional approval comments
        db: Database session
    
    Returns:
        Approval result
    """
    if not db:
        return {"success": False, "error": "Database session not provided"}
    
    try:
        from database import LeaveRequest, Notification, Student
        
        leave = db.query(LeaveRequest).filter(LeaveRequest.id == leave_id).first()
        if not leave:
            return {"success": False, "error": f"Leave request #{leave_id} not found"}
        
        if leave.status != "pending":
            return {"success": False, "error": f"Leave request is already {leave.status}"}
        
        # Update status
        leave.status = "approved"
        
        # Get student info
        student = db.query(Student).filter(Student.reg_no == leave.student_reg).first()
        
        # Send notification to student
        message = f"Your leave request for {leave.from_date} to {leave.to_date} has been APPROVED."
        if comments:
            message += f"\n\nComments: {comments}"
        
        db.add(Notification(
            user_id=leave.student_reg,
            title="✅ Leave Approved",
            message=message,
            icon="✅",
            created_at=datetime.now()
        ))
        
        db.commit()
        
        logger.info(f"Leave request #{leave_id} approved by {faculty_id}")
        
        return {
            "success": True,
            "leave_id": leave_id,
            "student_id": leave.student_reg,
            "student_name": student.name if student else leave.student_reg,
            "status": "approved",
            "message": f"Leave request #{leave_id} approved successfully"
        }
        
    except Exception as e:
        logger.error(f"Error approving leave: {e}")
        db.rollback()
        return {"success": False, "error": str(e)}


def reject_leave(
    leave_id: int,
    faculty_id: str,
    reason: Optional[str] = None,
    db: Session = None
) -> Dict[str, Any]:
    """
    Reject leave request (faculty only)
    
    Args:
        leave_id: Leave request ID
        faculty_id: Faculty ID rejecting the leave
        reason: Optional rejection reason
        db: Database session
    
    Returns:
        Rejection result
    """
    if not db:
        return {"success": False, "error": "Database session not provided"}
    
    try:
        from database import LeaveRequest, Notification, Student
        
        leave = db.query(LeaveRequest).filter(LeaveRequest.id == leave_id).first()
        if not leave:
            return {"success": False, "error": f"Leave request #{leave_id} not found"}
        
        if leave.status != "pending":
            return {"success": False, "error": f"Leave request is already {leave.status}"}
        
        # Update status
        leave.status = "rejected"
        
        # Get student info
        student = db.query(Student).filter(Student.reg_no == leave.student_reg).first()
        
        # Send notification to student
        message = f"Your leave request for {leave.from_date} to {leave.to_date} has been REJECTED."
        if reason:
            message += f"\n\nReason: {reason}"
        
        db.add(Notification(
            user_id=leave.student_reg,
            title="❌ Leave Rejected",
            message=message,
            icon="❌",
            created_at=datetime.now()
        ))
        
        db.commit()
        
        logger.info(f"Leave request #{leave_id} rejected by {faculty_id}")
        
        return {
            "success": True,
            "leave_id": leave_id,
            "student_id": leave.student_reg,
            "student_name": student.name if student else leave.student_reg,
            "status": "rejected",
            "message": f"Leave request #{leave_id} rejected"
        }
        
    except Exception as e:
        logger.error(f"Error rejecting leave: {e}")
        db.rollback()
        return {"success": False, "error": str(e)}

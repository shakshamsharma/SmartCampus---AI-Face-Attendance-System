"""
Function Registry - Available AI Functions
Defines all functions that AI can call to interact with the system
"""
import logging
from typing import Dict, List, Any, Callable
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class FunctionRegistry:
    """
    Registry of all available functions for AI assistant
    Maps function names to implementations and schemas
    """
    
    def __init__(self):
        self.functions: Dict[str, Dict[str, Any]] = {}
        self.handlers: Dict[str, Callable] = {}
        self._register_all_functions()
    
    def register(self, name: str, schema: Dict[str, Any], handler: Callable):
        """
        Register a new function
        
        Args:
            name: Function name
            schema: OpenAI function schema
            handler: Function implementation
        """
        self.functions[name] = schema
        self.handlers[name] = handler
        logger.info(f"Registered function: {name}")
    
    def get_function_schemas(self, role: str = None) -> List[Dict[str, Any]]:
        """
        Get all function schemas, optionally filtered by role
        
        Args:
            role: User role (student, faculty, admin)
        
        Returns:
            List of function schemas
        """
        if role:
            # Filter functions by role permissions
            return [
                schema for name, schema in self.functions.items()
                if self._is_allowed_for_role(name, role)
            ]
        return list(self.functions.values())
    
    def execute(self, name: str, arguments: Dict[str, Any], context: Dict[str, Any]) -> Any:
        """
        Execute a function
        
        Args:
            name: Function name
            arguments: Function arguments
            context: Execution context (user_id, role, etc.)
        
        Returns:
            Function result
        """
        if name not in self.handlers:
            raise ValueError(f"Function not found: {name}")
        
        handler = self.handlers[name]
        
        try:
            logger.info(f"Executing function: {name} with args: {arguments}")
            result = handler(arguments, context)
            logger.info(f"Function {name} executed successfully")
            return result
        except Exception as e:
            logger.error(f"Function {name} execution error: {e}")
            raise
    
    def _is_allowed_for_role(self, function_name: str, role: str) -> bool:
        """Check if function is allowed for role"""
        # Define role permissions
        permissions = {
            "student": [
                "get_attendance",
                "get_attendance_prediction",
                "apply_leave",
                "get_timetable",
                "get_notifications",
                "check_eligibility",
                "get_subject_attendance",
                "search_campus_info"
            ],
            "faculty": [
                "get_attendance",
                "get_student_list",
                "get_low_attendance_students",
                "get_timetable",
                "generate_report",
                "approve_leave",
                "reject_leave",
                "send_notification",
                "mark_manual_attendance",
                "get_today_schedule",
                "search_campus_info"
            ],
            "admin": [
                # Admin has access to all functions
                "*"
            ]
        }
        
        if role == "admin":
            return True
        
        allowed = permissions.get(role, [])
        return function_name in allowed
    
    def _register_all_functions(self):
        """Register all available functions"""
        
        # ============================================================
        # ATTENDANCE FUNCTIONS
        # ============================================================
        
        self.register(
            "get_attendance",
            {
                "name": "get_attendance",
                "description": "Get attendance percentage and details for a student. Can filter by subject.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "student_id": {
                            "type": "string",
                            "description": "Student registration number (optional, defaults to current user)"
                        },
                        "subject": {
                            "type": "string",
                            "description": "Subject name to filter (optional, e.g., 'DSA', 'Python')"
                        }
                    }
                }
            },
            self._get_attendance_handler
        )
        
        self.register(
            "get_attendance_prediction",
            {
                "name": "get_attendance_prediction",
                "description": "Predict future attendance percentage and identify risk of falling below 75%",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "student_id": {
                            "type": "string",
                            "description": "Student registration number"
                        },
                        "days_ahead": {
                            "type": "integer",
                            "description": "Number of days to predict ahead (default: 14)"
                        }
                    }
                }
            },
            self._get_attendance_prediction_handler
        )
        
        self.register(
            "get_subject_attendance",
            {
                "name": "get_subject_attendance",
                "description": "Get detailed attendance for a specific subject",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "student_id": {
                            "type": "string",
                            "description": "Student registration number"
                        },
                        "subject": {
                            "type": "string",
                            "description": "Subject name (required)"
                        }
                    },
                    "required": ["subject"]
                }
            },
            self._get_subject_attendance_handler
        )
        
        # ============================================================
        # LEAVE FUNCTIONS
        # ============================================================
        
        self.register(
            "apply_leave",
            {
                "name": "apply_leave",
                "description": "Apply for leave for specified dates with reason",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "from_date": {
                            "type": "string",
                            "description": "Start date (YYYY-MM-DD format)"
                        },
                        "to_date": {
                            "type": "string",
                            "description": "End date (YYYY-MM-DD format)"
                        },
                        "reason": {
                            "type": "string",
                            "description": "Reason for leave"
                        },
                        "leave_type": {
                            "type": "string",
                            "description": "Type of leave (sick, personal, emergency)",
                            "enum": ["sick", "personal", "emergency"]
                        }
                    },
                    "required": ["from_date", "to_date", "reason"]
                }
            },
            self._apply_leave_handler
        )
        
        self.register(
            "approve_leave",
            {
                "name": "approve_leave",
                "description": "Approve a pending leave request (faculty/admin only)",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "leave_id": {
                            "type": "integer",
                            "description": "Leave request ID"
                        },
                        "comments": {
                            "type": "string",
                            "description": "Optional approval comments"
                        }
                    },
                    "required": ["leave_id"]
                }
            },
            self._approve_leave_handler
        )
        
        # ============================================================
        # TIMETABLE FUNCTIONS
        # ============================================================
        
        self.register(
            "get_timetable",
            {
                "name": "get_timetable",
                "description": "Get timetable/schedule for a specific date or day",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "date": {
                            "type": "string",
                            "description": "Date (YYYY-MM-DD) or day name (Monday, Tuesday, etc.)"
                        },
                        "user_id": {
                            "type": "string",
                            "description": "User ID (optional, defaults to current user)"
                        }
                    }
                }
            },
            self._get_timetable_handler
        )
        
        self.register(
            "get_today_schedule",
            {
                "name": "get_today_schedule",
                "description": "Get today's class schedule",
                "parameters": {
                    "type": "object",
                    "properties": {}
                }
            },
            self._get_today_schedule_handler
        )
        
        # ============================================================
        # REPORT FUNCTIONS
        # ============================================================
        
        self.register(
            "generate_report",
            {
                "name": "generate_report",
                "description": "Generate attendance or analytics report",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "report_type": {
                            "type": "string",
                            "description": "Type of report",
                            "enum": ["attendance", "student_analytics", "department_analytics", "monthly_summary"]
                        },
                        "filters": {
                            "type": "object",
                            "description": "Report filters (subject, date_from, date_to, department, etc.)"
                        },
                        "format": {
                            "type": "string",
                            "description": "Output format",
                            "enum": ["pdf", "csv", "json"]
                        }
                    },
                    "required": ["report_type"]
                }
            },
            self._generate_report_handler
        )
        
        # ============================================================
        # NOTIFICATION FUNCTIONS
        # ============================================================
        
        self.register(
            "send_notification",
            {
                "name": "send_notification",
                "description": "Send notification to users (faculty/admin only)",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "recipients": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of user IDs or 'all_students', 'all_faculty'"
                        },
                        "title": {
                            "type": "string",
                            "description": "Notification title"
                        },
                        "message": {
                            "type": "string",
                            "description": "Notification message"
                        },
                        "icon": {
                            "type": "string",
                            "description": "Notification icon emoji"
                        }
                    },
                    "required": ["recipients", "title", "message"]
                }
            },
            self._send_notification_handler
        )
        
        # ============================================================
        # ANALYTICS FUNCTIONS
        # ============================================================
        
        self.register(
            "get_low_attendance_students",
            {
                "name": "get_low_attendance_students",
                "description": "Get list of students with attendance below threshold",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "threshold": {
                            "type": "number",
                            "description": "Attendance percentage threshold (default: 75)"
                        },
                        "subject": {
                            "type": "string",
                            "description": "Filter by subject (optional)"
                        }
                    }
                }
            },
            self._get_low_attendance_students_handler
        )
        
        self.register(
            "check_eligibility",
            {
                "name": "check_eligibility",
                "description": "Check if student is eligible for exams (75% attendance required)",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "student_id": {
                            "type": "string",
                            "description": "Student registration number"
                        }
                    }
                }
            },
            self._check_eligibility_handler
        )
        
        # ============================================================
        # SEARCH FUNCTIONS
        # ============================================================
        
        self.register(
            "search_campus_info",
            {
                "name": "search_campus_info",
                "description": "Search campus information (notices, events, faculty info, policies)",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query"
                        },
                        "category": {
                            "type": "string",
                            "description": "Category to search in",
                            "enum": ["notices", "events", "faculty", "policies", "all"]
                        }
                    },
                    "required": ["query"]
                }
            },
            self._search_campus_info_handler
        )
    
    # ============================================================
    # FUNCTION HANDLERS (Placeholders - will be implemented with actual DB logic)
    # ============================================================
    
    def _get_attendance_handler(self, args: Dict, context: Dict) -> Dict:
        """Get attendance - NOW WITH REAL DATABASE INTEGRATION"""
        # Import here to avoid circular dependency
        try:
            from ai_assistant.actions.attendance_actions import get_attendance
            
            student_id = args.get("student_id") or context.get("user_id")
            subject = args.get("subject")
            db = context.get("db")
            
            if not db:
                return {
                    "success": False,
                    "error": "Database session not available"
                }
            
            # Call real database function
            result = get_attendance(student_id, subject, db)
            return result
            
        except Exception as e:
            logger.error(f"Error in get_attendance handler: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def _get_attendance_prediction_handler(self, args: Dict, context: Dict) -> Dict:
        """Predict attendance - NOW WITH REAL DATABASE INTEGRATION"""
        try:
            from ai_assistant.actions.attendance_actions import predict_attendance
            
            student_id = args.get("student_id") or context.get("user_id")
            days_ahead = args.get("days_ahead", 14)
            db = context.get("db")
            
            if not db:
                return {"success": False, "error": "Database session not available"}
            
            result = predict_attendance(student_id, days_ahead, db)
            return result
            
        except Exception as e:
            logger.error(f"Error in predict_attendance handler: {e}")
            return {"success": False, "error": str(e)}
    
    def _get_subject_attendance_handler(self, args: Dict, context: Dict) -> Dict:
        """Get subject attendance - placeholder"""
        return {
            "success": True,
            "subject": args.get("subject"),
            "percentage": 88,
            "present": 22,
            "total": 25,
            "absent_dates": ["2024-01-15", "2024-01-22", "2024-02-05"]
        }
    
    def _apply_leave_handler(self, args: Dict, context: Dict) -> Dict:
        """Apply leave - NOW WITH REAL DATABASE INTEGRATION"""
        try:
            from ai_assistant.actions.leave_actions import apply_leave
            
            student_id = context.get("user_id")
            from_date = args.get("from_date")
            to_date = args.get("to_date")
            reason = args.get("reason")
            leave_type = args.get("leave_type", "personal")
            db = context.get("db")
            
            if not db:
                return {"success": False, "error": "Database session not available"}
            
            if not all([from_date, to_date, reason]):
                return {
                    "success": False,
                    "error": "Missing required fields: from_date, to_date, reason"
                }
            
            result = apply_leave(student_id, from_date, to_date, reason, leave_type, db)
            return result
            
        except Exception as e:
            logger.error(f"Error in apply_leave handler: {e}")
            return {"success": False, "error": str(e)}
    
    def _approve_leave_handler(self, args: Dict, context: Dict) -> Dict:
        """Approve leave - placeholder"""
        return {
            "success": True,
            "message": f"Leave request #{args['leave_id']} approved"
        }
    
    def _get_timetable_handler(self, args: Dict, context: Dict) -> Dict:
        """Get timetable - placeholder"""
        return {
            "success": True,
            "date": args.get("date", "today"),
            "schedule": [
                {"time": "09:00-10:00", "subject": "DSA", "faculty": "Dr. Smith", "room": "CS-101"},
                {"time": "10:00-11:00", "subject": "Python", "faculty": "Dr. Johnson", "room": "CS-102"},
                {"time": "11:00-12:00", "subject": "English", "faculty": "Prof. Williams", "room": "LH-201"}
            ]
        }
    
    def _get_today_schedule_handler(self, args: Dict, context: Dict) -> Dict:
        """Get today's schedule - placeholder"""
        return self._get_timetable_handler({"date": "today"}, context)
    
    def _generate_report_handler(self, args: Dict, context: Dict) -> Dict:
        """Generate report - placeholder"""
        return {
            "success": True,
            "report_type": args["report_type"],
            "report_url": "/reports/attendance_2024_02.pdf",
            "message": "Report generated successfully"
        }
    
    def _send_notification_handler(self, args: Dict, context: Dict) -> Dict:
        """Send notification - placeholder"""
        return {
            "success": True,
            "recipients_count": len(args["recipients"]),
            "message": "Notification sent successfully"
        }
    
    def _get_low_attendance_students_handler(self, args: Dict, context: Dict) -> Dict:
        """Get low attendance students - NOW WITH REAL DATABASE INTEGRATION"""
        try:
            from ai_assistant.actions.attendance_actions import get_low_attendance_students
            
            threshold = args.get("threshold", 75)
            subject = args.get("subject")
            db = context.get("db")
            
            if not db:
                return {"success": False, "error": "Database session not available"}
            
            result = get_low_attendance_students(threshold, subject, db)
            return result
            
        except Exception as e:
            logger.error(f"Error in get_low_attendance_students handler: {e}")
            return {"success": False, "error": str(e)}
    
    def _check_eligibility_handler(self, args: Dict, context: Dict) -> Dict:
        """Check eligibility - NOW WITH REAL DATABASE INTEGRATION"""
        try:
            from ai_assistant.actions.attendance_actions import check_eligibility
            
            student_id = args.get("student_id") or context.get("user_id")
            db = context.get("db")
            
            if not db:
                return {"success": False, "error": "Database session not available"}
            
            result = check_eligibility(student_id, db)
            return result
            
        except Exception as e:
            logger.error(f"Error in check_eligibility handler: {e}")
            return {"success": False, "error": str(e)}
    
    def _search_campus_info_handler(self, args: Dict, context: Dict) -> Dict:
        """Search campus info - placeholder"""
        return {
            "success": True,
            "query": args["query"],
            "results": [
                {"type": "notice", "title": "Mid-term Exam Schedule", "date": "2024-02-15"},
                {"type": "event", "title": "Tech Fest 2024", "date": "2024-03-01"}
            ]
        }


# Singleton instance
_function_registry = None

def get_function_registry() -> FunctionRegistry:
    """Get or create function registry singleton"""
    global _function_registry
    if _function_registry is None:
        _function_registry = FunctionRegistry()
    return _function_registry

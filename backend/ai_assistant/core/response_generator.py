"""
Response Generator - Formats AI Responses
Generates rich, formatted responses with cards, charts, and quick actions
"""
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

class ResponseGenerator:
    """
    Generates formatted responses for AI assistant
    Supports text, cards, charts, tables, and quick actions
    """
    
    def __init__(self):
        """Initialize response generator"""
        logger.info("Response Generator initialized")
    
    def generate(
        self,
        content: str,
        data: Optional[Dict[str, Any]] = None,
        format_type: str = "text",
        quick_actions: Optional[List[Dict]] = None
    ) -> Dict[str, Any]:
        """
        Generate formatted response
        
        Args:
            content: Main response text
            data: Optional data for rich formatting
            format_type: Response format (text, card, chart, table)
            quick_actions: Optional quick action buttons
        
        Returns:
            Formatted response dict
        """
        response = {
            "type": format_type,
            "content": content,
            "timestamp": datetime.now().isoformat()
        }
        
        if data:
            response["data"] = data
        
        if quick_actions:
            response["quick_actions"] = quick_actions
        
        # Generate format-specific content
        if format_type == "card" and data:
            response["card"] = self._generate_card(data)
        elif format_type == "chart" and data:
            response["chart"] = self._generate_chart(data)
        elif format_type == "table" and data:
            response["table"] = self._generate_table(data)
        
        return response
    
    def generate_attendance_card(self, attendance_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate attendance summary card
        
        Args:
            attendance_data: Attendance data from function
        
        Returns:
            Formatted card response
        """
        overall_pct = attendance_data.get("overall_percentage", 0)
        total_classes = attendance_data.get("total_classes", 0)
        present = attendance_data.get("present", 0)
        absent = attendance_data.get("absent", 0)
        
        # Determine status
        if overall_pct >= 75:
            status = "safe"
            status_emoji = "✅"
            status_text = "You're doing great!"
        elif overall_pct >= 65:
            status = "warning"
            status_emoji = "⚠️"
            status_text = "Attend more classes to stay safe"
        else:
            status = "critical"
            status_emoji = "🚨"
            status_text = "Urgent: Attend all upcoming classes"
        
        content = f"{status_emoji} Your overall attendance is **{overall_pct}%**\n\n"
        content += f"📊 **Summary:**\n"
        content += f"• Present: {present}/{total_classes} classes\n"
        content += f"• Absent: {absent} classes\n"
        content += f"• Status: {status_text}"
        
        # Add subject breakdown if available
        subjects = attendance_data.get("subjects", {})
        if subjects:
            content += f"\n\n📚 **Subject-wise:**\n"
            for subject, stats in subjects.items():
                pct = stats.get("percentage", 0)
                emoji = "✅" if pct >= 75 else "⚠️" if pct >= 65 else "🚨"
                content += f"{emoji} {subject}: {pct}% ({stats.get('present', 0)}/{stats.get('total', 0)})\n"
        
        quick_actions = [
            {"label": "📈 View Trend", "action": "show my attendance trend"},
            {"label": "🔮 Predict Future", "action": "predict my attendance"},
            {"label": "📝 Apply Leave", "action": "apply leave"}
        ]
        
        return self.generate(
            content=content,
            data=attendance_data,
            format_type="card",
            quick_actions=quick_actions
        )
    
    def generate_timetable_card(self, timetable_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate timetable card
        
        Args:
            timetable_data: Timetable data from function
        
        Returns:
            Formatted card response
        """
        date = timetable_data.get("date", "")
        day = timetable_data.get("day", "")
        schedule = timetable_data.get("schedule", [])
        
        if not schedule:
            content = f"📅 No classes scheduled for {day}"
            quick_actions = [
                {"label": "📚 Tomorrow's Schedule", "action": "show tomorrow's timetable"},
                {"label": "📆 Full Week", "action": "show this week's timetable"}
            ]
        else:
            content = f"📅 **{day}'s Schedule** ({date})\n\n"
            
            for i, cls in enumerate(schedule, 1):
                content += f"**{i}. {cls.get('time', '')}**\n"
                content += f"   📚 {cls.get('subject', '')}\n"
                content += f"   👨‍🏫 {cls.get('faculty', '')}\n"
                content += f"   🏫 {cls.get('room', '')}\n\n"
            
            content += f"Total: {len(schedule)} classes"
            
            quick_actions = [
                {"label": "✅ Mark Attendance", "action": "mark my attendance"},
                {"label": "📝 Apply Leave", "action": "apply leave for today"}
            ]
        
        return self.generate(
            content=content,
            data=timetable_data,
            format_type="card",
            quick_actions=quick_actions
        )
    
    def generate_leave_confirmation(self, leave_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate leave application confirmation
        
        Args:
            leave_data: Leave application data
        
        Returns:
            Formatted response
        """
        leave_id = leave_data.get("leave_id")
        from_date = leave_data.get("from_date", "")
        to_date = leave_data.get("to_date", "")
        status = leave_data.get("status", "pending")
        
        content = f"✅ **Leave Application Submitted**\n\n"
        content += f"📋 Leave ID: #{leave_id}\n"
        content += f"📅 Duration: {from_date} to {to_date}\n"
        content += f"📊 Status: {status.upper()}\n\n"
        content += f"Your leave request has been sent to faculty for approval. You'll be notified once it's reviewed."
        
        quick_actions = [
            {"label": "📋 View Leave Status", "action": "show my leave requests"},
            {"label": "📧 Check Notifications", "action": "show notifications"}
        ]
        
        return self.generate(
            content=content,
            data=leave_data,
            format_type="card",
            quick_actions=quick_actions
        )
    
    def generate_student_list(self, students_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate student list (for faculty)
        
        Args:
            students_data: Student list data
        
        Returns:
            Formatted table response
        """
        students = students_data.get("students", [])
        threshold = students_data.get("threshold", 75)
        
        if not students:
            content = f"✅ All students have attendance above {threshold}%"
            return self.generate(content=content, format_type="text")
        
        content = f"⚠️ **Students Below {threshold}% Attendance**\n\n"
        content += f"Found {len(students)} students:\n\n"
        
        for i, student in enumerate(students, 1):
            reg_no = student.get("reg_no", "")
            name = student.get("name", "")
            pct = student.get("percentage", 0)
            emoji = "🚨" if pct < 65 else "⚠️"
            content += f"{emoji} **{i}. {name}** ({reg_no})\n"
            content += f"   Attendance: {pct}%\n\n"
        
        quick_actions = [
            {"label": "📧 Send Reminder", "action": "send reminder to low attendance students"},
            {"label": "📊 Generate Report", "action": "generate attendance report"}
        ]
        
        return self.generate(
            content=content,
            data=students_data,
            format_type="table",
            quick_actions=quick_actions
        )
    
    def generate_prediction_card(self, prediction_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate attendance prediction card
        
        Args:
            prediction_data: Prediction data
        
        Returns:
            Formatted card response
        """
        current_pct = prediction_data.get("current_percentage", 0)
        predicted_pct = prediction_data.get("predicted_percentage", 0)
        days_ahead = prediction_data.get("days_ahead", 14)
        risk_level = prediction_data.get("risk_level", "low")
        recommendation = prediction_data.get("recommendation", "")
        
        # Determine emoji based on risk
        risk_emojis = {
            "low": "✅",
            "medium": "⚠️",
            "high": "🚨"
        }
        emoji = risk_emojis.get(risk_level, "📊")
        
        content = f"{emoji} **Attendance Prediction**\n\n"
        content += f"📊 Current: {current_pct}%\n"
        content += f"🔮 Predicted ({days_ahead} days): {predicted_pct}%\n"
        content += f"⚠️ Risk Level: {risk_level.upper()}\n\n"
        content += f"💡 **Recommendation:**\n{recommendation}"
        
        quick_actions = [
            {"label": "📅 View Timetable", "action": "show my timetable"},
            {"label": "📝 Apply Leave", "action": "apply leave"}
        ]
        
        return self.generate(
            content=content,
            data=prediction_data,
            format_type="card",
            quick_actions=quick_actions
        )
    
    def generate_error_response(self, error_message: str) -> Dict[str, Any]:
        """
        Generate error response
        
        Args:
            error_message: Error message
        
        Returns:
            Formatted error response
        """
        content = f"❌ **Error**\n\n{error_message}\n\nPlease try again or contact support if the issue persists."
        
        quick_actions = [
            {"label": "🏠 Go to Dashboard", "action": "show dashboard"},
            {"label": "❓ Get Help", "action": "help"}
        ]
        
        return self.generate(
            content=content,
            format_type="text",
            quick_actions=quick_actions
        )
    
    def generate_greeting_response(self, user_name: str, role: str) -> Dict[str, Any]:
        """
        Generate greeting response
        
        Args:
            user_name: User's name
            role: User's role
        
        Returns:
            Formatted greeting response
        """
        hour = datetime.now().hour
        if hour < 12:
            greeting = "Good morning"
            emoji = "🌅"
        elif hour < 17:
            greeting = "Good afternoon"
            emoji = "☀️"
        else:
            greeting = "Good evening"
            emoji = "🌙"
        
        content = f"{emoji} {greeting}, {user_name}!\n\n"
        content += f"I'm your SmartCampus AI assistant. How can I help you today?"
        
        # Role-specific quick actions
        if role == "student":
            quick_actions = [
                {"label": "📊 Check Attendance", "action": "what's my attendance"},
                {"label": "📅 View Timetable", "action": "show today's timetable"},
                {"label": "📝 Apply Leave", "action": "apply leave"}
            ]
        elif role == "faculty":
            quick_actions = [
                {"label": "📋 Today's Schedule", "action": "show today's schedule"},
                {"label": "⚠️ Low Attendance Students", "action": "show students below 75%"},
                {"label": "📊 Generate Report", "action": "generate attendance report"}
            ]
        else:  # admin
            quick_actions = [
                {"label": "📊 System Analytics", "action": "show system analytics"},
                {"label": "🔒 Security Dashboard", "action": "show security dashboard"},
                {"label": "📈 Department Stats", "action": "show department statistics"}
            ]
        
        return self.generate(
            content=content,
            format_type="text",
            quick_actions=quick_actions
        )
    
    def _generate_card(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Generate card structure"""
        return {
            "title": data.get("title", ""),
            "subtitle": data.get("subtitle", ""),
            "fields": data.get("fields", []),
            "footer": data.get("footer", "")
        }
    
    def _generate_chart(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Generate chart structure"""
        return {
            "type": data.get("chart_type", "line"),
            "labels": data.get("labels", []),
            "datasets": data.get("datasets", []),
            "options": data.get("options", {})
        }
    
    def _generate_table(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Generate table structure"""
        return {
            "headers": data.get("headers", []),
            "rows": data.get("rows", []),
            "footer": data.get("footer", "")
        }


# Singleton instance
_response_generator = None

def get_response_generator() -> ResponseGenerator:
    """Get or create response generator singleton"""
    global _response_generator
    if _response_generator is None:
        _response_generator = ResponseGenerator()
    return _response_generator

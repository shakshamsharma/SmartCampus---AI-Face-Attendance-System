"""
Intent Classifier - Natural Language Understanding
Classifies user intent from messages to route to appropriate handlers
"""
import logging
import re
from typing import Dict, List, Tuple, Optional

logger = logging.getLogger(__name__)

class IntentClassifier:
    """
    Classifies user intent from natural language messages
    Uses keyword matching and pattern recognition
    """
    
    # Intent categories
    INTENTS = {
        "attendance_query": {
            "keywords": ["attendance", "present", "absent", "percentage", "classes attended", "how many classes"],
            "patterns": [
                r"what.*attendance",
                r"show.*attendance",
                r"my attendance",
                r"attendance.*percentage",
                r"how many.*present",
                r"how many.*absent"
            ]
        },
        "attendance_prediction": {
            "keywords": ["predict", "future", "will i", "eligible", "fall below", "trend"],
            "patterns": [
                r"predict.*attendance",
                r"future.*attendance",
                r"will.*fall.*below",
                r"am i.*eligible",
                r"attendance.*trend"
            ]
        },
        "leave_application": {
            "keywords": ["leave", "apply", "absent tomorrow", "won't come", "can't attend"],
            "patterns": [
                r"apply.*leave",
                r"take.*leave",
                r"leave.*tomorrow",
                r"leave.*for.*days?",
                r"won'?t.*come",
                r"can'?t.*attend"
            ]
        },
        "timetable_query": {
            "keywords": ["timetable", "schedule", "class", "lecture", "when", "next class", "today's class"],
            "patterns": [
                r"what.*class",
                r"when.*class",
                r"next.*class",
                r"today'?s?.*schedule",
                r"show.*timetable",
                r"any.*class.*tomorrow"
            ]
        },
        "report_generation": {
            "keywords": ["report", "generate", "download", "export", "pdf", "csv"],
            "patterns": [
                r"generate.*report",
                r"create.*report",
                r"download.*report",
                r"export.*attendance"
            ]
        },
        "student_query": {
            "keywords": ["student", "who", "which students", "list students", "below 75"],
            "patterns": [
                r"which.*students",
                r"who.*below",
                r"list.*students",
                r"students.*attendance",
                r"low.*attendance.*students"
            ]
        },
        "notification_send": {
            "keywords": ["notify", "send", "alert", "remind", "message"],
            "patterns": [
                r"send.*notification",
                r"notify.*students",
                r"send.*reminder",
                r"alert.*students"
            ]
        },
        "eligibility_check": {
            "keywords": ["eligible", "eligibility", "exam", "75%", "75 percent"],
            "patterns": [
                r"am i.*eligible",
                r"eligible.*exam",
                r"check.*eligibility",
                r"75.*percent"
            ]
        },
        "campus_search": {
            "keywords": ["search", "find", "where", "who is", "faculty", "notice", "event"],
            "patterns": [
                r"search.*for",
                r"find.*information",
                r"who.*is.*faculty",
                r"where.*is",
                r"any.*notice",
                r"upcoming.*event"
            ]
        },
        "analytics_query": {
            "keywords": ["analytics", "statistics", "stats", "dashboard", "overview", "summary"],
            "patterns": [
                r"show.*analytics",
                r"department.*stats",
                r"system.*overview",
                r"attendance.*summary"
            ]
        },
        "greeting": {
            "keywords": ["hello", "hi", "hey", "good morning", "good afternoon", "good evening"],
            "patterns": [
                r"^hi+$",
                r"^hello+$",
                r"^hey+$",
                r"good\s+(morning|afternoon|evening)"
            ]
        },
        "help": {
            "keywords": ["help", "what can you do", "how to", "guide", "assist"],
            "patterns": [
                r"what.*can.*you.*do",
                r"how.*to",
                r"help.*me",
                r"need.*help"
            ]
        },
        "general_query": {
            "keywords": [],  # Fallback intent
            "patterns": []
        }
    }
    
    def __init__(self):
        """Initialize intent classifier"""
        logger.info("Intent Classifier initialized")
    
    def classify(self, message: str, context: Optional[Dict] = None) -> Tuple[str, float]:
        """
        Classify user intent from message
        
        Args:
            message: User message
            context: Optional conversation context
        
        Returns:
            Tuple of (intent, confidence_score)
        """
        message_lower = message.lower().strip()
        
        # Check for empty message
        if not message_lower:
            return "general_query", 0.0
        
        # Score each intent
        intent_scores = {}
        
        for intent_name, intent_data in self.INTENTS.items():
            score = 0.0
            
            # Check keywords
            keyword_matches = sum(1 for kw in intent_data["keywords"] if kw in message_lower)
            if keyword_matches > 0:
                score += keyword_matches * 0.3
            
            # Check patterns
            pattern_matches = sum(1 for pattern in intent_data["patterns"] if re.search(pattern, message_lower))
            if pattern_matches > 0:
                score += pattern_matches * 0.5
            
            # Context boost (if previous intent was similar)
            if context and context.get("current_intent") == intent_name:
                score += 0.2
            
            intent_scores[intent_name] = min(score, 1.0)  # Cap at 1.0
        
        # Get best intent
        if not intent_scores or max(intent_scores.values()) == 0:
            return "general_query", 0.5
        
        best_intent = max(intent_scores, key=intent_scores.get)
        confidence = intent_scores[best_intent]
        
        logger.info(f"Classified intent: {best_intent} (confidence: {confidence:.2f})")
        return best_intent, confidence
    
    def extract_entities(self, message: str, intent: str) -> Dict[str, any]:
        """
        Extract entities from message based on intent
        
        Args:
            message: User message
            intent: Classified intent
        
        Returns:
            Dict of extracted entities
        """
        entities = {}
        message_lower = message.lower()
        
        # Extract dates
        date_patterns = {
            "tomorrow": r"tomorrow",
            "today": r"today",
            "yesterday": r"yesterday",
            "specific_date": r"\d{4}-\d{2}-\d{2}",
            "day_name": r"(monday|tuesday|wednesday|thursday|friday|saturday|sunday)"
        }
        
        for date_type, pattern in date_patterns.items():
            match = re.search(pattern, message_lower)
            if match:
                entities["date"] = match.group(0)
                entities["date_type"] = date_type
                break
        
        # Extract subjects
        subjects = ["dsa", "python", "dbms", "networking", "english", "math", "physics"]
        for subject in subjects:
            if subject in message_lower:
                entities["subject"] = subject.upper()
                break
        
        # Extract numbers (for days, percentages, etc.)
        numbers = re.findall(r"\b\d+\b", message)
        if numbers:
            entities["numbers"] = [int(n) for n in numbers]
        
        # Extract leave reason (for leave applications)
        if intent == "leave_application":
            reason_patterns = [
                r"due to (.+?)(?:\.|$)",
                r"because (.+?)(?:\.|$)",
                r"reason[:\s]+(.+?)(?:\.|$)"
            ]
            for pattern in reason_patterns:
                match = re.search(pattern, message_lower)
                if match:
                    entities["reason"] = match.group(1).strip()
                    break
        
        logger.debug(f"Extracted entities: {entities}")
        return entities
    
    def get_intent_description(self, intent: str) -> str:
        """Get human-readable description of intent"""
        descriptions = {
            "attendance_query": "Checking attendance records",
            "attendance_prediction": "Predicting future attendance",
            "leave_application": "Applying for leave",
            "timetable_query": "Checking class schedule",
            "report_generation": "Generating reports",
            "student_query": "Querying student information",
            "notification_send": "Sending notifications",
            "eligibility_check": "Checking exam eligibility",
            "campus_search": "Searching campus information",
            "analytics_query": "Viewing analytics",
            "greeting": "Greeting",
            "help": "Requesting help",
            "general_query": "General question"
        }
        return descriptions.get(intent, "Unknown intent")
    
    def suggest_clarification(self, intent: str, confidence: float) -> Optional[str]:
        """
        Suggest clarification question if confidence is low
        
        Args:
            intent: Classified intent
            confidence: Confidence score
        
        Returns:
            Clarification question or None
        """
        if confidence >= 0.7:
            return None
        
        clarifications = {
            "attendance_query": "Would you like to check your overall attendance or for a specific subject?",
            "leave_application": "Could you specify the dates and reason for your leave?",
            "timetable_query": "Which day's timetable would you like to see?",
            "report_generation": "What type of report would you like to generate?",
            "student_query": "Are you looking for students with low attendance?",
        }
        
        return clarifications.get(intent)


# Singleton instance
_intent_classifier = None

def get_intent_classifier() -> IntentClassifier:
    """Get or create intent classifier singleton"""
    global _intent_classifier
    if _intent_classifier is None:
        _intent_classifier = IntentClassifier()
    return _intent_classifier

"""
Context Manager - Conversation Memory and State Management
Manages conversation history, user context, and session state
"""
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
import json

logger = logging.getLogger(__name__)

class ContextManager:
    """
    Manages conversation context and memory for AI assistant
    Stores conversation history, tracks user intent, maintains session state
    """
    
    def __init__(self, redis_client=None, max_history: int = 10):
        """
        Initialize context manager
        
        Args:
            redis_client: Optional Redis client for persistent storage
            max_history: Maximum number of messages to keep in history
        """
        self.redis = redis_client
        self.max_history = max_history
        
        # In-memory storage (fallback if Redis not available)
        self.contexts: Dict[str, Dict[str, Any]] = {}
        
        logger.info(f"Context Manager initialized (max_history: {max_history})")
    
    def get_context(self, user_id: str) -> Dict[str, Any]:
        """
        Get conversation context for user
        
        Args:
            user_id: User identifier
        
        Returns:
            Context dict with history, metadata, and state
        """
        if self.redis:
            try:
                data = self.redis.get(f"ai_context:{user_id}")
                if data:
                    return json.loads(data)
            except Exception as e:
                logger.error(f"Redis get error: {e}")
        
        # Fallback to in-memory
        if user_id not in self.contexts:
            self.contexts[user_id] = self._create_empty_context()
        
        return self.contexts[user_id]
    
    def update_context(self, user_id: str, message: Dict[str, str]):
        """
        Add message to conversation history
        
        Args:
            user_id: User identifier
            message: Message dict with role and content
        """
        context = self.get_context(user_id)
        
        # Add message to history
        context["history"].append({
            "role": message["role"],
            "content": message["content"],
            "timestamp": datetime.now().isoformat()
        })
        
        # Keep only last N messages
        if len(context["history"]) > self.max_history:
            context["history"] = context["history"][-self.max_history:]
        
        # Update metadata
        context["last_updated"] = datetime.now().isoformat()
        context["message_count"] += 1
        
        # Save context
        self._save_context(user_id, context)
        
        logger.debug(f"Context updated for user {user_id}: {len(context['history'])} messages")
    
    def add_function_call(self, user_id: str, function_name: str, arguments: Dict, result: Any):
        """
        Track function call in context
        
        Args:
            user_id: User identifier
            function_name: Name of function called
            arguments: Function arguments
            result: Function result
        """
        context = self.get_context(user_id)
        
        # Add to function call history
        if "function_calls" not in context:
            context["function_calls"] = []
        
        context["function_calls"].append({
            "function": function_name,
            "arguments": arguments,
            "result": result,
            "timestamp": datetime.now().isoformat()
        })
        
        # Keep only last 5 function calls
        if len(context["function_calls"]) > 5:
            context["function_calls"] = context["function_calls"][-5:]
        
        self._save_context(user_id, context)
    
    def set_intent(self, user_id: str, intent: str):
        """
        Set current user intent
        
        Args:
            user_id: User identifier
            intent: Detected intent
        """
        context = self.get_context(user_id)
        context["current_intent"] = intent
        context["intent_updated_at"] = datetime.now().isoformat()
        self._save_context(user_id, context)
    
    def get_intent(self, user_id: str) -> Optional[str]:
        """Get current user intent"""
        context = self.get_context(user_id)
        return context.get("current_intent")
    
    def set_state(self, user_id: str, key: str, value: Any):
        """
        Set custom state variable
        
        Args:
            user_id: User identifier
            key: State key
            value: State value
        """
        context = self.get_context(user_id)
        if "state" not in context:
            context["state"] = {}
        context["state"][key] = value
        self._save_context(user_id, context)
    
    def get_state(self, user_id: str, key: str, default: Any = None) -> Any:
        """Get custom state variable"""
        context = self.get_context(user_id)
        return context.get("state", {}).get(key, default)
    
    def clear_context(self, user_id: str):
        """
        Clear conversation history for user
        
        Args:
            user_id: User identifier
        """
        if self.redis:
            try:
                self.redis.delete(f"ai_context:{user_id}")
            except Exception as e:
                logger.error(f"Redis delete error: {e}")
        
        if user_id in self.contexts:
            del self.contexts[user_id]
        
        logger.info(f"Context cleared for user {user_id}")
    
    def get_recent_topics(self, user_id: str, limit: int = 3) -> List[str]:
        """
        Extract recent topics from conversation
        
        Args:
            user_id: User identifier
            limit: Number of recent topics to return
        
        Returns:
            List of topic keywords
        """
        context = self.get_context(user_id)
        history = context.get("history", [])
        
        # Extract keywords from recent user messages
        topics = []
        keywords = ["attendance", "leave", "timetable", "exam", "class", "subject", "report"]
        
        for msg in reversed(history[-limit*2:]):  # Look at last N*2 messages
            if msg["role"] == "user":
                content_lower = msg["content"].lower()
                for keyword in keywords:
                    if keyword in content_lower and keyword not in topics:
                        topics.append(keyword)
                        if len(topics) >= limit:
                            return topics
        
        return topics
    
    def get_conversation_summary(self, user_id: str) -> str:
        """
        Generate a summary of the conversation
        
        Args:
            user_id: User identifier
        
        Returns:
            Summary string
        """
        context = self.get_context(user_id)
        history = context.get("history", [])
        
        if not history:
            return "No conversation history"
        
        user_messages = [m for m in history if m["role"] == "user"]
        topics = self.get_recent_topics(user_id, limit=5)
        
        return f"Conversation with {len(user_messages)} user messages. Recent topics: {', '.join(topics) if topics else 'general queries'}"
    
    def _create_empty_context(self) -> Dict[str, Any]:
        """Create empty context structure"""
        return {
            "history": [],
            "current_intent": None,
            "intent_updated_at": None,
            "last_updated": datetime.now().isoformat(),
            "message_count": 0,
            "function_calls": [],
            "state": {}
        }
    
    def _save_context(self, user_id: str, context: Dict[str, Any]):
        """Save context to storage"""
        if self.redis:
            try:
                self.redis.setex(
                    f"ai_context:{user_id}",
                    timedelta(hours=24),  # Expire after 24 hours
                    json.dumps(context)
                )
            except Exception as e:
                logger.error(f"Redis save error: {e}")
        
        # Always save to in-memory as fallback
        self.contexts[user_id] = context
    
    def get_all_active_sessions(self) -> List[str]:
        """Get list of all active user sessions"""
        if self.redis:
            try:
                keys = self.redis.keys("ai_context:*")
                return [k.decode().replace("ai_context:", "") for k in keys]
            except Exception as e:
                logger.error(f"Redis keys error: {e}")
        
        return list(self.contexts.keys())
    
    def get_session_stats(self) -> Dict[str, Any]:
        """Get statistics about active sessions"""
        active_sessions = self.get_all_active_sessions()
        
        total_messages = 0
        total_function_calls = 0
        
        for user_id in active_sessions:
            context = self.get_context(user_id)
            total_messages += context.get("message_count", 0)
            total_function_calls += len(context.get("function_calls", []))
        
        return {
            "active_sessions": len(active_sessions),
            "total_messages": total_messages,
            "total_function_calls": total_function_calls,
            "avg_messages_per_session": round(total_messages / len(active_sessions), 1) if active_sessions else 0
        }


# Singleton instance
_context_manager = None

def get_context_manager(redis_client=None, max_history: int = 10) -> ContextManager:
    """Get or create context manager singleton"""
    global _context_manager
    if _context_manager is None:
        _context_manager = ContextManager(redis_client=redis_client, max_history=max_history)
    return _context_manager

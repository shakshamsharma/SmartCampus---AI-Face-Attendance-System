"""
LLM Engine - OpenAI Integration with Function Calling
Handles all LLM interactions, function calling, and response generation
"""
import os
import json
import logging
from typing import List, Dict, Any, Optional
from openai import OpenAI
from datetime import datetime

logger = logging.getLogger(__name__)

class LLMEngine:
    """
    Core LLM engine for SmartCampus AI Assistant
    Supports function calling, streaming, and context management
    """
    
    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-4-turbo-preview"):
        """
        Initialize LLM engine
        
        Args:
            api_key: OpenAI API key (defaults to env variable)
            model: Model to use (gpt-4-turbo-preview, gpt-3.5-turbo)
        """
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OpenAI API key not found. Set OPENAI_API_KEY environment variable.")
        
        self.client = OpenAI(api_key=self.api_key)
        self.model = model
        
        logger.info(f"LLM Engine initialized with model: {model}")
    
    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        functions: Optional[List[Dict]] = None,
        function_call: str = "auto",
        temperature: float = 0.7,
        max_tokens: int = 1000,
        stream: bool = False
    ) -> Dict[str, Any]:
        """
        Generate chat completion with optional function calling
        
        Args:
            messages: Conversation history
            functions: Available functions for function calling
            function_call: "auto", "none", or {"name": "function_name"}
            temperature: Randomness (0-2)
            max_tokens: Maximum response length
            stream: Enable streaming response
        
        Returns:
            Response dict with message and optional function_call
        """
        try:
            params = {
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": stream
            }
            
            # Add functions if provided
            if functions:
                params["tools"] = [{"type": "function", "function": f} for f in functions]
                params["tool_choice"] = function_call
            
            response = self.client.chat.completions.create(**params)
            
            if stream:
                return response  # Return stream object
            
            # Parse response
            message = response.choices[0].message
            
            result = {
                "content": message.content,
                "role": message.role,
                "finish_reason": response.choices[0].finish_reason,
                "usage": {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens
                }
            }
            
            # Check for function call
            if message.tool_calls:
                tool_call = message.tool_calls[0]
                result["function_call"] = {
                    "id": tool_call.id,
                    "name": tool_call.function.name,
                    "arguments": json.loads(tool_call.function.arguments)
                }
            
            logger.info(f"LLM response generated. Tokens: {result['usage']['total_tokens']}")
            return result
            
        except Exception as e:
            logger.error(f"LLM completion error: {e}")
            raise
    
    def chat_completion_stream(
        self,
        messages: List[Dict[str, str]],
        functions: Optional[List[Dict]] = None,
        temperature: float = 0.7,
        max_tokens: int = 1000
    ):
        """
        Generate streaming chat completion
        
        Yields:
            Chunks of response text
        """
        try:
            params = {
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": True
            }
            
            if functions:
                params["tools"] = [{"type": "function", "function": f} for f in functions]
            
            stream = self.client.chat.completions.create(**params)
            
            for chunk in stream:
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
                    
        except Exception as e:
            logger.error(f"LLM streaming error: {e}")
            raise
    
    def generate_embedding(self, text: str, model: str = "text-embedding-ada-002") -> List[float]:
        """
        Generate text embedding for RAG/vector search
        
        Args:
            text: Text to embed
            model: Embedding model
        
        Returns:
            Embedding vector
        """
        try:
            response = self.client.embeddings.create(
                model=model,
                input=text
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"Embedding generation error: {e}")
            raise
    
    def moderate_content(self, text: str) -> Dict[str, Any]:
        """
        Check content for policy violations
        
        Args:
            text: Text to moderate
        
        Returns:
            Moderation results
        """
        try:
            response = self.client.moderations.create(input=text)
            result = response.results[0]
            
            return {
                "flagged": result.flagged,
                "categories": result.categories.model_dump(),
                "category_scores": result.category_scores.model_dump()
            }
        except Exception as e:
            logger.error(f"Content moderation error: {e}")
            raise
    
    def count_tokens(self, text: str) -> int:
        """
        Estimate token count for text
        
        Args:
            text: Text to count
        
        Returns:
            Approximate token count
        """
        # Rough estimation: 1 token ≈ 4 characters
        return len(text) // 4
    
    def optimize_messages(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int = 4000
    ) -> List[Dict[str, str]]:
        """
        Optimize message history to fit within token limit
        
        Args:
            messages: Full conversation history
            max_tokens: Maximum tokens allowed
        
        Returns:
            Optimized message list
        """
        # Keep system message + last N messages that fit
        system_msg = messages[0] if messages and messages[0]["role"] == "system" else None
        user_messages = [m for m in messages if m["role"] != "system"]
        
        optimized = []
        if system_msg:
            optimized.append(system_msg)
        
        current_tokens = self.count_tokens(system_msg["content"]) if system_msg else 0
        
        # Add messages from most recent backwards
        for msg in reversed(user_messages):
            msg_tokens = self.count_tokens(msg["content"])
            if current_tokens + msg_tokens < max_tokens:
                optimized.insert(1 if system_msg else 0, msg)
                current_tokens += msg_tokens
            else:
                break
        
        return optimized


# Singleton instance
_llm_engine = None

def get_llm_engine(api_key: Optional[str] = None, model: str = "gpt-4-turbo-preview") -> LLMEngine:
    """Get or create LLM engine singleton"""
    global _llm_engine
    if _llm_engine is None:
        _llm_engine = LLMEngine(api_key=api_key, model=model)
    return _llm_engine

"""
Configuration Management
Centralized configuration with environment variables and validation
"""
import os
import secrets
from typing import List
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    """Application settings with validation"""
    
    # Application
    APP_NAME: str = "SmartCampus AI"
    APP_VERSION: str = "3.0.0"
    ENVIRONMENT: str = Field(default="development", env="ENVIRONMENT")
    DEBUG: bool = Field(default=False, env="DEBUG")
    
    # Security
    SECRET_KEY: str = Field(default_factory=lambda: secrets.token_urlsafe(32), env="SECRET_KEY")
    JWT_ALGORITHM: str = Field(default="HS256", env="JWT_ALGORITHM")
    ACCESS_TOKEN_EXPIRE_HOURS: int = Field(default=24, env="ACCESS_TOKEN_EXPIRE_HOURS")
    
    # Database
    DATABASE_URL: str = Field(default="sqlite:///./smartcampus.db", env="DATABASE_URL")
    DB_POOL_SIZE: int = Field(default=5, env="DB_POOL_SIZE")
    DB_MAX_OVERFLOW: int = Field(default=10, env="DB_MAX_OVERFLOW")
    
    # Redis
    REDIS_URL: str = Field(default="redis://localhost:6379/0", env="REDIS_URL")
    REDIS_ENABLED: bool = Field(default=False, env="REDIS_ENABLED")
    
    # CORS
    FRONTEND_URL: str = Field(default="http://localhost:3000", env="FRONTEND_URL")
    ALLOWED_ORIGINS: List[str] = Field(
        default=["http://localhost:3000", "http://localhost:5173"],
        env="ALLOWED_ORIGINS"
    )
    
    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def parse_origins(cls, v):
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v
    
    # File Upload
    MAX_UPLOAD_SIZE_MB: int = Field(default=10, env="MAX_UPLOAD_SIZE_MB")
    ALLOWED_IMAGE_TYPES: List[str] = Field(
        default=["image/jpeg", "image/png", "image/jpg"],
        env="ALLOWED_IMAGE_TYPES"
    )
    
    @field_validator("ALLOWED_IMAGE_TYPES", mode="before")
    @classmethod
    def parse_image_types(cls, v):
        if isinstance(v, str):
            return [t.strip() for t in v.split(",")]
        return v
    
    # Face Recognition
    FACE_RECOGNITION_THRESHOLD: int = Field(default=60, env="FACE_RECOGNITION_THRESHOLD")
    MIN_CONFIDENCE_SCORE: int = Field(default=40, env="MIN_CONFIDENCE_SCORE")
    UNKNOWN_FACE_THRESHOLD: int = Field(default=75, env="UNKNOWN_FACE_THRESHOLD")
    FACE_DATA_DIR: str = Field(default="face_data", env="FACE_DATA_DIR")
    
    # Rate Limiting
    RATE_LIMIT_PER_MINUTE: int = Field(default=60, env="RATE_LIMIT_PER_MINUTE")
    LOGIN_RATE_LIMIT_PER_MINUTE: int = Field(default=5, env="LOGIN_RATE_LIMIT_PER_MINUTE")
    
    # AI Assistant
    OPENAI_API_KEY: str = Field(default="", env="OPENAI_API_KEY")
    AI_MODEL: str = Field(default="gpt-4-turbo-preview", env="AI_MODEL")
    AI_TEMPERATURE: float = Field(default=0.7, env="AI_TEMPERATURE")
    
    # Monitoring
    SENTRY_DSN: str = Field(default="", env="SENTRY_DSN")
    SENTRY_ENABLED: bool = Field(default=False, env="SENTRY_ENABLED")
    
    # Email
    SMTP_HOST: str = Field(default="", env="SMTP_HOST")
    SMTP_PORT: int = Field(default=587, env="SMTP_PORT")
    SMTP_USER: str = Field(default="", env="SMTP_USER")
    SMTP_PASSWORD: str = Field(default="", env="SMTP_PASSWORD")
    SMTP_FROM: str = Field(default="noreply@smartcampus.ai", env="SMTP_FROM")
    SMTP_ENABLED: bool = Field(default=False, env="SMTP_ENABLED")
    
    # Logging
    LOG_LEVEL: str = Field(default="INFO", env="LOG_LEVEL")
    LOG_FORMAT: str = Field(default="json", env="LOG_FORMAT")
    
    # Session
    SESSION_TIMEOUT_MINUTES: int = Field(default=30, env="SESSION_TIMEOUT_MINUTES")
    MAX_LOGIN_ATTEMPTS: int = Field(default=5, env="MAX_LOGIN_ATTEMPTS")
    LOCKOUT_DURATION_MINUTES: int = Field(default=15, env="LOCKOUT_DURATION_MINUTES")
    
    # Password Policy
    PASSWORD_MIN_LENGTH: int = Field(default=8, env="PASSWORD_MIN_LENGTH")
    PASSWORD_REQUIRE_UPPERCASE: bool = Field(default=True, env="PASSWORD_REQUIRE_UPPERCASE")
    PASSWORD_REQUIRE_LOWERCASE: bool = Field(default=True, env="PASSWORD_REQUIRE_LOWERCASE")
    PASSWORD_REQUIRE_DIGIT: bool = Field(default=True, env="PASSWORD_REQUIRE_DIGIT")
    PASSWORD_REQUIRE_SPECIAL: bool = Field(default=True, env="PASSWORD_REQUIRE_SPECIAL")
    
    # Pagination
    DEFAULT_PAGE_SIZE: int = Field(default=20, env="DEFAULT_PAGE_SIZE")
    MAX_PAGE_SIZE: int = Field(default=100, env="MAX_PAGE_SIZE")
    
    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"
    
    @property
    def is_production(self) -> bool:
        """Check if running in production"""
        return self.ENVIRONMENT.lower() == "production"
    
    @property
    def is_development(self) -> bool:
        """Check if running in development"""
        return self.ENVIRONMENT.lower() == "development"
    
    @property
    def max_upload_size_bytes(self) -> int:
        """Get max upload size in bytes"""
        return self.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    
    def validate_production_settings(self) -> List[str]:
        """Validate settings for production deployment"""
        errors = []
        
        if self.is_production:
            # Check critical production settings
            if self.SECRET_KEY == secrets.token_urlsafe(32):
                errors.append("SECRET_KEY must be set in production")
            
            if "sqlite" in self.DATABASE_URL.lower():
                errors.append("SQLite is not recommended for production. Use PostgreSQL.")
            
            if "*" in self.ALLOWED_ORIGINS or "localhost" in str(self.ALLOWED_ORIGINS):
                errors.append("ALLOWED_ORIGINS must not include '*' or 'localhost' in production")
            
            if not self.SENTRY_ENABLED:
                errors.append("SENTRY_ENABLED should be True in production for error tracking")
            
            if self.DEBUG:
                errors.append("DEBUG must be False in production")
        
        return errors


# Global settings instance
settings = Settings()

# Validate production settings on startup
if settings.is_production:
    errors = settings.validate_production_settings()
    if errors:
        raise ValueError(f"Production configuration errors:\n" + "\n".join(f"- {e}" for e in errors))

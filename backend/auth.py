from datetime import datetime, timedelta
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from database import get_db, User
from config import settings
import re
import logging

logger = logging.getLogger(__name__)

# Use settings from config instead of hardcoded values
SECRET_KEY = settings.SECRET_KEY
ALGORITHM = settings.JWT_ALGORITHM
ACCESS_TOKEN_EXPIRE_HOURS = settings.ACCESS_TOKEN_EXPIRE_HOURS

# Use argon2 instead of bcrypt for better compatibility
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")
security = HTTPBearer()

# Login attempt tracking (in-memory, use Redis in production)
login_attempts = {}  # user_id -> {"count": int, "locked_until": datetime}

def validate_password_strength(password: str) -> tuple[bool, str]:
    """
    Validate password meets security requirements
    Returns: (is_valid, error_message)
    """
    if len(password) < settings.PASSWORD_MIN_LENGTH:
        return False, f"Password must be at least {settings.PASSWORD_MIN_LENGTH} characters long"
    
    if settings.PASSWORD_REQUIRE_UPPERCASE and not re.search(r'[A-Z]', password):
        return False, "Password must contain at least one uppercase letter"
    
    if settings.PASSWORD_REQUIRE_LOWERCASE and not re.search(r'[a-z]', password):
        return False, "Password must contain at least one lowercase letter"
    
    if settings.PASSWORD_REQUIRE_DIGIT and not re.search(r'\d', password):
        return False, "Password must contain at least one digit"
    
    if settings.PASSWORD_REQUIRE_SPECIAL and not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        return False, "Password must contain at least one special character"
    
    return True, ""

def hash_password(password: str) -> str:
    """Hash password using bcrypt"""
    return pwd_context.hash(password)

def verify_password(plain: str, hashed: str) -> bool:
    """Verify password against hash"""
    return pwd_context.verify(plain, hashed)

def check_account_locked(user_id: str) -> tuple[bool, str]:
    """
    Check if account is locked due to failed login attempts
    Returns: (is_locked, message)
    """
    if user_id not in login_attempts:
        return False, ""
    
    attempt_data = login_attempts[user_id]
    locked_until = attempt_data.get("locked_until")
    
    if locked_until and datetime.utcnow() < locked_until:
        remaining = int((locked_until - datetime.utcnow()).total_seconds() / 60)
        return True, f"Account locked. Try again in {remaining} minutes."
    
    # Lock expired, reset
    if locked_until and datetime.utcnow() >= locked_until:
        login_attempts.pop(user_id, None)
        return False, ""
    
    return False, ""

def record_failed_login(user_id: str):
    """Record failed login attempt and lock account if threshold exceeded"""
    if user_id not in login_attempts:
        login_attempts[user_id] = {"count": 0, "locked_until": None}
    
    login_attempts[user_id]["count"] += 1
    
    if login_attempts[user_id]["count"] >= settings.MAX_LOGIN_ATTEMPTS:
        lockout_until = datetime.utcnow() + timedelta(minutes=settings.LOCKOUT_DURATION_MINUTES)
        login_attempts[user_id]["locked_until"] = lockout_until
        logger.warning(f"Account {user_id} locked until {lockout_until} due to failed login attempts")

def reset_login_attempts(user_id: str):
    """Reset login attempts after successful login"""
    login_attempts.pop(user_id, None)

def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security), db: Session = Depends(get_db)):
    payload = decode_token(credentials.credentials)
    user_id = payload.get("sub")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user

def require_role(*roles):
    def checker(current_user: User = Depends(get_current_user)):
        if current_user.role not in roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return current_user
    return checker

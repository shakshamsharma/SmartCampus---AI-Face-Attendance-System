"""
Secure Authentication Module
Implements secure authentication with rate limiting, account lockout, and proper password policies
"""
from datetime import datetime, timedelta
from typing import Optional, Dict
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
import re
import logging

from database import get_db, User
from config import settings

logger = logging.getLogger(__name__)

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# HTTP Bearer security
security = HTTPBearer()

# In-memory store for login attempts (should use Redis in production)
login_attempts: Dict[str, Dict] = {}

# Token blacklist (should use Redis in production)
token_blacklist: set = set()


class PasswordPolicy:
    """Password policy validator"""
    
    MIN_LENGTH = 8
    REQUIRE_UPPERCASE = True
    REQUIRE_LOWERCASE = True
    REQUIRE_DIGIT = True
    REQUIRE_SPECIAL = True
    
    @classmethod
    def validate(cls, password: str) -> tuple[bool, str]:
        """
        Validate password against policy
        
        Returns:
            (is_valid, error_message)
        """
        if len(password) < cls.MIN_LENGTH:
            return False, f"Password must be at least {cls.MIN_LENGTH} characters long"
        
        if cls.REQUIRE_UPPERCASE and not re.search(r'[A-Z]', password):
            return False, "Password must contain at least one uppercase letter"
        
        if cls.REQUIRE_LOWERCASE and not re.search(r'[a-z]', password):
            return False, "Password must contain at least one lowercase letter"
        
        if cls.REQUIRE_DIGIT and not re.search(r'\d', password):
            return False, "Password must contain at least one digit"
        
        if cls.REQUIRE_SPECIAL and not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
            return False, "Password must contain at least one special character"
        
        return True, ""


def hash_password(password: str) -> str:
    """Hash password using bcrypt"""
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    """Verify password against hash"""
    try:
        return pwd_context.verify(plain, hashed)
    except Exception as e:
        logger.error(f"Password verification error: {e}")
        return False


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Create JWT access token
    
    Args:
        data: Token payload
        expires_delta: Optional expiration time
    
    Returns:
        Encoded JWT token
    """
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(hours=settings.ACCESS_TOKEN_EXPIRE_HOURS)
    
    to_encode.update({
        "exp": expire,
        "iat": datetime.utcnow(),
        "type": "access"
    })
    
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    """
    Decode and validate JWT token
    
    Args:
        token: JWT token string
    
    Returns:
        Token payload
    
    Raises:
        HTTPException: If token is invalid or expired
    """
    try:
        # Check if token is blacklisted
        if token in token_blacklist:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has been revoked"
            )
        
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM]
        )
        
        # Validate token type
        if payload.get("type") != "access":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type"
            )
        
        return payload
        
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired"
        )
    except JWTError as e:
        logger.error(f"JWT decode error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    """
    Get current authenticated user from JWT token
    
    Args:
        credentials: HTTP Bearer credentials
        db: Database session
    
    Returns:
        User object
    
    Raises:
        HTTPException: If authentication fails
    """
    payload = decode_token(credentials.credentials)
    user_id = payload.get("sub")
    
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload"
        )
    
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )
    
    return user


def require_role(*roles: str):
    """
    Dependency to require specific user roles
    
    Args:
        *roles: Required roles (e.g., "student", "faculty", "admin")
    
    Returns:
        Dependency function
    """
    def checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in roles:
            logger.warning(
                f"Unauthorized access attempt: user={current_user.id}, "
                f"role={current_user.role}, required={roles}"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required role: {', '.join(roles)}"
            )
        return current_user
    
    return checker


def check_login_attempts(user_id: str, request: Request) -> None:
    """
    Check if user is locked out due to too many failed login attempts
    
    Args:
        user_id: User identifier
        request: FastAPI request object
    
    Raises:
        HTTPException: If user is locked out
    """
    client_ip = request.client.host
    key = f"{user_id}:{client_ip}"
    
    if key in login_attempts:
        attempts = login_attempts[key]
        
        # Check if locked out
        if attempts["locked_until"] and datetime.utcnow() < attempts["locked_until"]:
            remaining = (attempts["locked_until"] - datetime.utcnow()).seconds // 60
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Account locked due to too many failed attempts. Try again in {remaining} minutes."
            )
        
        # Reset if lockout expired
        if attempts["locked_until"] and datetime.utcnow() >= attempts["locked_until"]:
            login_attempts[key] = {"count": 0, "locked_until": None}


def record_failed_login(user_id: str, request: Request) -> None:
    """
    Record failed login attempt and lock account if threshold exceeded
    
    Args:
        user_id: User identifier
        request: FastAPI request object
    """
    client_ip = request.client.host
    key = f"{user_id}:{client_ip}"
    
    if key not in login_attempts:
        login_attempts[key] = {"count": 0, "locked_until": None}
    
    login_attempts[key]["count"] += 1
    
    logger.warning(
        f"Failed login attempt: user={user_id}, ip={client_ip}, "
        f"attempts={login_attempts[key]['count']}"
    )
    
    # Lock account if threshold exceeded
    if login_attempts[key]["count"] >= settings.MAX_LOGIN_ATTEMPTS:
        lockout_until = datetime.utcnow() + timedelta(minutes=settings.LOCKOUT_DURATION_MINUTES)
        login_attempts[key]["locked_until"] = lockout_until
        
        logger.error(
            f"Account locked: user={user_id}, ip={client_ip}, "
            f"locked_until={lockout_until.isoformat()}"
        )


def record_successful_login(user_id: str, request: Request) -> None:
    """
    Record successful login and reset failed attempts
    
    Args:
        user_id: User identifier
        request: FastAPI request object
    """
    client_ip = request.client.host
    key = f"{user_id}:{client_ip}"
    
    # Reset failed attempts
    if key in login_attempts:
        del login_attempts[key]
    
    logger.info(f"Successful login: user={user_id}, ip={client_ip}")


def revoke_token(token: str) -> None:
    """
    Revoke (blacklist) a token
    
    Args:
        token: JWT token to revoke
    """
    token_blacklist.add(token)
    logger.info(f"Token revoked: {token[:20]}...")


def validate_password_strength(password: str) -> None:
    """
    Validate password strength
    
    Args:
        password: Password to validate
    
    Raises:
        HTTPException: If password doesn't meet policy
    """
    is_valid, error_message = PasswordPolicy.validate(password)
    
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_message
        )


# Optional: Implement refresh tokens
def create_refresh_token(data: dict) -> str:
    """
    Create JWT refresh token
    
    Args:
        data: Token payload
    
    Returns:
        Encoded JWT refresh token
    """
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=7)  # Refresh tokens last 7 days
    
    to_encode.update({
        "exp": expire,
        "iat": datetime.utcnow(),
        "type": "refresh"
    })
    
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def refresh_access_token(refresh_token: str, db: Session) -> str:
    """
    Create new access token from refresh token
    
    Args:
        refresh_token: Refresh token
        db: Database session
    
    Returns:
        New access token
    
    Raises:
        HTTPException: If refresh token is invalid
    """
    try:
        payload = jwt.decode(
            refresh_token,
            settings.SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM]
        )
        
        if payload.get("type") != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type"
            )
        
        user_id = payload.get("sub")
        user = db.query(User).filter(User.id == user_id).first()
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found"
            )
        
        # Create new access token
        return create_access_token({
            "sub": user.id,
            "role": user.role,
            "name": user.name
        })
        
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has expired"
        )
    except JWTError as e:
        logger.error(f"Refresh token decode error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token"
        )

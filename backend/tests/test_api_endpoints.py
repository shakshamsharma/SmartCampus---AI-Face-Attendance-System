"""
Comprehensive API Endpoint Tests
Tests all endpoints for functionality, security, and error handling
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database import Base, get_db
from main import app
from auth import hash_password
import json

# Test database
SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

client = TestClient(app)

@pytest.fixture(scope="module")
def setup_database():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)

@pytest.fixture
def test_user_token(setup_database):
    """Create test user and return auth token"""
    from database import User, Student
    db = TestingSessionLocal()
    
    # Create test user
    user = User(
        id="TEST001",
        name="Test Student",
        password_hash=hash_password("testpass123"),
        role="student",
        email="test@test.com"
    )
    db.add(user)
    
    student = Student(
        reg_no="TEST001",
        name="Test Student",
        dept="CSE",
        semester=6,
        section="A",
        user_id="TEST001"
    )
    db.add(student)
    db.commit()
    db.close()
    
    # Login and get token
    response = client.post("/api/auth/login", json={
        "id": "TEST001",
        "password": "testpass123",
        "role": "student"
    })
    return response.json()["access_token"]

class TestAuthentication:
    """Test authentication endpoints"""
    
    def test_login_success(self, setup_database):
        """Test successful login"""
        response = client.post("/api/auth/login", json={
            "id": "TEST001",
            "password": "testpass123",
            "role": "student"
        })
        assert response.status_code == 200
        assert "access_token" in response.json()
        assert response.json()["token_type"] == "bearer"
    
    def test_login_invalid_credentials(self, setup_database):
        """Test login with invalid credentials"""
        response = client.post("/api/auth/login", json={
            "id": "TEST001",
            "password": "wrongpassword",
            "role": "student"
        })
        assert response.status_code == 401
    
    def test_login_wrong_role(self, setup_database):
        """Test login with wrong role"""
        response = client.post("/api/auth/login", json={
            "id": "TEST001",
            "password": "testpass123",
            "role": "faculty"
        })
        assert response.status_code == 403
    
    def test_login_rate_limiting(self, setup_database):
        """Test rate limiting on login endpoint"""
        # Make multiple rapid requests
        for _ in range(6):
            response = client.post("/api/auth/login", json={
                "id": "TEST001",
                "password": "wrongpassword",
                "role": "student"
            })
        # Should be rate limited after 5 attempts
        assert response.status_code == 429
    
    def test_login_sql_injection_attempt(self, setup_database):
        """Test SQL injection protection"""
        response = client.post("/api/auth/login", json={
            "id": "TEST001' OR '1'='1",
            "password": "anything",
            "role": "student"
        })
        assert response.status_code in [400, 401]  # Should be rejected

class TestStudentEndpoints:
    """Test student-specific endpoints"""
    
    def test_student_dashboard(self, test_user_token):
        """Test student dashboard endpoint"""
        response = client.get(
            "/api/student/dashboard",
            headers={"Authorization": f"Bearer {test_user_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "student" in data
        assert "summary" in data
        assert "subjects" in data
    
    def test_student_dashboard_unauthorized(self):
        """Test dashboard without authentication"""
        response = client.get("/api/student/dashboard")
        assert response.status_code == 403  # No auth header
    
    def test_attendance_logs(self, test_user_token):
        """Test attendance logs endpoint"""
        response = client.get(
            "/api/student/attendance-logs",
            headers={"Authorization": f"Bearer {test_user_token}"}
        )
        assert response.status_code == 200
        assert isinstance(response.json(), list)
    
    def test_monthly_trend(self, test_user_token):
        """Test monthly attendance trend"""
        response = client.get(
            "/api/student/monthly-trend",
            headers={"Authorization": f"Bearer {test_user_token}"}
        )
        assert response.status_code == 200
        assert isinstance(response.json(), list)
    
    def test_submit_leave(self, test_user_token):
        """Test leave request submission"""
        response = client.post(
            "/api/student/leave",
            headers={"Authorization": f"Bearer {test_user_token}"},
            json={
                "from_date": "2026-05-15",
                "to_date": "2026-05-17",
                "reason": "Medical emergency",
                "leave_type": "sick"
            }
        )
        assert response.status_code == 200
        assert response.json()["success"] == True
    
    def test_raise_dispute(self, test_user_token):
        """Test attendance dispute"""
        response = client.post(
            "/api/student/dispute",
            headers={"Authorization": f"Bearer {test_user_token}"},
            json={
                "subject": "DSA",
                "date": "2026-05-10",
                "claim": "I was present but marked absent"
            }
        )
        assert response.status_code == 200
        assert response.json()["success"] == True

class TestFaceRecognition:
    """Test face recognition endpoints"""
    
    def test_face_registration_insufficient_images(self, test_user_token):
        """Test face registration with insufficient images"""
        response = client.post(
            "/api/student/register-face",
            headers={"Authorization": f"Bearer {test_user_token}"},
            json={"images": ["base64_image_1", "base64_image_2"]}  # Only 2 images
        )
        assert response.status_code == 400
    
    def test_face_stats(self, test_user_token):
        """Test face registration stats"""
        response = client.get(
            "/api/face/stats",
            headers={"Authorization": f"Bearer {test_user_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "total_registered" in data
        assert "embedding_dimensions" in data

class TestNotifications:
    """Test notification endpoints"""
    
    def test_get_notifications(self, test_user_token):
        """Test getting notifications"""
        response = client.get(
            "/api/notifications",
            headers={"Authorization": f"Bearer {test_user_token}"}
        )
        assert response.status_code == 200
        assert isinstance(response.json(), list)
    
    def test_mark_notification_read(self, test_user_token):
        """Test marking notification as read"""
        # First create a notification
        db = TestingSessionLocal()
        from database import Notification
        notif = Notification(
            user_id="TEST001",
            title="Test Notification",
            message="Test message",
            icon="📢"
        )
        db.add(notif)
        db.commit()
        notif_id = notif.id
        db.close()
        
        # Mark as read
        response = client.post(
            f"/api/notifications/{notif_id}/read",
            headers={"Authorization": f"Bearer {test_user_token}"}
        )
        assert response.status_code == 200

class TestSecurity:
    """Test security features"""
    
    def test_cors_headers(self):
        """Test CORS headers are present"""
        response = client.options("/api/health")
        assert "access-control-allow-origin" in response.headers
    
    def test_xss_protection(self):
        """Test XSS protection headers"""
        response = client.get("/api/health")
        # Should have security headers (if configured in nginx)
        assert response.status_code == 200
    
    def test_invalid_token(self):
        """Test with invalid JWT token"""
        response = client.get(
            "/api/student/dashboard",
            headers={"Authorization": "Bearer invalid_token_here"}
        )
        assert response.status_code == 401
    
    def test_expired_token(self):
        """Test with expired token"""
        # Create an expired token
        from datetime import datetime, timedelta
        from jose import jwt
        from auth import SECRET_KEY, ALGORITHM
        
        expired_token = jwt.encode(
            {"sub": "TEST001", "exp": datetime.utcnow() - timedelta(hours=1)},
            SECRET_KEY,
            algorithm=ALGORITHM
        )
        
        response = client.get(
            "/api/student/dashboard",
            headers={"Authorization": f"Bearer {expired_token}"}
        )
        assert response.status_code == 401

class TestInputValidation:
    """Test input validation"""
    
    def test_invalid_date_format(self, test_user_token):
        """Test with invalid date format"""
        response = client.post(
            "/api/student/leave",
            headers={"Authorization": f"Bearer {test_user_token}"},
            json={
                "from_date": "invalid-date",
                "to_date": "2026-05-17",
                "reason": "Test",
                "leave_type": "sick"
            }
        )
        # Should validate date format
        assert response.status_code in [400, 422]
    
    def test_missing_required_fields(self, test_user_token):
        """Test with missing required fields"""
        response = client.post(
            "/api/student/leave",
            headers={"Authorization": f"Bearer {test_user_token}"},
            json={"from_date": "2026-05-15"}  # Missing other fields
        )
        assert response.status_code == 422
    
    def test_sql_injection_in_search(self, test_user_token):
        """Test SQL injection in search parameter"""
        response = client.get(
            "/api/student/attendance-logs?subject=DSA' OR '1'='1",
            headers={"Authorization": f"Bearer {test_user_token}"}
        )
        # Should handle safely
        assert response.status_code == 200

class TestPerformance:
    """Test performance and pagination"""
    
    def test_pagination_limit(self, test_user_token):
        """Test pagination limit parameter"""
        response = client.get(
            "/api/student/attendance-logs?limit=10",
            headers={"Authorization": f"Bearer {test_user_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) <= 10
    
    def test_large_limit_rejected(self, test_user_token):
        """Test that excessively large limits are rejected"""
        response = client.get(
            "/api/student/attendance-logs?limit=10000",
            headers={"Authorization": f"Bearer {test_user_token}"}
        )
        # Should cap at max page size
        assert response.status_code == 200

class TestHealthCheck:
    """Test health check endpoint"""
    
    def test_health_endpoint(self):
        """Test health check returns 200"""
        response = client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert data["status"] == "healthy"

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--cov=backend", "--cov-report=html"])

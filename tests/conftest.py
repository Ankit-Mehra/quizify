import pytest
from unittest.mock import Mock, patch
import os

os.environ["SUPABASE_URL"] = "https://test.supabase.co"
os.environ["SUPABASE_KEY"] = "test_key"
os.environ["SUPABASE_STORAGE_NAME"] = "test-bucket"
os.environ["OPENAI_API_KEY"] = "sk-test123"
os.environ["TESTING"] = "true"

class MockSupabaseAuth:
    def __init__(self):
        self._registered_emails = set()
    
    def sign_up(self, credentials):
        email = credentials.get("email", "")
        password = credentials.get("password", "")
        
        if not email or "@" not in email:
            raise Exception(f"Email address \"{email}\" is invalid")
        
        if email in self._registered_emails:
            raise Exception("User already registered")
        
        if len(password) < 6:
            raise Exception("Password should be at least 6 characters")
        
        self._registered_emails.add(email)
        
        return Mock(
            user=Mock(id="mock_user_123", email=email),
            session=Mock(access_token="mock_access_token_abc123", refresh_token="mock_refresh")
        )
    
    def sign_in_with_password(self, credentials):
        email = credentials.get("email", "")
        password = credentials.get("password", "")
        
        if not email or not password:
            raise Exception("Invalid login credentials")
        
        if email == "test@example.com" and password != "SecurePass123!":
            raise Exception("Invalid login credentials")
        
        if email.startswith("nonexistent_"):
            raise Exception("Invalid login credentials")
        
        return Mock(
            user=Mock(id="mock_user_123", email=email),
            session=Mock(access_token="mock_access_token_abc123", refresh_token="mock_refresh")
        )

class MockSupabaseClient:
    def __init__(self):
        self.auth = MockSupabaseAuth()

@pytest.fixture
def mock_supabase():
    return MockSupabaseClient()

@pytest.fixture
def mock_supabase_client(mock_supabase):
    from main import app
    from dependencies.auth_dependencies import get_current_user_id, get_current_user_token
    
    def mock_save_file_to_supabase(*args, **kwargs):
        return {"message": "File uploaded successfully"}
    
    def mock_delete_file_from_supabase(*args, **kwargs):
        return {"message": "File deleted successfully"}
    
    async def mock_generate_quizzes_single_async(text, num_questions, question_types=None):
        """Mock AI quiz generation"""
        return [
            {
                "id": f"q{i}",
                "type": "multiple_choice",
                "question": f"Question {i}?",
                "options": ["A", "B", "C", "D"],
                "correct_answer": "A",
                "explanation": f"Explanation for question {i}",
                "source": "mock"
            }
            for i in range(1, min(int(num_questions) + 1, 6))
        ]
    
    def mock_save_quiz_to_database(title, quizzes, user_id):
        """Mock saving quiz to database"""
        return "mock_quiz_123"
    
    def mock_save_metadata(metadata):
        """Mock saving metadata"""
        return {"success": True}
    
    # Helper functions for tests that need to bypass auth
    def bypass_auth_get_user_id():
        return "mock_user_123"
    
    def bypass_auth_get_token():
        return "mock_access_token_abc123"
    
    # Provide bypass functions as attributes for tests to use
    app.mock_bypass_auth_user_id = bypass_auth_get_user_id
    app.mock_bypass_auth_token = bypass_auth_get_token
    
    with patch("handlers.auth_handlers.supabase", mock_supabase):
        with patch("handlers.file_handlers.save_file_to_supabase", side_effect=mock_save_file_to_supabase):
            with patch("handlers.file_handlers.delete_file_from_supabase", side_effect=mock_delete_file_from_supabase):
                # Patch where the function is USED, not where it's defined
                with patch("handlers.quiz_handlers.generate_quizzes_single_async", side_effect=mock_generate_quizzes_single_async):
                    with patch("handlers.quiz_handlers.save_quiz_to_database", side_effect=mock_save_quiz_to_database):
                        with patch("handlers.quiz_handlers.save_metadata", side_effect=mock_save_metadata):
                            with patch("handlers.quiz_handlers.save_file_to_supabase", side_effect=mock_save_file_to_supabase):
                                yield mock_supabase
    
    # Clear dependency overrides after test
    app.dependency_overrides.clear()

@pytest.fixture
def auth_bypass(mock_supabase_client):
    """Fixture that bypasses authentication for tests that need it (like quiz generation tests)"""
    from main import app
    from dependencies.auth_dependencies import get_current_user_id, get_current_user_token
    
    def mock_get_current_user_id():
        return "mock_user_123"
    
    def mock_get_current_user_token():
        return "mock_access_token_abc123"
    
    # Set up overrides
    app.dependency_overrides[get_current_user_id] = mock_get_current_user_id
    app.dependency_overrides[get_current_user_token] = mock_get_current_user_token
    
    yield
    
    # Clear overrides
    app.dependency_overrides.clear()

@pytest.fixture
def reset_auth_state(mock_supabase_client):
    """Reset auth state before each test - only used when mock_supabase_client is used."""
    mock_supabase_client.auth._registered_emails.clear()
    yield
    mock_supabase_client.auth._registered_emails.clear()

@pytest.fixture
def test_user_data():
    return {
        "email": "test@example.com",
        "password": "SecurePass123!",
        "name": "Test User"
    }

@pytest.fixture
def mock_auth_token():
    return "mock_access_token_abc123"

@pytest.fixture
def auth_headers(mock_auth_token):
    return {"Authorization": f"Bearer {mock_auth_token}"}

import pytest
from unittest.mock import Mock
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
        self._mock_data = {}
        # Pre-populate default user tier data for testing
        self._default_tier_data = {
            "user_tier_info": [
                {
                    "id": "mock_user_123",
                    "email": "test@example.com",
                    "account_tier": "free",
                    "current_quiz_count": 0,
                    "quota_limit": 5,
                    "quota_exceeded": False
                }
            ],
            "profiles": [
                {
                    "id": "mock_user_123",
                    "email": "test@example.com",
                    "account_tier": "free",
                    "is_admin": False
                }
            ]
        }
    
    def table(self, table_name):
        """Return a mock table interface with realistic data."""
        mock_table = Mock()
        
        # Store the table name and query context
        mock_table._table_name = table_name
        mock_table._filters = {}
        
        def mock_select(columns="*"):
            """Mock select operation"""
            mock_table._columns = columns
            return mock_table
        
        def mock_eq(column, value):
            """Mock equality filter"""
            mock_table._filters[column] = value
            return mock_table
        
        def mock_execute():
            """Mock execute - returns appropriate data based on table and filters"""
            mock_result = Mock()
            
            # Get data for this table (default to empty)
            table_data = self._default_tier_data.get(table_name, [])
            
            # Apply filters if any
            if mock_table._filters:
                filtered_data = []
                for row in table_data:
                    match = all(
                        row.get(col) == val 
                        for col, val in mock_table._filters.items()
                    )
                    if match:
                        filtered_data.append(row)
                mock_result.data = filtered_data
            else:
                mock_result.data = table_data
            
            mock_result.count = len(mock_result.data)
            return mock_result
        
        # Setup method chaining
        mock_table.select = mock_select
        mock_table.insert.return_value = mock_table
        mock_table.update.return_value = mock_table
        mock_table.delete.return_value = mock_table
        mock_table.eq = mock_eq
        mock_table.in_.return_value = mock_table
        mock_table.execute = mock_execute
        
        return mock_table

@pytest.fixture
def mock_supabase():
    return MockSupabaseClient()

@pytest.fixture
def mock_supabase_client(mock_supabase, mocker):
    """
    Mock Supabase client with all necessary service patches.
    Uses pytest-mock's mocker fixture for cleaner test setup.
    """
    from main import app
    
    # Define mock implementations
    def mock_save_file_to_supabase(*args, **kwargs):
        return {"message": "File uploaded successfully"}
    
    def mock_delete_file_from_supabase(*args, **kwargs):
        return {"message": "File deleted successfully"}
    
    async def mock_generate_quizzes_single_async(text, num_questions, question_types=None):
        """Mock AI quiz generation"""
        return [
            {
                "type": "multiple_choice",
                "question": f"Question {i}?",
                "options": ["A", "B", "C", "D"],
                "correct_answer": "A",
                "explanation": f"Explanation for question {i}",
                "source": "mock"
            }
            for i in range(1, min(int(num_questions) + 1, 6))
        ]
    
    def mock_save_quiz_to_database(title, quizzes, created_by, content_source_type=None, content_source_reference=None, user_token=None):
        """Mock saving quiz to database - returns (quiz_id, saved_questions) tuple"""
        import uuid
        # Generate a proper UUID for quiz_id
        quiz_id = str(uuid.uuid4())
        
        # Add IDs to questions to match real database behavior
        saved_questions = []
        for i, q in enumerate(quizzes):
            question_with_id = q.copy() if isinstance(q, dict) else q.model_dump()
            question_with_id['id'] = str(uuid.uuid4())  # Generate proper UUID
            question_with_id['quiz_id'] = quiz_id
            saved_questions.append(question_with_id)
        return quiz_id, saved_questions
    
    def mock_save_metadata(metadata, user_token=None):
        """Mock saving metadata - now accepts optional user_token parameter"""
        return {"success": True}
    
    # Apply all patches using mocker (pytest-mock)
    # NEW PATTERN: Mock get_supabase() functions instead of module-level variables
    mocker.patch("handlers.auth_handlers.get_supabase", return_value=mock_supabase)
    mocker.patch("services.db_services.supabase_quiz.get_supabase", return_value=mock_supabase)
    mocker.patch("services.db_services.supabase_file.get_supabase", return_value=mock_supabase)
    mocker.patch("services.db_services.supabase_submission.get_supabase", return_value=mock_supabase)
    
    # Keep function-level mocks
    mocker.patch("handlers.file_handlers.save_file_to_supabase", side_effect=mock_save_file_to_supabase)
    mocker.patch("handlers.file_handlers.delete_file_from_supabase", side_effect=mock_delete_file_from_supabase)
    mocker.patch("handlers.quiz_handlers.generate_quizzes_single_async", side_effect=mock_generate_quizzes_single_async)
    mocker.patch("handlers.quiz_handlers.save_quiz_to_database", side_effect=mock_save_quiz_to_database)
    mocker.patch("handlers.quiz_handlers.save_metadata", side_effect=mock_save_metadata)
    mocker.patch("handlers.quiz_handlers.save_file_to_supabase", side_effect=mock_save_file_to_supabase)
    
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

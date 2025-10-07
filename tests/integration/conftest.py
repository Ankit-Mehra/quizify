"""
Integration test fixtures.

Sets up comprehensive mocks for Supabase and AI services 
to enable integration testing without real external dependencies.
"""

import pytest
from unittest.mock import Mock, patch

# Mock Supabase responses for integration tests
class MockSupabaseAuthResponse:
    def __init__(self, user_id, email):
        self.user = Mock(id=user_id, email=email)
        self.session = Mock(
            access_token=f"mock_token_{user_id}", 
            refresh_token=f"mock_refresh_{user_id}"
        )


class MockSupabaseAuth:
    """Mock Supabase auth for integration tests."""
    
    def __init__(self):
        self._users = {}  # email -> (user_id, password)
        self._next_user_id = 1000
    
    def sign_up(self, credentials):
        """Mock user signup."""
        email = credentials.get("email", "")
        password = credentials.get("password", "")
        
        if not email or "@" not in email:
            raise Exception(f"Email address \"{email}\" is invalid")
        
        if email in self._users:
            raise Exception("User already registered")
        
        if len(password) < 6:
            raise Exception("Password should be at least 6 characters")
        
        user_id = f"user_{self._next_user_id}"
        self._next_user_id += 1
        self._users[email] = (user_id, password)
        
        return MockSupabaseAuthResponse(user_id, email)
    
    def sign_in_with_password(self, credentials):
        """Mock user login."""
        email = credentials.get("email", "")
        password = credentials.get("password", "")
        
        if not email or not password:
            raise Exception("Invalid login credentials")
        
        if email not in self._users:
            raise Exception("Invalid login credentials")
        
        user_id, stored_password = self._users[email]
        if password != stored_password:
            raise Exception("Invalid login credentials")
        
        return MockSupabaseAuthResponse(user_id, email)
    
    def sign_out(self):
        """Mock user logout."""
        return Mock()
    
    def get_user(self, jwt):
        """Mock get user from token."""
        # For integration tests, just return a mock user
        return Mock(user=Mock(id="mock_user_123", email="test@example.com"))


class MockSupabaseStorage:
    """Mock Supabase storage for integration tests."""
    
    def __init__(self):
        self._files = {}  # file_id -> file_data
    
    def from_(self, bucket_name):
        """Return self to allow method chaining."""
        self.bucket_name = bucket_name
        return self
    
    def upload(self, path, file_data, file_options=None):
        """Mock file upload."""
        file_id = f"file_{len(self._files) + 1}"
        self._files[file_id] = {
            "path": path,
            "data": file_data,
            "bucket": self.bucket_name
        }
        return Mock(path=path)
    
    def remove(self, paths):
        """Mock file removal."""
        return Mock()
    
    def get_public_url(self, path):
        """Mock get public URL."""
        return f"https://mock-storage.supabase.co/{self.bucket_name}/{path}"


class MockSupabaseTable:
    """Mock Supabase table operations."""
    
    def __init__(self, table_name):
        self.table_name = table_name
        self._data = []
        self._query: dict = {}
    
    def select(self, *args, **kwargs):
        """Mock select query."""
        self._query = {"operation": "select"}
        return self
    
    def insert(self, data, **kwargs):
        """Mock insert query."""
        if isinstance(data, list):
            self._data.extend(data)
        else:
            self._data.append(data)
        self._query = {"operation": "insert", "data": data}
        return self
    
    def update(self, data):
        """Mock update query."""
        self._query = {"operation": "update", "data": data}
        return self
    
    def delete(self):
        """Mock delete query."""
        self._query = {"operation": "delete"}
        return self
    
    def eq(self, column, value):
        """Mock equality filter."""
        self._query["filter"] = {column: value}  # type: ignore
        return self
    
    def execute(self):
        """Mock execute query."""
        return Mock(
            data=self._data if self._data else [{"id": "mock_123"}],
            error=None
        )


class MockSupabaseClient:
    """Mock Supabase client for integration tests."""
    
    def __init__(self):
        self.auth = MockSupabaseAuth()
        self.storage = MockSupabaseStorage()
        self._tables = {}
    
    def table(self, table_name):
        """Mock table accessor."""
        if table_name not in self._tables:
            self._tables[table_name] = MockSupabaseTable(table_name)
        return self._tables[table_name]


# Mock AI services
async def mock_generate_quizzes_single_async(text, num_questions, question_types=None):
    """Mock OpenAI quiz generation."""
    import uuid
    return [
        {
            "id": str(uuid.uuid4()),
            "type": "multiple_choice",
            "question": f"Sample question {i} about: {text[:50]}?",
            "options": ["Option A", "Option B", "Option C", "Option D"],
            "correct_answer": "Option A",
            "explanation": f"Explanation for question {i}",
            "source": "mock_ai"
        }
        for i in range(1, min(int(num_questions) + 1, 11))
    ]


def mock_save_quiz_to_database(title, quizzes, user_id):
    """Mock saving quiz to database."""
    import uuid
    quiz_id = str(uuid.uuid4())
    # Store the quiz so we can retrieve it later
    if not hasattr(mock_save_quiz_to_database, '_quizzes'):
        mock_save_quiz_to_database._quizzes = {}
    mock_save_quiz_to_database._quizzes[quiz_id] = {
        "id": quiz_id,
        "title": title,
        "questions": quizzes,
        "user_id": user_id,
        "created_by": user_id,
        "created_at": "2025-10-04T00:00:00"
    }
    return quiz_id


def mock_save_file_to_supabase(*args, **kwargs):
    """Mock file upload to storage."""
    return {"message": "File uploaded successfully", "file_id": "mock_file_123"}


def mock_save_metadata(metadata):
    """Mock saving quiz metadata."""
    return {"success": True, "quiz_id": "mock_quiz_123"}


def mock_requests_get(url, headers=None, **kwargs):
    """Mock requests.get for auth verification."""
    if "/auth/v1/user" in url:
        # Extract token from headers
        auth_header = headers.get("Authorization", "") if headers else ""
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            # Reject invalid tokens (anything with "invalid" in it or too short)
            if "invalid" in token.lower() or len(token) < 20:
                return Mock(
                    status_code=401,
                    json=lambda: {"error": "Invalid token"},
                    raise_for_status=lambda: None
                )
            # Accept all other tokens (should be real-looking tokens from login)
            return Mock(
                status_code=200,
                json=lambda: {"id": "mock_user_123", "email": "test@example.com"},
                raise_for_status=lambda: None
            )
        return Mock(
            status_code=401,
            json=lambda: {"error": "Invalid token"},
            raise_for_status=lambda: None
        )
    # For other URLs, return a generic success
    return Mock(status_code=200, json=lambda: {}, raise_for_status=lambda: None)


def mock_get_user_quizzes(user_id):
    """Mock getting user quizzes."""
    # Return all quizzes stored in mock_save_quiz_to_database
    if hasattr(mock_save_quiz_to_database, '_quizzes'):
        return [
            {
                "id": quiz["id"],
                "title": quiz["title"],
                "created_by": quiz["user_id"],
                "created_at": quiz["created_at"],
                "question_count": len(quiz["questions"])
            }
            for quiz in mock_save_quiz_to_database._quizzes.values()
        ]
    return []


def mock_get_quiz_from_database(quiz_id, user_id=None):
    """Mock getting quiz from database."""
    # Try to get the actual quiz if it was saved
    if hasattr(mock_save_quiz_to_database, '_quizzes') and quiz_id in mock_save_quiz_to_database._quizzes:
        quiz = mock_save_quiz_to_database._quizzes[quiz_id]
        # Ensure created_by is set
        if 'created_by' not in quiz:
            quiz['created_by'] = quiz.get('user_id', 'mock_user_123')
        return quiz
    
    # Fallback to generic mock data
    return {
        "id": quiz_id,
        "title": "Mock Quiz",
        "created_by": user_id or "mock_user_123",
        "questions": [
            {
                "id": f"q{i}",
                "type": "multiple_choice",
                "question": f"Question {i}?",
                "options": ["A", "B", "C", "D"],
                "correct_answer": "A",
                "explanation": f"Explanation {i}"
            }
            for i in range(1, 7)
        ],
        "created_at": "2025-10-04T00:00:00"
    }


@pytest.fixture(scope="module", autouse=True)
def setup_integration_mocks():
    """
    Auto-applied fixture that sets up all mocks for integration tests.
    
    This runs once per test module and patches all external dependencies.
    Uses context managers stacked with contextlib for cleaner setup.
    """
    from contextlib import ExitStack
    
    mock_supabase = MockSupabaseClient()
    
    # Use ExitStack to manage multiple patches without deep nesting
    with ExitStack() as stack:
        stack.enter_context(patch("handlers.auth_handlers.supabase", mock_supabase))
        stack.enter_context(patch("dependencies.auth_dependencies.requests.get", side_effect=mock_requests_get))
        stack.enter_context(patch("handlers.quiz_handlers.generate_quizzes_single_async", side_effect=mock_generate_quizzes_single_async))
        stack.enter_context(patch("handlers.quiz_handlers.save_quiz_to_database", side_effect=mock_save_quiz_to_database))
        stack.enter_context(patch("handlers.quiz_handlers.get_user_quizzes", side_effect=mock_get_user_quizzes))
        stack.enter_context(patch("handlers.quiz_handlers.get_quiz_from_database", side_effect=mock_get_quiz_from_database))
        stack.enter_context(patch("handlers.quiz_handlers.save_file_to_supabase", side_effect=mock_save_file_to_supabase))
        stack.enter_context(patch("handlers.quiz_handlers.save_metadata", side_effect=mock_save_metadata))
        stack.enter_context(patch("handlers.file_handlers.save_file_to_supabase", side_effect=mock_save_file_to_supabase))
        
        yield mock_supabase

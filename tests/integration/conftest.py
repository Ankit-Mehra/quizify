"""
Integration test fixtures.

Sets up comprehensive mocks for Supabase and AI services 
to enable integration testing without real external dependencies.
"""

import pytest
from fastapi import HTTPException
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
        
        if len(password) < 8:
            raise Exception("Password should be at least 8 characters")
        
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
        
        response = MockSupabaseAuthResponse(user_id, email)
        
        # Register token mapping for auth verification
        _token_user_map[response.session.access_token] = {
            "id": user_id,
            "email": email
        }
        
        return response
    
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
    
    def __init__(self, table_name, quiz_storage=None):
        self.table_name = table_name
        self._data = []
        self._query: dict = {}
        self._quiz_storage = quiz_storage
        # Default tier data for user_tier_info queries
        if table_name == "user_tier_info":
            self._data = [
                {
                    "id": "mock_user_123",
                    "email": "test@example.com",
                    "account_tier": "free",
                    "current_quiz_count": 0,
                    "quizzes_attempted": 0,
                    "quota_limit": 5,
                    "quota_exceeded": False
                }
            ]
    
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
        # Special handling for questions table - fetch from quiz storage
        if self.table_name == "questions" and "filter" in self._query:
            filter_col, filter_val = list(self._query["filter"].items())[0]
            if filter_col == "quiz_id" and self._quiz_storage:
                quiz = self._quiz_storage.get_quiz(filter_val)
                if quiz:
                    return Mock(
                        data=quiz.get("questions", []),
                        error=None,
                        count=len(quiz.get("questions", []))
                    )
        
        # Apply filter if specified
        result_data = self._data
        if "filter" in self._query:
            filter_col, filter_val = list(self._query["filter"].items())[0]
            result_data = [row for row in self._data if row.get(filter_col) == filter_val]
        
        # If no data and not a specific table, return default
        if not result_data and self.table_name not in ["user_tier_info", "questions"]:
            result_data = [{"id": "mock_123"}]

        return Mock(
            data=result_data,
            error=None,
            count=len(result_data)
        )


class MockSupabaseClient:
    """Mock Supabase client for integration tests."""
    
    def __init__(self, quiz_storage=None):
        self.auth = MockSupabaseAuth()
        self.storage = MockSupabaseStorage()
        self._tables = {}
        self._quiz_storage = quiz_storage
    
    def table(self, table_name):
        """Mock table accessor."""
        if table_name not in self._tables:
            self._tables[table_name] = MockSupabaseTable(table_name, self._quiz_storage)
        return self._tables[table_name]


class MockQuizStorage:
    """
    Mock quiz storage for integration tests.
    
    Thread-safe storage for quiz data that can be shared across test functions.
    Uses a class-based approach instead of function attributes for better maintainability.
    """
    
    def __init__(self):
        self._quizzes = {}  # quiz_id -> quiz_data
    
    def save_quiz(self, title, quizzes, created_by, content_source_type=None, content_source_reference=None):
        """Save a quiz and return tuple of (quiz_id, saved_questions)."""
        import uuid
        quiz_id = str(uuid.uuid4())
        
        # Add IDs to questions to match real database behavior
        saved_questions = []
        for i, q in enumerate(quizzes):
            question_with_id = q.copy() if isinstance(q, dict) else q.model_dump()
            question_with_id['id'] = str(uuid.uuid4())  # Generate proper UUID
            question_with_id['quiz_id'] = quiz_id
            saved_questions.append(question_with_id)
        
        self._quizzes[quiz_id] = {
            "id": quiz_id,
            "title": title,
            "questions": saved_questions,
            "user_id": created_by,
            "created_by": created_by,
            "created_at": "2025-10-04T00:00:00",
            "content_source_type": content_source_type,
            "content_source_reference": content_source_reference
        }
        return quiz_id, saved_questions
    
    def get_quiz(self, quiz_id, user_id=None):
        """Get a quiz by ID."""
        if quiz_id in self._quizzes:
            quiz = self._quizzes[quiz_id]
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
                    "type": "multiple_choice",
                    "question": f"Question {i}?",
                    "options": ["A", "B", "C", "D"],
                    "correct_answer": "A",
                    "explanation": f"Explanation {i}",
                    "source": "mock"
                }
                for i in range(1, 7)
            ],
            "created_at": "2025-10-04T00:00:00"
        }
    
    def get_user_quizzes(self, user_id):
        """Get all quizzes for a user."""
        return [
            {
                "id": quiz["id"],
                "title": quiz["title"],
                "created_by": quiz["user_id"],
                "created_at": quiz["created_at"],
                "question_count": len(quiz["questions"])
            }
            for quiz in self._quizzes.values()
            if quiz.get("user_id") == user_id
        ]
    
    def clear(self):
        """Clear all stored quizzes."""
        self._quizzes.clear()


# Module-level quiz storage instance
_quiz_storage = MockQuizStorage()


# Utility function for tests to create deterministic mock responses
def create_mock_quiz_response(num_questions, question_types=None, text="sample text"):
    """
    Create a deterministic mock quiz response for testing.
    
    Use this in tests when you need exact control over the number of questions:
    
    Example:
        # Test 75% threshold failure
        with patch("handlers.quiz_handlers.generate_quizzes_single_async", 
                   return_value=create_mock_quiz_response(7)):  # 7/10 = 70% < 75%
            response = client.post("/api/quizzes/generate-text", ...)
    
    Args:
        num_questions: Exact number of questions to return
        question_types: List of question types or single type
        text: Text snippet for question content
    
    Returns:
        List of mock question dictionaries
    """
    import uuid
    
    if question_types:
        types_to_use = question_types if isinstance(question_types, list) else [question_types]
        question_type_list = [types_to_use[i % len(types_to_use)] for i in range(num_questions)]
    else:
        question_type_list = ["multiple_choice"] * num_questions
    
    questions = []
    for i in range(num_questions):
        qtype = question_type_list[i]
        question = {
            "id": str(uuid.uuid4()),
            "type": qtype,
            "question": f"Sample question {i+1} about: {text[:50]}?",
            "explanation": f"Explanation for question {i+1}",
            "source": "mock_ai"
        }
        
        # Add type-specific fields
        if qtype == "multiple_choice":
            question["options"] = ["Option A", "Option B", "Option C", "Option D"]
            question["correct_answer"] = "Option A"
        elif qtype == "true_false":
            question["options"] = None
            question["correct_answer"] = True
        elif qtype == "fill_blank":
            question["options"] = ["blank1", "blank2", "blank3"]
            question["correct_answer"] = "blank1"
        elif qtype == "matching":
            question["left"] = ["Item 1", "Item 2"]
            question["right"] = ["Match A", "Match B"]
            question["correct_answer"] = [["Item 1", "Match A"], ["Item 2", "Match B"]]
            question["options"] = None
        
        questions.append(question)
    
    return questions


# Mock AI services
async def mock_generate_quizzes_single_async(text, num_questions, question_types=None):
    """
    Mock OpenAI quiz generation.
    
    Default behavior: Returns exactly min(num_questions, 10) questions for predictable tests.
    
    For edge case testing (e.g., 75% threshold), patch this function in your test
    using create_mock_quiz_response() to get exact control over question count.
    
    Example:
        # Test 75% threshold failure (7 out of 10 = 70%)
        with patch("handlers.quiz_handlers.generate_quizzes_single_async",
                   return_value=create_mock_quiz_response(7)):
            response = client.post(...)
    """
    import uuid
    
    # Default: return exactly what was requested (up to 10)
    requested = int(num_questions)
    actual_count = min(requested, 10)
    
    # Determine question types to generate
    if question_types:
        # question_types is a list from FastAPI Form parameter
        types_to_use = question_types if isinstance(question_types, list) else [question_types]
        question_type_list = [types_to_use[i % len(types_to_use)] for i in range(actual_count)]
    else:
        question_type_list = ["multiple_choice"] * actual_count
    
    questions = []
    for i in range(actual_count):
        qtype = question_type_list[i]
        question = {
            "id": str(uuid.uuid4()),
            "type": qtype,
            "question": f"Sample question {i+1} about: {text[:50]}?",
            "explanation": f"Explanation for question {i+1}",
            "source": "mock_ai"
        }
        
        # Add type-specific fields
        if qtype == "multiple_choice":
            question["options"] = ["Option A", "Option B", "Option C", "Option D"]
            question["correct_answer"] = "Option A"
        elif qtype == "true_false":
            question["options"] = None
            question["correct_answer"] = True  # Boolean for true/false
        elif qtype == "fill_blank":
            question["options"] = ["blank1", "blank2", "blank3"]
            question["correct_answer"] = "blank1"
        elif qtype == "matching":
            question["left"] = ["Item 1", "Item 2"]
            question["right"] = ["Match A", "Match B"]
            question["correct_answer"] = [["Item 1", "Match A"], ["Item 2", "Match B"]]
            question["options"] = None
        
        questions.append(question)
    
    return questions


def mock_save_quiz_to_database(title, quizzes, created_by, content_source_type=None, content_source_reference=None, user_token=None):
    """Mock saving quiz to database - returns (quiz_id, saved_questions) tuple."""
    return _quiz_storage.save_quiz(title, quizzes, created_by, content_source_type, content_source_reference)


def mock_save_file_to_supabase(*args, **kwargs):
    """Mock file upload to storage."""
    return {"message": "File uploaded successfully", "file_id": "mock_file_123"}


def mock_save_metadata(metadata, user_token=None):
    """Mock saving quiz metadata - now accepts optional user_token parameter."""
    return {"success": True, "quiz_id": "mock_quiz_123"}


# Module-level token-to-user mapping for mock auth
_token_user_map = {}

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
            # Look up user from token mapping (set during login)
            if token in _token_user_map:
                user_data = _token_user_map[token]
                return Mock(
                    status_code=200,
                    json=lambda: {"id": user_data["id"], "email": user_data["email"]},
                    raise_for_status=lambda: None
                )
            # Fallback for tokens not in map (legacy test support)
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


class MockSupabaseAsyncClient:
    """Async mock of httpx.AsyncClient for Supabase auth calls."""

    def __init__(self, *args, **kwargs):
        self.timeout = kwargs.get("timeout", None)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url, headers=None):
        return mock_requests_get(url, headers=headers)


def mock_get_user_quizzes(user_id, user_token=None):
    """Mock getting user quizzes."""
    return _quiz_storage.get_user_quizzes(user_id)


def mock_get_quiz_from_database(quiz_id, user_id=None):
    """Mock getting quiz from database."""
    return _quiz_storage.get_quiz(quiz_id, user_id)


async def mock_get_quiz_metadata_cached(quiz_id, user_id, user_token=None):
    """Mock cached metadata retrieval using in-memory quiz storage."""
    quiz = _quiz_storage.get_quiz(quiz_id, user_id)
    if not quiz:
        raise HTTPException(status_code=404, detail="Quiz not found")

    created_by = quiz.get("created_by") or quiz.get("user_id") or (user_id or "mock_user_123")

    return {
        "id": quiz_id,
        "title": quiz.get("title", "Mock Quiz"),
        "created_by": created_by,
        "created_at": quiz.get("created_at", "2025-10-04T00:00:00"),
        "question_count": len(quiz.get("questions", [])),
        "content_source_type": quiz.get("content_source_type"),
        "content_source_reference": quiz.get("content_source_reference"),
    }


@pytest.fixture(scope="module", autouse=True)
def setup_integration_mocks():
    """
    Auto-applied fixture that sets up all mocks for integration tests.
    
    This runs once per test module and patches all external dependencies.
    Uses context managers stacked with contextlib for cleaner setup.
    """
    from contextlib import ExitStack
    from dependencies.auth_dependencies import reset_http_client
    from fakeredis import aioredis as fakeredis
    from main import app
    import asyncio
    
    # Reset HTTP client singleton before patching (ensures fresh mock client is used)
    reset_http_client()
    
    # Set up fakeredis for session management (module-scoped)
    loop = asyncio.new_event_loop()
    redis_client = loop.run_until_complete(fakeredis.FakeRedis(decode_responses=True))
    app.state.redis = redis_client
    
    # Pass the quiz storage to the mock client so it can access saved quizzes
    mock_supabase = MockSupabaseClient(quiz_storage=_quiz_storage)
    
    # Use ExitStack to manage multiple patches without deep nesting
    with ExitStack() as stack:
        # Patch the lazy loading functions for all modules that use Supabase
        stack.enter_context(patch("handlers.auth_handlers.get_supabase", return_value=mock_supabase))
        stack.enter_context(patch("services.db_services.supabase_quiz.get_supabase", return_value=mock_supabase))
        stack.enter_context(patch("services.db_services.supabase_quiz.get_authed_supabase_client", return_value=mock_supabase))
        stack.enter_context(patch("services.db_services.supabase_file.get_supabase", return_value=mock_supabase))
        stack.enter_context(patch("services.db_services.supabase_submission.get_supabase", return_value=mock_supabase))
        stack.enter_context(patch("services.db_services.supabase_quiz.get_quiz_metadata_cached", side_effect=mock_get_quiz_metadata_cached))
        
        # Patch external dependencies
        stack.enter_context(patch("dependencies.auth_dependencies.httpx.AsyncClient", MockSupabaseAsyncClient))
        
        # Patch handler-level functions
        stack.enter_context(patch("handlers.quiz_handlers.get_quiz_metadata_cached", side_effect=mock_get_quiz_metadata_cached))
        stack.enter_context(patch("handlers.quiz_handlers.get_authed_supabase_client", return_value=mock_supabase))
        stack.enter_context(patch("handlers.quiz_handlers.generate_quizzes_single_async", side_effect=mock_generate_quizzes_single_async))
        stack.enter_context(patch("handlers.quiz_handlers.save_quiz_to_database", side_effect=mock_save_quiz_to_database))
        stack.enter_context(patch("handlers.quiz_handlers.get_user_quizzes", side_effect=mock_get_user_quizzes))
        stack.enter_context(patch("handlers.quiz_handlers.get_quiz_from_database", side_effect=mock_get_quiz_from_database))
        stack.enter_context(patch("handlers.quiz_handlers.save_file_to_supabase", side_effect=mock_save_file_to_supabase))
        stack.enter_context(patch("handlers.quiz_handlers.save_metadata", side_effect=mock_save_metadata))
        stack.enter_context(patch("handlers.file_handlers.save_file_to_supabase", side_effect=mock_save_file_to_supabase))
        
        yield mock_supabase
    
    # Cleanup
    loop.run_until_complete(redis_client.close())
    loop.close()
    app.state.redis = None

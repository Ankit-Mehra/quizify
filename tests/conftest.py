import pytest
from unittest.mock import Mock, MagicMock
import os
import asyncio
import logging

os.environ["SUPABASE_URL"] = "https://test.supabase.co"
os.environ["SUPABASE_KEY"] = "test_key"
os.environ["SUPABASE_STORAGE_NAME"] = "test-bucket"
os.environ["OPENAI_API_KEY"] = "sk-test123"
os.environ["IP_HASH_SECRET"] = "test-secret-for-ip-hashing-min-32-chars"
os.environ["TESTING"] = "true"
os.environ["REDIS_ENABLED"] = "false"  # Disable real Redis by default for tests

@pytest.fixture(scope="function")
def event_loop():
    """Create an event loop for async fixtures."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()

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
        
        if len(password) < 8:
            raise Exception("Password should be at least 8 characters")
        
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
                    "quizzes_attempted": 0,
                    "quota_exceeded": False
                }
            ],
            "profiles": [
                {
                    "id": "mock_user_123",
                    "email": "test@example.com",
                    "account_tier": "free",
                    "is_admin": False,
                    # Storage quota fields
                    "billing_plan": "free",
                    "subscription_status": None,
                    "credit_units_purchased": 0,
                }
            ],
            # Storage usage aggregation (empty by default)
            "user_files": []
        }
    
    def table(self, table_name):
        """Return a mock table interface with realistic data."""
        mock_table = Mock()
        
        # Store the table name and query context
        mock_table._table_name = table_name
        mock_table._filters = {}
        mock_table._single = False
        
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
                    match = True
                    for col, val in mock_table._filters.items():
                        row_val = row.get(col)
                        if row_val != val:
                            match = False
                            break
                    if match:
                        filtered_data.append(row)
                mock_result.data = filtered_data
            else:
                mock_result.data = table_data
            
            # For single() calls, return first item's data directly
            if getattr(mock_table, '_single', False) and mock_result.data:
                mock_result.data = mock_result.data[0]
            elif getattr(mock_table, '_single', False):
                mock_result.data = None
            
            mock_result.count = len(mock_result.data) if isinstance(mock_result.data, list) else 1
            return mock_result
        
        def mock_single():
            """Mock single() - returns first result"""
            mock_table._single = True
            return mock_table
        
        # Setup method chaining
        mock_table.select = mock_select
        mock_table.insert.return_value = mock_table
        mock_table.update.return_value = mock_table
        mock_table.delete.return_value = mock_table
        mock_table.eq = mock_eq
        mock_table.in_.return_value = mock_table
        mock_table.single = mock_single
        mock_table.execute = mock_execute
        
        return mock_table

@pytest.fixture
def mock_supabase():
    return MockSupabaseClient()

class SimpleAsyncRedis:
    """
    Simple in-memory Redis mock that works across event loops.
    Avoids fakeredis event loop binding issues.
    """
    def __init__(self):
        self._data = {}
        self._sets = {}
        self._expires = {}
    
    async def set(self, key, value, ex=None):
        self._data[key] = value
        if ex:
            self._expires[key] = ex
        return True
    
    async def get(self, key):
        return self._data.get(key)
    
    async def delete(self, *keys):
        count = 0
        for key in keys:
            if key in self._data:
                del self._data[key]
                count += 1
        return count
    
    async def hset(self, name, key=None, value=None, mapping=None):
        if name not in self._data:
            self._data[name] = {}
        if mapping:
            self._data[name].update(mapping)
        elif key and value:
            self._data[name][key] = value
        return 1
    
    async def hgetall(self, name):
        return self._data.get(name, {})
    
    async def hdel(self, name, *keys):
        if name not in self._data:
            return 0
        count = 0
        for key in keys:
            if key in self._data[name]:
                del self._data[name][key]
                count += 1
        return count

    async def sadd(self, name, *values):
        if name not in self._sets:
            self._sets[name] = set()
        before = len(self._sets[name])
        self._sets[name].update(values)
        return len(self._sets[name]) - before
    
    async def smembers(self, name):
        return self._sets.get(name, set())
    
    async def srem(self, name, *values):
        if name not in self._sets:
            return 0
        count = 0
        for value in values:
            if value in self._sets[name]:
                self._sets[name].remove(value)
                count += 1
        return count
    
    async def scard(self, name):
        return len(self._sets.get(name, set()))
    
    async def expire(self, name, time):
        self._expires[name] = time
        return True
    
    async def eval(self, script, numkeys, *keys_and_args):
        """Mock eval for Lua scripts - just approve session creation."""
        return 1  # Success
    
    async def close(self):
        pass
    
    async def aclose(self):
        pass

@pytest.fixture(scope="function")
async def mock_redis_client():
    """Provide a SimpleAsyncRedis client for tests."""
    redis_client = SimpleAsyncRedis()
    yield redis_client
    await redis_client.aclose()

@pytest.fixture(scope="function")
def mock_supabase_client(mock_supabase, mocker, mock_redis_client):
    """
    Mock Supabase client with all necessary service patches.
    Uses pytest-mock's mocker fixture for cleaner test setup.
    Also provides a fakeredis client for session management.
    """
    from main import app
    
    # Set up fakeredis for session management
    app.state.redis = mock_redis_client
    
    # Define mock implementations
    def mock_save_file_to_supabase(*args, **kwargs):
        return {"message": "File uploaded successfully"}
    
    def mock_delete_file_from_supabase(*args, **kwargs):
        return {"message": "File deleted successfully"}
    
    async def mock_generate_quizzes_single_async(text, num_questions, question_types=None, user_id=None, trace_id=None, generation_mode=None, content_source_type=None):
        """Mock AI quiz generation with PostHog analytics support"""
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
    
    def mock_save_quiz_to_database(title, quizzes, created_by, content_source_type=None, content_source_reference=None, user_token=None, generation_mode=None):
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
    
    async def mock_consume_units(user_id: str, quiz_type: str):
        """Mock credit consumption - always succeeds in tests"""
        return True
    
    async def mock_get_billing_state(user_id: str):
        """Mock billing state - returns default free user state"""
        from schemas.billing import UserBillingState
        from datetime import datetime, timezone, timedelta
        return UserBillingState(
            user_id=user_id,
            plan="free",
            credit_units_monthly=6,
            credit_units_remaining=6,
            credit_units_purchased=0,
            period_start=datetime.now(timezone.utc),
            period_end=datetime.now(timezone.utc) + timedelta(days=30)
        )
    
    # Apply all patches using mocker (pytest-mock)
    # NEW PATTERN: Mock get_supabase() functions instead of module-level variables
    mocker.patch("handlers.auth_handlers.get_supabase", return_value=mock_supabase)
    mocker.patch("services.db_services.supabase_quiz.get_supabase", return_value=mock_supabase)
    mocker.patch("services.db_services.supabase_file.get_supabase", return_value=mock_supabase)
    mocker.patch("services.db_services.supabase_submission.get_supabase", return_value=mock_supabase)
    mocker.patch("services.storage_service.get_supabase", return_value=mock_supabase)
    
    # Mock billing service functions
    mocker.patch("handlers.quiz_handlers.consume_units", side_effect=mock_consume_units)
    mocker.patch("handlers.quiz_handlers.get_billing_state", side_effect=mock_get_billing_state)
    mocker.patch("services.billing_service.get_billing_state", side_effect=mock_get_billing_state)
    
    # Keep function-level mocks
    mocker.patch("handlers.file_handlers.save_file_to_supabase_async", side_effect=mock_save_file_to_supabase)
    mocker.patch("handlers.file_handlers.delete_file_from_supabase", side_effect=mock_delete_file_from_supabase)
    mocker.patch("handlers.quiz_handlers.generate_quizzes_single_async", side_effect=mock_generate_quizzes_single_async)
    mocker.patch("handlers.quiz_handlers.save_quiz_to_database", side_effect=mock_save_quiz_to_database)
    mocker.patch("handlers.quiz_handlers.save_metadata", side_effect=mock_save_metadata)
    mocker.patch("handlers.quiz_handlers.save_file_to_supabase_async", side_effect=mock_save_file_to_supabase)
    
    yield mock_supabase
    
    # Cleanup
    app.state.redis = None
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


@pytest.fixture(autouse=True)
def cleanup_logging_handlers():
    """Cleanup mock logging handlers attached to ANY logger to prevent TypeErrors."""
    
    def remove_mock_handlers():
        # Get all loggers including root
        loggers = [logging.getLogger()] + [
            logging.getLogger(name) for name in logging.root.manager.loggerDict
        ]
        
        for logger in loggers:
            handlers_to_remove = [
                h for h in logger.handlers 
                if isinstance(h, (Mock, MagicMock))
            ]
            for h in handlers_to_remove:
                logger.removeHandler(h)

    # Cleanup before test
    remove_mock_handlers()
        
    yield
    
    # Cleanup after test
    remove_mock_handlers()


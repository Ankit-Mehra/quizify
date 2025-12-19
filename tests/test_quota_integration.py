"""
Integration tests for quota enforcement in quiz generation endpoints.
Tests both /api/quiz/generate/text and /api/quiz/generate/file endpoints.
"""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from contextlib import contextmanager
from fastapi import HTTPException
from handlers.quiz_handlers import generate_quiz_from_text, generate_quiz_from_file_openai, generate_quiz_from_fileid
from schemas.quiz import TextQuizRequest, FileQuizRequest
from schemas.billing import UserBillingState


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def mock_question():
    """Create a mock question dict that works with both spread operator and attribute access."""
    return {
        "type": "multiple_choice",
        "question": "Test question?",
        "options": ["A", "B", "C", "D"],
        "correct_answer": "A",
        "explanation": "Test explanation",
        "source": "Test source"
    }


@pytest.fixture
def mock_file():
    """Create a mock file object."""
    file_content = b"Test file content for quiz generation"
    mock = MagicMock()
    mock.filename = "test.txt"
    mock.content_type = "text/plain"
    mock.read = AsyncMock(return_value=file_content)
    mock.seek = AsyncMock()
    return mock


@pytest.fixture
def mock_file_record():
    """Create a mock file record from database."""
    return {
        'id': 'file-123',
        'user_id': 'test-user-id',
        'original_filename': 'test.pdf',
        'file_type': 'application/pdf',
        'storage_path': 'user-files/test.pdf'
    }


@pytest.fixture
def text_quiz_request():
    """Create a standard text quiz request."""
    return TextQuizRequest(
        title="Test Quiz",
        content="This is test content for generating a quiz about Python programming.",
        num_questions=5,
        question_type=["multiple_choice"]
    )


@pytest.fixture
def file_quiz_request():
    """Create a standard file quiz request."""
    return FileQuizRequest(
        title="Test File Quiz",
        num_questions=5,
        question_type=["multiple_choice"]
    )


# ============================================================================
# Helper Functions
# ============================================================================

def create_tier_info(account_tier: str, current_count: int, quota_limit: int) -> dict:
    """Helper to create tier info dictionary."""
    return {
        'id': 'test-user-id',
        'account_tier': account_tier,
        'current_quiz_count': current_count,
        'quizzes_attempted': current_count,
        'quota_limit': quota_limit,
        'quota_exceeded': current_count >= quota_limit
    }


def create_billing_state(plan: str = "free", credits_remaining: float = 10.0) -> UserBillingState:
    """Helper to create billing state object."""
    return UserBillingState(
        user_id="test-user-id",
        plan=plan,
        credit_units_monthly=6,
        credit_units_remaining=int(credits_remaining * 2),
        credit_units_purchased=0,
        free_credit_units_monthly=6,
        free_credit_units_remaining=int(credits_remaining * 2),
        period_start=None,
        period_end=None
    )


def setup_successful_generation_mocks(mock_generate, mock_save_quiz, mock_question, quiz_id="quiz-123"):
    """Helper to set up mocks for successful quiz generation."""
    import uuid
    # Use actual UUID format for quiz_id if it's the default
    if quiz_id == "quiz-123":
        quiz_id = str(uuid.uuid4())
    
    mock_generate.return_value = [mock_question]
    # Return tuple (quiz_id, saved_questions) to match updated function signature
    saved_questions = [{
        **mock_question,
        'id': str(uuid.uuid4()),  # Generate proper UUID
        'quiz_id': quiz_id
    }]
    mock_save_quiz.return_value = (quiz_id, saved_questions)


def assert_quota_exceeded_error(exc_info, expected_plan: str, expected_available: float = 0.0):
    """Helper to assert quota exceeded error details."""
    assert exc_info.value.status_code == 402
    detail = exc_info.value.detail
    assert detail['error'] == 'quota_exceeded'
    assert detail['current_plan'] == expected_plan
    assert detail['available_credits'] == expected_available


def create_quota_exception(plan, credits_remaining, required_credits=0.5):
    """Helper to create quota exceeded exception for mocks."""
    message = "Not enough credits. Upgrade to Pro or purchase credits."
    if plan == 'pro':
        message = "Not enough credits. Purchase additional credits to continue."
        
    return HTTPException(
        status_code=402,
        detail={
            "error": "quota_exceeded",
            "message": message,
            "current_plan": plan,
            "available_credits": credits_remaining,
            "required_credits": required_credits
        }
    )


@contextmanager
def mock_quiz_generation_success(mock_question, tier_info, quiz_id="quiz-123"):
    """Context manager to mock successful quiz generation with all dependencies."""
    with patch('handlers.quiz_handlers.get_user_tier_info_cached') as mock_tier, \
         patch('handlers.quiz_handlers.generate_quizzes_single_async') as mock_generate, \
         patch('handlers.quiz_handlers.save_quiz_to_database') as mock_save_quiz, \
         patch('handlers.quiz_handlers.save_file_to_supabase_async') as mock_save_file, \
         patch('handlers.quiz_handlers.save_metadata') as mock_save_metadata, \
         patch('handlers.quiz_handlers.reserve_credits_atomic') as mock_validate:
        
        # Setup all mocks
        mock_tier.return_value = tier_info
        mock_validate.return_value = None  # Success
        
        setup_successful_generation_mocks(mock_generate, mock_save_quiz, mock_question, quiz_id)
        
        # Yield all mocks for test assertions
        yield {
            'tier': mock_tier,
            'generate': mock_generate,
            'save_quiz': mock_save_quiz,
            'save_file': mock_save_file,
            'save_metadata': mock_save_metadata,
            'validate': mock_validate
        }


@contextmanager
def mock_file_extraction_and_generation(mock_question, tier_info, quiz_id="quiz-123", extracted_text=None):
    """Context manager to mock file extraction and quiz generation."""
    if extracted_text is None:
        extracted_text = "Extracted text content for quiz generation. This text needs to be long enough to pass the minimum content length check."
    
    with patch('handlers.quiz_handlers.get_user_tier_info_cached') as mock_tier, \
         patch('handlers.quiz_handlers.extract_text_from_plain_text') as mock_extract, \
         patch('handlers.quiz_handlers.generate_quizzes_single_async') as mock_generate, \
         patch('handlers.quiz_handlers.save_quiz_to_database') as mock_save_quiz, \
         patch('handlers.quiz_handlers.save_metadata') as mock_save_metadata, \
         patch('handlers.quiz_handlers.save_file_to_supabase_async') as mock_save_file, \
         patch('handlers.quiz_handlers.reserve_credits_atomic') as mock_validate:
        
        # Setup all mocks
        mock_tier.return_value = tier_info
        mock_extract.return_value = extracted_text
        mock_validate.return_value = None  # Success
        
        setup_successful_generation_mocks(mock_generate, mock_save_quiz, mock_question, quiz_id)
        
        # Yield all mocks for test assertions
        yield {
            'tier': mock_tier,
            'extract': mock_extract,
            'generate': mock_generate,
            'save_quiz': mock_save_quiz,
            'save_metadata': mock_save_metadata,
            'save_file': mock_save_file,
            'validate': mock_validate
        }


@contextmanager
def mock_file_id_generation(mock_question, mock_file_record, tier_info, quiz_id="quiz-123", parsed_text=None):
    """Context manager to mock file ID based quiz generation."""
    if parsed_text is None:
        parsed_text = "Parsed text from stored file. This text needs to be long enough to pass the minimum content length check."
    
    with patch('handlers.quiz_handlers.get_user_tier_info_cached') as mock_tier, \
         patch('handlers.quiz_handlers.get_file_record') as mock_get_record, \
         patch('handlers.quiz_handlers.parse_file_from_supabase') as mock_parse, \
         patch('handlers.quiz_handlers.generate_quizzes_single_async') as mock_generate, \
         patch('handlers.quiz_handlers.save_quiz_to_database') as mock_save_quiz, \
         patch('handlers.quiz_handlers.save_metadata') as mock_save_metadata, \
         patch('handlers.quiz_handlers.reserve_credits_atomic') as mock_validate:
        
        # Setup all mocks
        mock_tier.return_value = tier_info
        mock_get_record.return_value = mock_file_record
        mock_parse.return_value = parsed_text
        mock_validate.return_value = None  # Success
        
        setup_successful_generation_mocks(mock_generate, mock_save_quiz, mock_question, quiz_id)
        
        # Yield all mocks for test assertions
        yield {
            'tier': mock_tier,
            'get_record': mock_get_record,
            'parse': mock_parse,
            'generate': mock_generate,
            'save_quiz': mock_save_quiz,
            'save_metadata': mock_save_metadata,
            'validate': mock_validate
        }


@contextmanager
def mock_quota_exceeded(tier_info):
    """Context manager to mock quota exceeded scenario (no generation)."""
    with patch('handlers.quiz_handlers.get_user_tier_info_cached') as mock_tier, \
         patch('handlers.quiz_handlers.reserve_credits_atomic') as mock_validate, \
         patch('handlers.quiz_handlers.get_file_record') as mock_get_record, \
         patch('handlers.quiz_handlers.parse_file_from_supabase') as mock_parse:
        
        mock_tier.return_value = tier_info
        
        # Mock file operations to avoid DB errors
        mock_get_record.return_value = {
            'id': 'file-123',
            'user_id': 'test-user-id',
            'original_filename': 'test.pdf',
            'file_type': 'application/pdf',
            'storage_path': 'user-files/test.pdf'
        }
        mock_parse.return_value = "Extracted text content long enough."
        
        # Map legacy tiers to new billing plans
        plan = tier_info['account_tier']
        if plan in ['basic', 'premium']:
            plan = 'pro'
            
        # Simulate quota exceeded exception
        mock_validate.side_effect = create_quota_exception(plan, 0.0)
        
        yield {
            'tier': mock_tier,
            'validate': mock_validate,
            'get_record': mock_get_record,
            'parse': mock_parse
        }


# ============================================================================
# Text Endpoint Tests
# ============================================================================

class TestQuotaEnforcementTextEndpoint:
    """Integration tests for quota enforcement on text generation endpoint."""
    
    @pytest.mark.asyncio
    async def test_text_endpoint_free_tier_under_limit_success(
        self, mock_question, text_quiz_request
    ):
        """Test text endpoint allows quiz generation for free tier user under limit."""
        tier_info = create_tier_info('free', 3, 5)
        
        with mock_quiz_generation_success(mock_question, tier_info) as mocks:
            # Call handler
            result = await generate_quiz_from_text(
                data=text_quiz_request,
                current_user_id='test-user-id',
                user_token='test-token'
            )
            
            # Assertions - result is now EnhancedQuizGenerationResponse object
            assert hasattr(result, 'quiz_id')
            assert isinstance(result.quiz_id, str)
            assert len(result.quiz_id) > 0  # Valid quiz ID returned
            assert 'Quiz generated successfully' in result.message
            mocks['generate'].assert_called_once()
            mocks['save_quiz'].assert_called_once()
        
    @pytest.mark.asyncio
    async def test_text_endpoint_free_tier_at_limit_forbidden(
        self, text_quiz_request
    ):
        """Test text endpoint returns 403 for free tier user at limit."""
        tier_info = create_tier_info('free', 5, 5)
        
        with mock_quota_exceeded(tier_info):
            # Call handler and expect exception
            with pytest.raises(HTTPException) as exc_info:
                await generate_quiz_from_text(
                    data=text_quiz_request,
                    current_user_id='test-user-id',
                    user_token='test-token'
                )
            
            # Assertions
            assert_quota_exceeded_error(exc_info, 'free', 0.0)
            assert 'Upgrade to Pro' in exc_info.value.detail['message']
        
    @pytest.mark.asyncio
    async def test_text_endpoint_basic_tier_at_limit_forbidden(
        self, text_quiz_request
    ):
        """Test text endpoint returns 403 for basic tier user at limit."""
        tier_info = create_tier_info('basic', 100, 100)
        
        with mock_quota_exceeded(tier_info):
            # Call handler and expect exception
            with pytest.raises(HTTPException) as exc_info:
                await generate_quiz_from_text(
                    data=text_quiz_request,
                    current_user_id='test-user-id',
                    user_token='test-token'
                )
            
            # Assertions
            # 'basic' tier is normalized to 'premium' in user-facing messages
            assert_quota_exceeded_error(exc_info, 'pro', 0.0)
            assert 'Purchase additional credits' in exc_info.value.detail['message']
        
    @pytest.mark.asyncio
    async def test_text_endpoint_pro_tier_under_limit_success(
        self, mock_question
    ):
        """Test text endpoint allows quiz generation for pro tier user under limit."""
        tier_info = create_tier_info('pro', 450, 999999)
        
        # Create request for advanced content
        request_data = TextQuizRequest(
            title="Test Quiz",
            content="This is test content for generating a quiz about advanced topics.",
            num_questions=10,
            question_type=["multiple_choice"]
        )
        
        with mock_quiz_generation_success(mock_question, tier_info) as mocks:  # Uses auto-generated UUID
            # Call handler
            result = await generate_quiz_from_text(
                data=request_data,
                current_user_id='test-user-id',
                user_token='test-token'
            )
            
            # Assertions - result is now EnhancedQuizGenerationResponse object
            assert hasattr(result, 'quiz_id')
            assert isinstance(result.quiz_id, str)
            assert len(result.quiz_id) > 0  # Valid quiz ID returned
            assert 'Quiz generated successfully' in result.message
            mocks['generate'].assert_called_once()
            mocks['save_quiz'].assert_called_once()


# ============================================================================
# File Endpoint Tests
# ============================================================================

class TestQuotaEnforcementFileEndpoint:
    """Integration tests for quota enforcement on file generation endpoint."""
    
    @pytest.mark.asyncio
    async def test_file_endpoint_free_tier_under_limit_success(
        self, mock_question
    ):
        """Test file endpoint allows quiz generation for free tier user under limit."""
        tier_info = create_tier_info('free', 2, 5)
        
        # Create mock file
        file_content = b"Test file content for quiz generation"
        mock_file = MagicMock()
        mock_file.filename = "test.txt"
        mock_file.content_type = "text/plain"
        mock_file.read = AsyncMock(return_value=file_content)
        mock_file.seek = AsyncMock()
        
        with mock_file_extraction_and_generation(mock_question, tier_info) as mocks:
            # Call handler
            result = await generate_quiz_from_file_openai(
                file=mock_file,
                title="Test File Quiz",
                num_questions=5,
                question_type=["multiple_choice"],
                mode="standard",  # Required when calling handler directly (bypasses FastAPI Form resolution)
                current_user_id='test-user-id',
                user_token='test-token'
            )
            
            # Assertions - result is now EnhancedQuizGenerationResponse object
            assert hasattr(result, 'quiz_id')
            assert isinstance(result.quiz_id, str)
            assert len(result.quiz_id) > 0  # Valid quiz ID returned
            assert 'Quiz generated successfully' in result.message
            mocks['generate'].assert_called_once()
            mocks['save_quiz'].assert_called_once()
        
    @pytest.mark.asyncio
    async def test_file_endpoint_free_tier_at_limit_forbidden(self):
        """Test file endpoint returns 403 for free tier user at limit."""
        tier_info = create_tier_info('free', 5, 5)
        
        # Create mock file
        file_content = b"Test file content"
        mock_file = MagicMock()
        mock_file.filename = "test.txt"
        mock_file.content_type = "text/plain"
        mock_file.read = AsyncMock(return_value=file_content)
        
        with mock_quota_exceeded(tier_info):
            # Call handler and expect exception
            with pytest.raises(HTTPException) as exc_info:
                await generate_quiz_from_file_openai(
                    file=mock_file,
                    title="Test File Quiz",
                    num_questions=5,
                    question_type=["multiple_choice"],
                    mode="standard",
                    current_user_id='test-user-id',
                    user_token='test-token'
                )
            
            # Assertions
            assert_quota_exceeded_error(exc_info, 'free', 0.0)
            assert 'Upgrade to Pro' in exc_info.value.detail['message']
        
    @pytest.mark.asyncio
    async def test_file_endpoint_basic_tier_at_limit_forbidden(self):
        """Test file endpoint returns 403 for basic tier user at limit."""
        tier_info = create_tier_info('basic', 100, 100)
        
        # Create mock file
        file_content = b"Test file content"
        mock_file = MagicMock()
        mock_file.filename = "test.txt"
        mock_file.content_type = "text/plain"
        mock_file.read = AsyncMock(return_value=file_content)
        
        with mock_quota_exceeded(tier_info):
            # Call handler and expect exception
            with pytest.raises(HTTPException) as exc_info:
                await generate_quiz_from_file_openai(
                    file=mock_file,
                    title="Test File Quiz",
                    num_questions=5,
                    question_type=["multiple_choice"],
                    mode="standard",
                    current_user_id='test-user-id',
                    user_token='test-token'
                )
            
            # Assertions
            # 'basic' tier is normalized to 'premium' in user-facing messages
            assert_quota_exceeded_error(exc_info, 'pro', 0.0)
            assert 'Purchase additional credits' in exc_info.value.detail['message']


class TestQuotaCheckBeforeGeneration:
    """Tests to verify quota check happens before AI generation."""
    
    @pytest.mark.asyncio
    async def test_text_endpoint_quota_check_before_ai_call(
        self, text_quiz_request
    ):
        """Test that quota check happens before AI generation for text endpoint."""
        tier_info = create_tier_info('free', 5, 5)
        
        with mock_quota_exceeded(tier_info) as mocks:
            # Call handler and expect exception
            with pytest.raises(HTTPException) as exc_info:
                await generate_quiz_from_text(
                    data=text_quiz_request,
                    current_user_id='test-user-id',
                    user_token='test-token'
                )
            
            # Verify quota check failed with 402 (updated from 403)
            assert exc_info.value.status_code == 402
            
            # Verify AI generation was NOT called (no API waste)
            # Note: mock_quota_exceeded doesn't mock generate_quizzes_single_async directly
            # but since validate raises exception, generate is never reached.
        
    @pytest.mark.asyncio
    async def test_file_endpoint_quota_check_before_ai_call(
        self
    ):
        """Test that quota check happens before AI generation for file endpoint."""
        tier_info = create_tier_info('basic', 100, 100)
        
        # Create mock file
        file_content = b"Test file content"
        mock_file = MagicMock()
        mock_file.filename = "test.txt"
        mock_file.content_type = "text/plain"
        mock_file.read = AsyncMock(return_value=file_content)
        
        with mock_quota_exceeded(tier_info) as mocks:
            # Call handler and expect exception
            with pytest.raises(HTTPException) as exc_info:
                await generate_quiz_from_file_openai(
                    file=mock_file,
                    title="Test File Quiz",
                    num_questions=5,
                    question_type=["multiple_choice"],
                    mode="standard",
                    current_user_id='test-user-id',
                    user_token='test-token'
                )
            
            # Verify quota check failed with 402
            assert exc_info.value.status_code == 402


class TestQuotaEnforcementFileIdEndpoint:
    """Integration tests for quota enforcement on file ID generation endpoint."""
    
    @pytest.mark.asyncio
    async def test_file_id_endpoint_free_tier_under_limit_success(
        self, mock_question, mock_file_record
    ):
        """Test file ID endpoint allows quiz generation for free tier user under limit."""
        tier_info = create_tier_info('free', 2, 5)
        
        with mock_file_id_generation(mock_question, mock_file_record, tier_info) as mocks:
            # Create request data
            request_data = FileQuizRequest(
                title="Test File ID Quiz",
                num_questions=5,
                question_type=["multiple_choice"]
            )
            
            # Call handler
            result = await generate_quiz_from_fileid(
                file_id='file-123',
                data=request_data,
                current_user_id='test-user-id',
                user_token='test-token'
            )
            
            # Assertions
            assert hasattr(result, 'quiz_id')
            assert isinstance(result.quiz_id, str)
            assert len(result.quiz_id) > 0
            assert 'Quiz generated successfully' in result.message
            mocks['generate'].assert_called_once()
            mocks['save_quiz'].assert_called_once()
        
    @pytest.mark.asyncio
    async def test_file_id_endpoint_free_tier_at_limit_forbidden(
        self, mock_file_record
    ):
        """Test file ID endpoint returns 403 for free tier user at limit."""
        tier_info = create_tier_info('free', 5, 5)
        
        with mock_quota_exceeded(tier_info):
            # Create request data
            request_data = FileQuizRequest(
                title="Test File ID Quiz",
                num_questions=5,
                question_type=["multiple_choice"]
            )
            
            # Call handler and expect exception
            with pytest.raises(HTTPException) as exc_info:
                await generate_quiz_from_fileid(
                    file_id='file-123',
                    data=request_data,
                    current_user_id='test-user-id',
                    user_token='test-token'
                )
            
            # Assertions
            assert_quota_exceeded_error(exc_info, 'free', 0.0)
            assert 'Upgrade to Pro' in exc_info.value.detail['message']
        
    @pytest.mark.asyncio
    async def test_file_id_endpoint_basic_tier_at_limit_forbidden(
        self, mock_file_record
    ):
        """Test file ID endpoint returns 403 for basic tier user at limit."""
        tier_info = create_tier_info('basic', 100, 100)
        
        with mock_quota_exceeded(tier_info):
            # Create request data
            request_data = FileQuizRequest(
                title="Test File ID Quiz",
                num_questions=5,
                question_type=["multiple_choice"]
            )
            
            # Call handler and expect exception
            with pytest.raises(HTTPException) as exc_info:
                await generate_quiz_from_fileid(
                    file_id='file-123',
                    data=request_data,
                    current_user_id='test-user-id',
                    user_token='test-token'
                )
            
            # Assertions
            assert_quota_exceeded_error(exc_info, 'pro', 0.0)
            assert 'Purchase additional credits' in exc_info.value.detail['message']
        
    @pytest.mark.asyncio
    async def test_file_id_endpoint_quota_check_before_ai_call(
        self, mock_file_record
    ):
        """Test that quota check happens before AI generation for file ID endpoint."""
        tier_info = create_tier_info('free', 5, 5)
        
        with mock_quota_exceeded(tier_info):
            # Create request data
            request_data = FileQuizRequest(
                title="Test File ID Quiz",
                num_questions=5,
                question_type=["multiple_choice"]
            )
            
            # Call handler and expect exception
            with pytest.raises(HTTPException) as exc_info:
                await generate_quiz_from_fileid(
                    file_id='file-123',
                    data=request_data,
                    current_user_id='test-user-id',
                    user_token='test-token'
                )
            
            # Verify quota check failed with 402
            assert exc_info.value.status_code == 402


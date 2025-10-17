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


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def mock_question():
    """Create a mock question object."""
    question = MagicMock()
    question.type = "multiple_choice"
    question.question = "Test question?"
    question.options = ["A", "B", "C", "D"]
    question.correct_answer = "A"
    question.explanation = "Test explanation"
    question.source = "Test source"
    return question


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
        'quota_limit': quota_limit,
        'quota_exceeded': current_count >= quota_limit
    }


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


def assert_quota_exceeded_error(exc_info, expected_tier: str, expected_count: int, expected_limit: int):
    """Helper to assert quota exceeded error details."""
    assert exc_info.value.status_code == 403
    detail = exc_info.value.detail
    assert detail['current_count'] == expected_count
    assert detail['quota_limit'] == expected_limit
    assert detail['user_tier'] == expected_tier


@contextmanager
def mock_quiz_generation_success(mock_question, tier_info, quiz_id="quiz-123"):
    """Context manager to mock successful quiz generation with all dependencies."""
    with patch('handlers.quiz_handlers.get_user_tier_info') as mock_tier, \
         patch('handlers.quiz_handlers.generate_quizzes_single_async') as mock_generate, \
         patch('handlers.quiz_handlers.save_quiz_to_database') as mock_save_quiz, \
         patch('handlers.quiz_handlers.save_file_to_supabase') as mock_save_file, \
         patch('handlers.quiz_handlers.save_metadata') as mock_save_metadata:
        
        # Setup all mocks
        mock_tier.return_value = tier_info
        setup_successful_generation_mocks(mock_generate, mock_save_quiz, mock_question, quiz_id)
        
        # Yield all mocks for test assertions
        yield {
            'tier': mock_tier,
            'generate': mock_generate,
            'save_quiz': mock_save_quiz,
            'save_file': mock_save_file,
            'save_metadata': mock_save_metadata
        }


@contextmanager
def mock_file_extraction_and_generation(mock_question, tier_info, quiz_id="quiz-123", extracted_text=None):
    """Context manager to mock file extraction and quiz generation."""
    if extracted_text is None:
        extracted_text = "Extracted text content for quiz generation."
    
    with patch('handlers.quiz_handlers.get_user_tier_info') as mock_tier, \
         patch('handlers.quiz_handlers.extract_text_from_plain_text') as mock_extract, \
         patch('handlers.quiz_handlers.generate_quizzes_single_async') as mock_generate, \
         patch('handlers.quiz_handlers.save_quiz_to_database') as mock_save_quiz, \
         patch('handlers.quiz_handlers.save_metadata') as mock_save_metadata, \
         patch('handlers.quiz_handlers.save_file_to_supabase') as mock_save_file:
        
        # Setup all mocks
        mock_tier.return_value = tier_info
        mock_extract.return_value = extracted_text
        setup_successful_generation_mocks(mock_generate, mock_save_quiz, mock_question, quiz_id)
        
        # Yield all mocks for test assertions
        yield {
            'tier': mock_tier,
            'extract': mock_extract,
            'generate': mock_generate,
            'save_quiz': mock_save_quiz,
            'save_metadata': mock_save_metadata,
            'save_file': mock_save_file
        }


@contextmanager
def mock_file_id_generation(mock_question, mock_file_record, tier_info, quiz_id="quiz-123", parsed_text=None):
    """Context manager to mock file ID based quiz generation."""
    if parsed_text is None:
        parsed_text = "Parsed text from stored file."
    
    with patch('handlers.quiz_handlers.get_user_tier_info') as mock_tier, \
         patch('handlers.quiz_handlers.get_file_record') as mock_get_record, \
         patch('handlers.quiz_handlers.parse_file_from_supabase') as mock_parse, \
         patch('handlers.quiz_handlers.generate_quizzes_single_async') as mock_generate, \
         patch('handlers.quiz_handlers.save_quiz_to_database') as mock_save_quiz, \
         patch('handlers.quiz_handlers.save_metadata') as mock_save_metadata:
        
        # Setup all mocks
        mock_tier.return_value = tier_info
        mock_get_record.return_value = mock_file_record
        mock_parse.return_value = parsed_text
        setup_successful_generation_mocks(mock_generate, mock_save_quiz, mock_question, quiz_id)
        
        # Yield all mocks for test assertions
        yield {
            'tier': mock_tier,
            'get_record': mock_get_record,
            'parse': mock_parse,
            'generate': mock_generate,
            'save_quiz': mock_save_quiz,
            'save_metadata': mock_save_metadata
        }


@contextmanager
def mock_quota_exceeded(tier_info):
    """Context manager to mock quota exceeded scenario (no generation)."""
    with patch('handlers.quiz_handlers.get_user_tier_info') as mock_tier:
        mock_tier.return_value = tier_info
        yield mock_tier


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
            
            # Assertions
            assert 'quiz_id' in result
            assert isinstance(result['quiz_id'], str)
            assert len(result['quiz_id']) > 0  # Valid quiz ID returned
            assert 'Quiz generated successfully' in result['message']
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
            assert_quota_exceeded_error(exc_info, 'free', 5, 5)
            assert 'Upgrade to basic' in exc_info.value.detail['detail']
        
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
            assert_quota_exceeded_error(exc_info, 'basic', 100, 100)
            assert 'Upgrade to educator' in exc_info.value.detail['detail']
        
    @pytest.mark.asyncio
    async def test_text_endpoint_educator_tier_under_limit_success(
        self, mock_question
    ):
        """Test text endpoint allows quiz generation for educator tier user under limit."""
        tier_info = create_tier_info('educator', 450, 500)
        
        # Create request for advanced content
        request_data = TextQuizRequest(
            title="Test Quiz",
            content="This is test content for generating a quiz about advanced topics.",
            num_questions=10,
            question_type=["multiple_choice"]
        )
        
        with mock_quiz_generation_success(mock_question, tier_info, "quiz-456") as mocks:
            # Call handler
            result = await generate_quiz_from_text(
                data=request_data,
                current_user_id='test-user-id',
                user_token='test-token'
            )
            
            # Assertions
            assert 'quiz_id' in result
            assert isinstance(result['quiz_id'], str)
            assert len(result['quiz_id']) > 0  # Valid quiz ID returned
            assert 'Quiz generated successfully' in result['message']
            mocks['generate'].assert_called_once()
            mocks['save_quiz'].assert_called_once()


# ============================================================================
# File Endpoint Tests
# ============================================================================
    """Integration tests for quota enforcement on file generation endpoint."""
    
    @pytest.mark.asyncio
    @patch('handlers.quiz_handlers.get_user_tier_info')
    @patch('handlers.quiz_handlers.extract_text_from_plain_text')
    @patch('handlers.quiz_handlers.generate_quizzes_single_async')
    @patch('handlers.quiz_handlers.save_quiz_to_database')
    @patch('handlers.quiz_handlers.save_metadata')
    @patch('handlers.quiz_handlers.save_file_to_supabase')
    async def test_file_endpoint_free_tier_under_limit_success(
        self, mock_save_file, mock_save_metadata, mock_save_quiz,
        mock_generate, mock_extract, mock_get_tier_info
    ):
        """Test file endpoint allows quiz generation for free tier user under limit."""
        # Setup mocks
        mock_get_tier_info.return_value = {
            'id': 'test-user-id',
            'account_tier': 'free',
            'current_quiz_count': 2,
            'quota_limit': 5,
            'quota_exceeded': False
        }
        
        mock_extract.return_value = "This is extracted text from the file with enough content to generate quizzes."
        
        mock_question = MagicMock()
        mock_question.type = "multiple_choice"
        mock_question.question = "Test question?"
        mock_question.options = ["A", "B", "C", "D"]
        mock_question.correct_answer = "A"
        mock_question.explanation = "Test explanation"
        mock_question.source = "Test source"
        mock_generate.return_value = [mock_question]
        # Return tuple (quiz_id, saved_questions) to match updated signature
        import uuid
        quiz_id = str(uuid.uuid4())
        saved_questions = [{
            **{
                'type': mock_question.type,
                'question': mock_question.question,
                'options': mock_question.options,
                'correct_answer': mock_question.correct_answer,
                'explanation': mock_question.explanation,
                'source': mock_question.source
            },
            'id': str(uuid.uuid4()),
            'quiz_id': quiz_id
        }]
        mock_save_quiz.return_value = (quiz_id, saved_questions)
        
        # Create mock file
        file_content = b"Test file content for quiz generation"
        mock_file = MagicMock()
        mock_file.filename = "test.txt"
        mock_file.content_type = "text/plain"
        mock_file.read = AsyncMock(return_value=file_content)
        mock_file.seek = AsyncMock()
        
        # Call handler
        result = await generate_quiz_from_file_openai(
            file=mock_file,
            title="Test File Quiz",
            num_questions=5,
            question_type=["multiple_choice"],
            current_user_id='test-user-id',
            user_token='test-token'
        )
        
        # Assertions
        assert 'quiz_id' in result
        assert isinstance(result['quiz_id'], str)
        assert len(result['quiz_id']) > 0  # Valid quiz ID returned
        assert 'Quiz generated successfully' in result['message']
        mock_generate.assert_called_once()
        mock_save_quiz.assert_called_once()
        
    @pytest.mark.asyncio
    @patch('handlers.quiz_handlers.get_user_tier_info')
    async def test_file_endpoint_free_tier_at_limit_forbidden(self, mock_get_tier_info):
        """Test file endpoint returns 403 for free tier user at limit."""
        # Setup mock
        mock_get_tier_info.return_value = {
            'id': 'test-user-id',
            'account_tier': 'free',
            'current_quiz_count': 5,
            'quota_limit': 5,
            'quota_exceeded': True
        }
        
        # Create mock file
        file_content = b"Test file content"
        mock_file = MagicMock()
        mock_file.filename = "test.txt"
        mock_file.content_type = "text/plain"
        mock_file.read = AsyncMock(return_value=file_content)
        
        # Call handler and expect exception
        with pytest.raises(HTTPException) as exc_info:
            await generate_quiz_from_file_openai(
                file=mock_file,
                title="Test File Quiz",
                num_questions=5,
                question_type=["multiple_choice"],
                current_user_id='test-user-id',
                user_token='test-token'
            )
        
        # Assertions
        assert exc_info.value.status_code == 403
        detail = exc_info.value.detail
        assert detail['current_count'] == 5
        assert detail['quota_limit'] == 5
        assert detail['user_tier'] == 'free'
        
    @pytest.mark.asyncio
    @patch('handlers.quiz_handlers.get_user_tier_info')
    async def test_file_endpoint_basic_tier_at_limit_forbidden(self, mock_get_tier_info):
        """Test file endpoint returns 403 for basic tier user at limit."""
        # Setup mock
        mock_get_tier_info.return_value = {
            'id': 'test-user-id',
            'account_tier': 'basic',
            'current_quiz_count': 100,
            'quota_limit': 100,
            'quota_exceeded': True
        }
        
        # Create mock file
        file_content = b"Test file content"
        mock_file = MagicMock()
        mock_file.filename = "test.txt"
        mock_file.content_type = "text/plain"
        mock_file.read = AsyncMock(return_value=file_content)
        
        # Call handler and expect exception
        with pytest.raises(HTTPException) as exc_info:
            await generate_quiz_from_file_openai(
                file=mock_file,
                title="Test File Quiz",
                num_questions=5,
                question_type=["multiple_choice"],
                current_user_id='test-user-id',
                user_token='test-token'
            )
        
        # Assertions
        assert exc_info.value.status_code == 403
        detail = exc_info.value.detail
        assert detail['current_count'] == 100
        assert detail['quota_limit'] == 100
        assert detail['user_tier'] == 'basic'


class TestQuotaCheckBeforeGeneration:
    """Tests to verify quota check happens before AI generation."""
    
    @pytest.mark.asyncio
    @patch('handlers.quiz_handlers.get_user_tier_info')
    @patch('handlers.quiz_handlers.generate_quizzes_single_async')
    async def test_text_endpoint_quota_check_before_ai_call(
        self, mock_generate, mock_get_tier_info
    ):
        """Test that quota check happens before AI generation for text endpoint."""
        # Setup mock to indicate quota exceeded
        mock_get_tier_info.return_value = {
            'id': 'test-user-id',
            'account_tier': 'free',
            'current_quiz_count': 5,
            'quota_limit': 5,
            'quota_exceeded': True
        }
        
        # Create request
        request_data = TextQuizRequest(
            title="Test Quiz",
            content="This is test content for generating a quiz.",
            num_questions=5,
            question_type=["multiple_choice"]
        )
        
        # Call handler and expect exception
        with pytest.raises(HTTPException) as exc_info:
            await generate_quiz_from_text(
                data=request_data,
                current_user_id='test-user-id',
                user_token='test-token'
            )
        
        # Verify quota check failed with 403
        assert exc_info.value.status_code == 403
        
        # Verify AI generation was NOT called (no API waste)
        mock_generate.assert_not_called()
        
    @pytest.mark.asyncio
    @patch('handlers.quiz_handlers.get_user_tier_info')
    @patch('handlers.quiz_handlers.extract_text_from_plain_text')
    @patch('handlers.quiz_handlers.generate_quizzes_single_async')
    async def test_file_endpoint_quota_check_before_ai_call(
        self, mock_generate, mock_extract, mock_get_tier_info
    ):
        """Test that quota check happens before AI generation for file endpoint."""
        # Setup mock to indicate quota exceeded
        mock_get_tier_info.return_value = {
            'id': 'test-user-id',
            'account_tier': 'basic',
            'current_quiz_count': 100,
            'quota_limit': 100,
            'quota_exceeded': True
        }
        
        # Create mock file
        file_content = b"Test file content"
        mock_file = MagicMock()
        mock_file.filename = "test.txt"
        mock_file.content_type = "text/plain"
        mock_file.read = AsyncMock(return_value=file_content)
        
        # Call handler and expect exception
        with pytest.raises(HTTPException) as exc_info:
            await generate_quiz_from_file_openai(
                file=mock_file,
                title="Test File Quiz",
                num_questions=5,
                question_type=["multiple_choice"],
                current_user_id='test-user-id',
                user_token='test-token'
            )
        
        # Verify quota check failed with 403
        assert exc_info.value.status_code == 403
        
        # Verify file extraction was NOT called (no processing waste)
        mock_extract.assert_not_called()
        
        # Verify AI generation was NOT called (no API waste)
        mock_generate.assert_not_called()


class TestQuotaEnforcementFileIdEndpoint:
    """Integration tests for quota enforcement on file ID generation endpoint."""
    
    @pytest.mark.asyncio
    @patch('handlers.quiz_handlers.get_user_tier_info')
    @patch('handlers.quiz_handlers.get_file_record')
    @patch('handlers.quiz_handlers.parse_file_from_supabase')
    @patch('handlers.quiz_handlers.generate_quizzes_single_async')
    @patch('handlers.quiz_handlers.save_quiz_to_database')
    @patch('handlers.quiz_handlers.save_metadata')
    async def test_file_id_endpoint_free_tier_under_limit_success(
        self, mock_save_metadata, mock_save_quiz, mock_generate,
        mock_parse, mock_get_record, mock_get_tier_info
    ):
        """Test file ID endpoint allows quiz generation for free tier user under limit."""
        # Setup mocks
        mock_get_tier_info.return_value = {
            'id': 'test-user-id',
            'account_tier': 'free',
            'current_quiz_count': 2,
            'quota_limit': 5,
            'quota_exceeded': False
        }
        
        mock_get_record.return_value = {
            'id': 'file-123',
            'user_id': 'test-user-id',
            'original_filename': 'test.pdf',
            'file_type': 'application/pdf',
            'storage_path': 'user-files/test.pdf'
        }
        
        mock_parse.return_value = "This is extracted text from the stored file with enough content to generate quizzes."
        
        mock_question = MagicMock()
        mock_question.type = "multiple_choice"
        mock_question.question = "Test question?"
        mock_question.options = ["A", "B", "C", "D"]
        mock_question.correct_answer = "A"
        mock_question.explanation = "Test explanation"
        mock_question.source = "Test source"
        mock_generate.return_value = [mock_question]
        # Return tuple (quiz_id, saved_questions) to match updated signature
        import uuid
        quiz_id = str(uuid.uuid4())
        saved_questions = [{
            **{
                'type': mock_question.type,
                'question': mock_question.question,
                'options': mock_question.options,
                'correct_answer': mock_question.correct_answer,
                'explanation': mock_question.explanation,
                'source': mock_question.source
            },
            'id': str(uuid.uuid4()),
            'quiz_id': quiz_id
        }]
        mock_save_quiz.return_value = (quiz_id, saved_questions)
        
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
        assert 'quiz_id' in result
        assert isinstance(result['quiz_id'], str)
        assert len(result['quiz_id']) > 0  # Valid quiz ID returned
        assert 'Quiz generated successfully' in result['message']
        mock_generate.assert_called_once()
        mock_save_quiz.assert_called_once()
        
    @pytest.mark.asyncio
    @patch('handlers.quiz_handlers.get_user_tier_info')
    @patch('handlers.quiz_handlers.get_file_record')
    @patch('handlers.quiz_handlers.parse_file_from_supabase')
    async def test_file_id_endpoint_free_tier_at_limit_forbidden(
        self, mock_parse, mock_get_record, mock_get_tier_info
    ):
        """Test file ID endpoint returns 403 for free tier user at limit."""
        # Setup mocks
        mock_get_tier_info.return_value = {
            'id': 'test-user-id',
            'account_tier': 'free',
            'current_quiz_count': 5,
            'quota_limit': 5,
            'quota_exceeded': True
        }
        
        mock_get_record.return_value = {
            'id': 'file-123',
            'user_id': 'test-user-id',
            'original_filename': 'test.pdf',
            'file_type': 'application/pdf',
            'storage_path': 'user-files/test.pdf'
        }
        
        mock_parse.return_value = "This is extracted text content."
        
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
        assert exc_info.value.status_code == 403
        detail = exc_info.value.detail
        assert detail['current_count'] == 5
        assert detail['quota_limit'] == 5
        assert detail['user_tier'] == 'free'
        assert 'Upgrade to basic' in detail['detail']
        
    @pytest.mark.asyncio
    @patch('handlers.quiz_handlers.get_user_tier_info')
    @patch('handlers.quiz_handlers.get_file_record')
    @patch('handlers.quiz_handlers.parse_file_from_supabase')
    async def test_file_id_endpoint_basic_tier_at_limit_forbidden(
        self, mock_parse, mock_get_record, mock_get_tier_info
    ):
        """Test file ID endpoint returns 403 for basic tier user at limit."""
        # Setup mocks
        mock_get_tier_info.return_value = {
            'id': 'test-user-id',
            'account_tier': 'basic',
            'current_quiz_count': 100,
            'quota_limit': 100,
            'quota_exceeded': True
        }
        
        mock_get_record.return_value = {
            'id': 'file-123',
            'user_id': 'test-user-id',
            'original_filename': 'test.pdf',
            'file_type': 'application/pdf',
            'storage_path': 'user-files/test.pdf'
        }
        
        mock_parse.return_value = "This is extracted text content."
        
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
        assert exc_info.value.status_code == 403
        detail = exc_info.value.detail
        assert detail['current_count'] == 100
        assert detail['quota_limit'] == 100
        assert detail['user_tier'] == 'basic'
        assert 'Upgrade to educator' in detail['detail']
        
    @pytest.mark.asyncio
    @patch('handlers.quiz_handlers.get_user_tier_info')
    @patch('handlers.quiz_handlers.get_file_record')
    @patch('handlers.quiz_handlers.parse_file_from_supabase')
    @patch('handlers.quiz_handlers.generate_quizzes_single_async')
    async def test_file_id_endpoint_quota_check_before_ai_call(
        self, mock_generate, mock_parse, mock_get_record, mock_get_tier_info
    ):
        """Test that quota check happens before AI generation for file ID endpoint."""
        # Setup mock to indicate quota exceeded
        mock_get_tier_info.return_value = {
            'id': 'test-user-id',
            'account_tier': 'free',
            'current_quiz_count': 5,
            'quota_limit': 5,
            'quota_exceeded': True
        }
        
        mock_get_record.return_value = {
            'id': 'file-123',
            'user_id': 'test-user-id',
            'original_filename': 'test.pdf',
            'file_type': 'application/pdf',
            'storage_path': 'user-files/test.pdf'
        }
        
        mock_parse.return_value = "This is extracted text content."
        
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
        
        # Verify quota check failed with 403
        assert exc_info.value.status_code == 403
        
        # Verify AI generation was NOT called (no API waste)
        mock_generate.assert_not_called()


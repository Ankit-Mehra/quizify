"""
Integration tests for quiz search and filtering functionality.
Tests the GET /api/quiz/my-quizzes endpoint with query parameters.
"""
import pytest
from unittest.mock import patch, MagicMock
from datetime import date, datetime, time
from fastapi import HTTPException
from handlers.quiz_handlers import get_user_quizzes_handler
from services.db_services.supabase_quiz import get_user_quizzes


class TestGetUserQuizzesHandler:
    """Tests for get_user_quizzes_handler with filtering parameters."""
    
    @pytest.mark.asyncio
    @patch('handlers.quiz_handlers.get_user_quizzes')
    async def test_handler_without_filters(self, mock_get_quizzes):
        """Test handler returns all quizzes when no filters provided."""
        mock_get_quizzes.return_value = [
            {
                "id": "quiz-1",
                "title": "Python Basics",
                "created_at": "2025-10-01T10:00:00Z",
                "created_by": "user-1",
                "question_count": 10
            }
        ]
        
        result = await get_user_quizzes_handler(current_user_id="user-1")
        
        assert len(result) == 1
        assert result[0]["title"] == "Python Basics"
        mock_get_quizzes.assert_called_once_with("user-1", title=None, start_date=None, end_date=None)
    
    @pytest.mark.asyncio
    @patch('handlers.quiz_handlers.get_user_quizzes')
    async def test_handler_with_title_filter(self, mock_get_quizzes):
        """Test handler passes title filter to service."""
        mock_get_quizzes.return_value = []
        
        await get_user_quizzes_handler(current_user_id="user-1", title="python")
        
        mock_get_quizzes.assert_called_once_with("user-1", title="python", start_date=None, end_date=None)
    
    @pytest.mark.asyncio
    @patch('handlers.quiz_handlers.get_user_quizzes')
    async def test_handler_with_date_filters(self, mock_get_quizzes):
        """Test handler passes date filters to service."""
        mock_get_quizzes.return_value = []
        start = date(2025, 10, 1)
        end = date(2025, 10, 31)
        
        await get_user_quizzes_handler(
            current_user_id="user-1",
            start_date=start,
            end_date=end
        )
        
        mock_get_quizzes.assert_called_once_with("user-1", title=None, start_date=start, end_date=end)
    
    @pytest.mark.asyncio
    async def test_handler_rejects_invalid_date_range(self):
        """Test handler validates start_date <= end_date."""
        start = date(2025, 10, 31)
        end = date(2025, 10, 1)
        
        with pytest.raises(HTTPException) as exc_info:
            await get_user_quizzes_handler(
                current_user_id="user-1",
                start_date=start,
                end_date=end
            )
        
        assert exc_info.value.status_code == 400
        assert "start_date must be less than or equal to end_date" in str(exc_info.value.detail)
    
    @pytest.mark.asyncio
    @patch('handlers.quiz_handlers.get_user_quizzes')
    async def test_handler_with_all_filters(self, mock_get_quizzes):
        """Test handler with all filters combined."""
        mock_get_quizzes.return_value = []
        start = date(2025, 10, 1)
        end = date(2025, 10, 31)
        
        await get_user_quizzes_handler(
            current_user_id="user-1",
            title="machine learning",
            start_date=start,
            end_date=end
        )
        
        mock_get_quizzes.assert_called_once_with(
            "user-1",
            title="machine learning",
            start_date=start,
            end_date=end
        )


class TestGetUserQuizzesService:
    """Tests for get_user_quizzes service function with filters."""
    
    @patch('services.db_services.supabase_quiz.get_supabase')
    def test_service_title_search_case_insensitive(self, mock_get_supabase):
        """Test title search is case-insensitive."""
        mock_supabase = MagicMock()
        mock_get_supabase.return_value = mock_supabase
        
        # Mock query chain
        mock_query = MagicMock()
        mock_supabase.table.return_value.select.return_value.eq.return_value = mock_query
        mock_query.ilike.return_value = mock_query
        mock_query.order.return_value.execute.return_value.data = []
        
        get_user_quizzes("user-1", title="Python")
        
        # Verify ilike was called with wildcard pattern
        mock_query.ilike.assert_called_once_with("title", "%Python%")
    
    @patch('services.db_services.supabase_quiz.get_supabase')
    def test_service_start_date_filter(self, mock_get_supabase):
        """Test start_date filter applies gte condition."""
        mock_supabase = MagicMock()
        mock_get_supabase.return_value = mock_supabase
        
        # Mock query chain
        mock_query = MagicMock()
        mock_supabase.table.return_value.select.return_value.eq.return_value = mock_query
        mock_query.gte.return_value = mock_query
        mock_query.order.return_value.execute.return_value.data = []
        
        start = date(2025, 10, 1)
        get_user_quizzes("user-1", start_date=start)
        
        # Verify gte was called with ISO format
        mock_query.gte.assert_called_once_with("created_at", "2025-10-01")
    
    @patch('services.db_services.supabase_quiz.get_supabase')
    def test_service_end_date_filter_inclusive(self, mock_get_supabase):
        """Test end_date filter is inclusive (end of day)."""
        mock_supabase = MagicMock()
        mock_get_supabase.return_value = mock_supabase
        
        # Mock query chain
        mock_query = MagicMock()
        mock_supabase.table.return_value.select.return_value.eq.return_value = mock_query
        mock_query.lte.return_value = mock_query
        mock_query.order.return_value.execute.return_value.data = []
        
        end = date(2025, 10, 31)
        get_user_quizzes("user-1", end_date=end)
        
        # Verify lte was called with end of day timestamp
        expected_datetime = datetime.combine(end, time.max).isoformat()
        mock_query.lte.assert_called_once_with("created_at", expected_datetime)
    
    @patch('services.db_services.supabase_quiz.get_supabase')
    def test_service_combined_filters(self, mock_get_supabase):
        """Test all filters can be applied together."""
        mock_supabase = MagicMock()
        mock_get_supabase.return_value = mock_supabase
        
        # Mock query chain
        mock_query = MagicMock()
        mock_supabase.table.return_value.select.return_value.eq.return_value = mock_query
        mock_query.ilike.return_value = mock_query
        mock_query.gte.return_value = mock_query
        mock_query.lte.return_value = mock_query
        mock_query.order.return_value.execute.return_value.data = []
        
        start = date(2025, 10, 1)
        end = date(2025, 10, 31)
        get_user_quizzes("user-1", title="machine", start_date=start, end_date=end)
        
        # Verify all filters were applied
        mock_query.ilike.assert_called_once_with("title", "%machine%")
        mock_query.gte.assert_called_once_with("created_at", "2025-10-01")
        mock_query.lte.assert_called_once()
    
    @patch('services.db_services.supabase_quiz.get_supabase')
    def test_service_no_filters_returns_all(self, mock_get_supabase):
        """Test service returns all quizzes when no filters provided."""
        mock_supabase = MagicMock()
        mock_get_supabase.return_value = mock_supabase
        
        # Mock query chain
        mock_query = MagicMock()
        mock_supabase.table.return_value.select.return_value.eq.return_value = mock_query
        mock_query.order.return_value.execute.return_value.data = [
            {
                "id": "quiz-1",
                "title": "Quiz 1",
                "created_at": "2025-10-01T10:00:00Z",
                "created_by": "user-1"
            },
            {
                "id": "quiz-2",
                "title": "Quiz 2",
                "created_at": "2025-10-02T10:00:00Z",
                "created_by": "user-1"
            }
        ]
        
        # Mock question counts
        mock_questions = MagicMock()
        mock_questions.count = 10
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_questions
        
        result = get_user_quizzes("user-1")
        
        # Verify no filter methods were called (except eq for user_id)
        assert mock_query.ilike.call_count == 0
        assert mock_query.gte.call_count == 0
        assert mock_query.lte.call_count == 0
    
    @patch('services.db_services.supabase_quiz.get_supabase')
    def test_service_empty_results(self, mock_get_supabase):
        """Test service handles empty results correctly."""
        mock_supabase = MagicMock()
        mock_get_supabase.return_value = mock_supabase
        
        # Mock query chain returning no data
        mock_query = MagicMock()
        mock_supabase.table.return_value.select.return_value.eq.return_value = mock_query
        mock_query.ilike.return_value = mock_query
        mock_query.order.return_value.execute.return_value.data = []
        
        result = get_user_quizzes("user-1", title="nonexistent")
        
        assert result == []
    
    @patch('services.db_services.supabase_quiz.get_supabase')
    def test_service_partial_title_match(self, mock_get_supabase):
        """Test title filter performs partial matching."""
        mock_supabase = MagicMock()
        mock_get_supabase.return_value = mock_supabase
        
        # Mock query chain
        mock_query = MagicMock()
        mock_supabase.table.return_value.select.return_value.eq.return_value = mock_query
        mock_query.ilike.return_value = mock_query
        mock_query.order.return_value.execute.return_value.data = []
        
        # Search for "py" should match "Python", "PyTorch", etc.
        get_user_quizzes("user-1", title="py")
        
        # Verify wildcards are added on both sides
        mock_query.ilike.assert_called_once_with("title", "%py%")
    
    @patch('services.db_services.supabase_quiz.get_supabase')
    def test_service_results_ordered_by_date_desc(self, mock_get_supabase):
        """Test results are ordered by created_at descending."""
        mock_supabase = MagicMock()
        mock_get_supabase.return_value = mock_supabase
        
        # Mock query chain
        mock_query = MagicMock()
        mock_supabase.table.return_value.select.return_value.eq.return_value = mock_query
        mock_query.order.return_value.execute.return_value.data = []
        
        get_user_quizzes("user-1")
        
        # Verify order was called with DESC
        mock_query.order.assert_called_once_with("created_at", desc=True)


class TestDateValidation:
    """Tests for date validation edge cases."""
    
    @pytest.mark.asyncio
    async def test_same_start_and_end_date_allowed(self):
        """Test that start_date == end_date is valid."""
        same_date = date(2025, 10, 15)
        
        # Should not raise exception
        with patch('handlers.quiz_handlers.get_user_quizzes') as mock:
            mock.return_value = []
            await get_user_quizzes_handler(
                current_user_id="user-1",
                start_date=same_date,
                end_date=same_date
            )
    
    @pytest.mark.asyncio
    async def test_start_date_only_allowed(self):
        """Test that only start_date without end_date is valid."""
        with patch('handlers.quiz_handlers.get_user_quizzes') as mock:
            mock.return_value = []
            await get_user_quizzes_handler(
                current_user_id="user-1",
                start_date=date(2025, 10, 1)
            )
    
    @pytest.mark.asyncio
    async def test_end_date_only_allowed(self):
        """Test that only end_date without start_date is valid."""
        with patch('handlers.quiz_handlers.get_user_quizzes') as mock:
            mock.return_value = []
            await get_user_quizzes_handler(
                current_user_id="user-1",
                end_date=date(2025, 10, 31)
            )

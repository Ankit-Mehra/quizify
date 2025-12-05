"""
Integration tests for quiz search, filtering, and pagination functionality.
Tests the GET /api/quiz/my-quizzes endpoint with query parameters.
"""
import pytest
from unittest.mock import patch, MagicMock
from datetime import date, datetime, time
from fastapi import HTTPException
from handlers.quiz_handlers import get_user_quizzes_handler
from services.db_services.supabase_quiz import get_user_quizzes


class TestGetUserQuizzesHandler:
    """Tests for get_user_quizzes_handler with filtering and pagination parameters."""
    
    @pytest.mark.asyncio
    @patch('handlers.quiz_handlers.get_user_quizzes')
    async def test_handler_without_filters(self, mock_get_quizzes):
        """Test handler returns paginated response when no filters provided."""
        mock_get_quizzes.return_value = {
            "quizzes": [
                {
                    "id": "quiz-1",
                    "title": "Python Basics",
                    "created_at": "2025-10-01T10:00:00Z",
                    "created_by": "user-1",
                    "generation_mode": "standard",
                    "content_source_type": "file",
                    "question_count": 10
                }
            ],
            "total": 1,
            "page": 1,
            "limit": 20,
            "total_pages": 1,
            "has_next": False,
            "has_previous": False
        }
        
        result = await get_user_quizzes_handler(
            current_user_id="user-1",
            user_token="test-token",
            title=None,
            start_date=None,
            end_date=None,
            source_type=None,
            mode=None,
            page=1,
            limit=20
        )
        
        assert result["total"] == 1
        assert len(result["quizzes"]) == 1
        assert result["quizzes"][0]["title"] == "Python Basics"
        mock_get_quizzes.assert_called_once_with(
            "user-1",
            user_token="test-token",
            title=None,
            start_date=None,
            end_date=None,
            source_type=None,
            mode=None,
            page=1,
            limit=20
        )
    
    @pytest.mark.asyncio
    @patch('handlers.quiz_handlers.get_user_quizzes')
    async def test_handler_with_title_filter(self, mock_get_quizzes):
        """Test handler passes title filter to service."""
        mock_get_quizzes.return_value = {
            "quizzes": [],
            "total": 0,
            "page": 1,
            "limit": 20,
            "total_pages": 0,
            "has_next": False,
            "has_previous": False
        }
        
        await get_user_quizzes_handler(
            current_user_id="user-1",
            user_token="test-token",
            title="python",
            start_date=None,
            end_date=None,
            source_type=None,
            mode=None,
            page=1,
            limit=20
        )
        
        mock_get_quizzes.assert_called_once_with(
            "user-1",
            user_token="test-token",
            title="python",
            start_date=None,
            end_date=None,
            source_type=None,
            mode=None,
            page=1,
            limit=20
        )
    
    @pytest.mark.asyncio
    @patch('handlers.quiz_handlers.get_user_quizzes')
    async def test_handler_with_date_filters(self, mock_get_quizzes):
        """Test handler passes date filters to service."""
        mock_get_quizzes.return_value = {
            "quizzes": [],
            "total": 0,
            "page": 1,
            "limit": 20,
            "total_pages": 0,
            "has_next": False,
            "has_previous": False
        }
        start = date(2025, 10, 1)
        end = date(2025, 10, 31)
        
        await get_user_quizzes_handler(
            current_user_id="user-1",
            user_token="test-token",
            title=None,
            start_date=start,
            end_date=end,
            source_type=None,
            mode=None,
            page=1,
            limit=20
        )
        
        mock_get_quizzes.assert_called_once_with(
            "user-1",
            user_token="test-token",
            title=None,
            start_date=start,
            end_date=end,
            source_type=None,
            mode=None,
            page=1,
            limit=20
        )
    
    @pytest.mark.asyncio
    async def test_handler_rejects_invalid_date_range(self):
        """Test handler validates start_date <= end_date."""
        start = date(2025, 10, 31)
        end = date(2025, 10, 1)
        
        with pytest.raises(HTTPException) as exc_info:
            await get_user_quizzes_handler(
                current_user_id="user-1",
                user_token="test-token",
                title=None,
                start_date=start,
                end_date=end,
                source_type=None,
                mode=None,
                page=1,
                limit=20
            )
        
        assert exc_info.value.status_code == 400
        assert "start_date must be less than or equal to end_date" in str(exc_info.value.detail)
    
    @pytest.mark.asyncio
    async def test_handler_rejects_invalid_source_type(self):
        """Test handler validates source_type values."""
        with pytest.raises(HTTPException) as exc_info:
            await get_user_quizzes_handler(
                current_user_id="user-1",
                user_token="test-token",
                title=None,
                start_date=None,
                end_date=None,
                source_type="invalid",
                mode=None,
                page=1,
                limit=20
            )
        
        assert exc_info.value.status_code == 400
        assert "source_type must be one of: file, url, text" in str(exc_info.value.detail)
    
    @pytest.mark.asyncio
    async def test_handler_rejects_invalid_mode(self):
        """Test handler validates mode values."""
        with pytest.raises(HTTPException) as exc_info:
            await get_user_quizzes_handler(
                current_user_id="user-1",
                user_token="test-token",
                title=None,
                start_date=None,
                end_date=None,
                source_type=None,
                mode="invalid",
                page=1,
                limit=20
            )
        
        assert exc_info.value.status_code == 400
        assert "mode must be one of: standard, enhanced" in str(exc_info.value.detail)
    
    @pytest.mark.asyncio
    @patch('handlers.quiz_handlers.get_user_quizzes')
    async def test_handler_with_source_type_filter(self, mock_get_quizzes):
        """Test handler passes source_type filter to service."""
        mock_get_quizzes.return_value = {
            "quizzes": [],
            "total": 0,
            "page": 1,
            "limit": 20,
            "total_pages": 0,
            "has_next": False,
            "has_previous": False
        }
        
        await get_user_quizzes_handler(
            current_user_id="user-1",
            user_token="test-token",
            title=None,
            start_date=None,
            end_date=None,
            source_type="file",
            mode=None,
            page=1,
            limit=20
        )
        
        mock_get_quizzes.assert_called_once_with(
            "user-1",
            user_token="test-token",
            title=None,
            start_date=None,
            end_date=None,
            source_type="file",
            mode=None,
            page=1,
            limit=20
        )
    
    @pytest.mark.asyncio
    @patch('handlers.quiz_handlers.get_user_quizzes')
    async def test_handler_with_mode_filter(self, mock_get_quizzes):
        """Test handler passes mode filter to service."""
        mock_get_quizzes.return_value = {
            "quizzes": [],
            "total": 0,
            "page": 1,
            "limit": 20,
            "total_pages": 0,
            "has_next": False,
            "has_previous": False
        }
        
        await get_user_quizzes_handler(
            current_user_id="user-1",
            user_token="test-token",
            title=None,
            start_date=None,
            end_date=None,
            source_type=None,
            mode="enhanced",
            page=1,
            limit=20
        )
        
        mock_get_quizzes.assert_called_once_with(
            "user-1",
            user_token="test-token",
            title=None,
            start_date=None,
            end_date=None,
            source_type=None,
            mode="enhanced",
            page=1,
            limit=20
        )
    
    @pytest.mark.asyncio
    @patch('handlers.quiz_handlers.get_user_quizzes')
    async def test_handler_with_pagination(self, mock_get_quizzes):
        """Test handler passes pagination parameters."""
        mock_get_quizzes.return_value = {
            "quizzes": [],
            "total": 50,
            "page": 3,
            "limit": 10,
            "total_pages": 5,
            "has_next": True,
            "has_previous": True
        }
        
        result = await get_user_quizzes_handler(
            current_user_id="user-1",
            user_token="test-token",
            title=None,
            start_date=None,
            end_date=None,
            source_type=None,
            mode=None,
            page=3,
            limit=10
        )
        
        assert result["page"] == 3
        assert result["limit"] == 10
        assert result["total_pages"] == 5
        assert result["has_next"] is True
        assert result["has_previous"] is True
        mock_get_quizzes.assert_called_once_with(
            "user-1",
            user_token="test-token",
            title=None,
            start_date=None,
            end_date=None,
            source_type=None,
            mode=None,
            page=3,
            limit=10
        )
    
    @pytest.mark.asyncio
    @patch('handlers.quiz_handlers.get_user_quizzes')
    async def test_handler_with_all_filters(self, mock_get_quizzes):
        """Test handler with all filters combined."""
        mock_get_quizzes.return_value = {
            "quizzes": [],
            "total": 0,
            "page": 1,
            "limit": 20,
            "total_pages": 0,
            "has_next": False,
            "has_previous": False
        }
        start = date(2025, 10, 1)
        end = date(2025, 10, 31)
        
        await get_user_quizzes_handler(
            current_user_id="user-1",
            user_token="test-token",
            title="machine learning",
            start_date=start,
            end_date=end,
            source_type="url",
            mode="enhanced",
            page=2,
            limit=15
        )
        
        mock_get_quizzes.assert_called_once_with(
            "user-1",
            user_token="test-token",
            title="machine learning",
            start_date=start,
            end_date=end,
            source_type="url",
            mode="enhanced",
            page=2,
            limit=15
        )


class TestGetUserQuizzesService:
    """Tests for get_user_quizzes service function with filters and pagination."""
    
    @patch('services.db_services.supabase_quiz.get_supabase')
    def test_service_title_search_case_insensitive(self, mock_get_supabase):
        """Test title search is case-insensitive."""
        mock_supabase = MagicMock()
        mock_get_supabase.return_value = mock_supabase
        
        # Mock count query
        mock_count_query = MagicMock()
        mock_count_query.count = 0
        
        # Mock data query
        mock_data_query = MagicMock()
        mock_data_query.ilike.return_value = mock_data_query
        mock_data_query.order.return_value.range.return_value.execute.return_value.data = []
        
        # Setup query chain
        mock_supabase.table.return_value.select.return_value.eq.return_value = mock_data_query
        mock_supabase.table.return_value.select.return_value.eq.return_value.ilike.return_value.execute.return_value = mock_count_query
        
        get_user_quizzes("user-1", title="Python")
        
        # Verify ilike was called with wildcard pattern
        assert mock_data_query.ilike.called
        mock_data_query.ilike.assert_called_with("title", "%Python%")
    
    @patch('services.db_services.supabase_quiz.get_supabase')
    def test_service_source_type_filter(self, mock_get_supabase):
        """Test source_type filter applies eq condition."""
        mock_supabase = MagicMock()
        mock_get_supabase.return_value = mock_supabase
        
        # Mock count query
        mock_count_query = MagicMock()
        mock_count_query.count = 0
        
        # Mock data query chain
        mock_data_query = MagicMock()
        mock_data_query.eq.return_value = mock_data_query
        mock_data_query.order.return_value.range.return_value.execute.return_value.data = []
        
        mock_supabase.table.return_value.select.return_value.eq.return_value = mock_data_query
        mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = mock_count_query
        
        get_user_quizzes("user-1", source_type="file")
        
        # Verify eq was called for content_source_type
        calls = [str(call) for call in mock_data_query.eq.call_args_list]
        assert any("content_source_type" in str(call) and "file" in str(call) for call in calls)
    
    @patch('services.db_services.supabase_quiz.get_supabase')
    def test_service_mode_filter(self, mock_get_supabase):
        """Test mode filter applies eq condition."""
        mock_supabase = MagicMock()
        mock_get_supabase.return_value = mock_supabase
        
        # Mock count query
        mock_count_query = MagicMock()
        mock_count_query.count = 0
        
        # Mock data query chain
        mock_data_query = MagicMock()
        mock_data_query.eq.return_value = mock_data_query
        mock_data_query.order.return_value.range.return_value.execute.return_value.data = []
        
        mock_supabase.table.return_value.select.return_value.eq.return_value = mock_data_query
        mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = mock_count_query
        
        get_user_quizzes("user-1", mode="enhanced")
        
        # Verify eq was called for generation_mode
        calls = [str(call) for call in mock_data_query.eq.call_args_list]
        assert any("generation_mode" in str(call) and "enhanced" in str(call) for call in calls)
    
    @patch('services.db_services.supabase_quiz.get_supabase')
    def test_service_pagination_offset(self, mock_get_supabase):
        """Test pagination applies correct offset."""
        mock_supabase = MagicMock()
        mock_get_supabase.return_value = mock_supabase
        
        # Mock count query
        mock_count_query = MagicMock()
        mock_count_query.count = 50
        
        # Mock data query chain
        mock_data_query = MagicMock()
        mock_data_query.order.return_value.range.return_value.execute.return_value.data = []
        
        mock_supabase.table.return_value.select.return_value.eq.return_value = mock_data_query
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_count_query
        
        result = get_user_quizzes("user-1", page=3, limit=10)
        
        # Page 3 with limit 10 should use offset 20 (range 20-29)
        mock_data_query.order.return_value.range.assert_called_once_with(20, 29)
    
    @patch('services.db_services.supabase_quiz.get_supabase')
    def test_service_returns_paginated_response(self, mock_get_supabase):
        """Test service returns properly structured paginated response."""
        mock_supabase = MagicMock()
        mock_get_supabase.return_value = mock_supabase
        
        # Mock count query
        mock_count_query = MagicMock()
        mock_count_query.count = 25
        
        # Mock data query chain
        mock_data_query = MagicMock()
        mock_data_query.order.return_value.range.return_value.execute.return_value.data = [
            {
                "id": "quiz-1",
                "title": "Quiz 1",
                "created_at": "2025-10-01T10:00:00Z",
                "created_by": "user-1",
                "generation_mode": "standard",
                "content_source_type": "file",
                "questions": [{"count": 10}]
            }
        ]
        
        mock_supabase.table.return_value.select.return_value.eq.return_value = mock_data_query
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_count_query
        
        result = get_user_quizzes("user-1", page=2, limit=10)
        
        assert "quizzes" in result
        assert "total" in result
        assert "page" in result
        assert "limit" in result
        assert "total_pages" in result
        assert "has_next" in result
        assert "has_previous" in result
        
        assert result["total"] == 25
        assert result["page"] == 2
        assert result["limit"] == 10
        assert result["total_pages"] == 3  # ceil(25/10)
        assert result["has_next"] is True
        assert result["has_previous"] is True
    
    @patch('services.db_services.supabase_quiz.get_supabase')
    def test_service_empty_results(self, mock_get_supabase):
        """Test service handles empty results correctly."""
        mock_supabase = MagicMock()
        mock_get_supabase.return_value = mock_supabase
        
        # Mock count query
        mock_count_query = MagicMock()
        mock_count_query.count = 0
        
        # Mock data query chain
        mock_data_query = MagicMock()
        mock_data_query.ilike.return_value = mock_data_query
        mock_data_query.order.return_value.range.return_value.execute.return_value.data = []
        
        mock_supabase.table.return_value.select.return_value.eq.return_value = mock_data_query
        mock_supabase.table.return_value.select.return_value.eq.return_value.ilike.return_value.execute.return_value = mock_count_query
        
        result = get_user_quizzes("user-1", title="nonexistent")
        
        assert result["quizzes"] == []
        assert result["total"] == 0
        assert result["total_pages"] == 0
        assert result["has_next"] is False
        assert result["has_previous"] is False


class TestDateValidation:
    """Tests for date validation edge cases."""
    
    @pytest.mark.asyncio
    async def test_same_start_and_end_date_allowed(self):
        """Test that start_date == end_date is valid."""
        same_date = date(2025, 10, 15)
        
        # Should not raise exception
        with patch('handlers.quiz_handlers.get_user_quizzes') as mock:
            mock.return_value = {
                "quizzes": [],
                "total": 0,
                "page": 1,
                "limit": 20,
                "total_pages": 0,
                "has_next": False,
                "has_previous": False
            }
            await get_user_quizzes_handler(
                current_user_id="user-1",
                user_token="test-token",
                title=None,
                start_date=same_date,
                end_date=same_date,
                source_type=None,
                mode=None,
                page=1,
                limit=20
            )
    
    @pytest.mark.asyncio
    async def test_start_date_only_allowed(self):
        """Test that only start_date without end_date is valid."""
        with patch('handlers.quiz_handlers.get_user_quizzes') as mock:
            mock.return_value = {
                "quizzes": [],
                "total": 0,
                "page": 1,
                "limit": 20,
                "total_pages": 0,
                "has_next": False,
                "has_previous": False
            }
            await get_user_quizzes_handler(
                current_user_id="user-1",
                user_token="test-token",
                title=None,
                start_date=date(2025, 10, 1),
                end_date=None,
                source_type=None,
                mode=None,
                page=1,
                limit=20
            )
    
    @pytest.mark.asyncio
    async def test_end_date_only_allowed(self):
        """Test that only end_date without start_date is valid."""
        with patch('handlers.quiz_handlers.get_user_quizzes') as mock:
            mock.return_value = {
                "quizzes": [],
                "total": 0,
                "page": 1,
                "limit": 20,
                "total_pages": 0,
                "has_next": False,
                "has_previous": False
            }
            await get_user_quizzes_handler(
                current_user_id="user-1",
                user_token="test-token",
                title=None,
                start_date=None,
                end_date=date(2025, 10, 31),
                source_type=None,
                mode=None,
                page=1,
                limit=20
            )


class TestPaginationEdgeCases:
    """Tests for pagination edge cases."""
    
    @pytest.mark.asyncio
    @patch('handlers.quiz_handlers.get_user_quizzes')
    async def test_first_page_has_no_previous(self, mock_get_quizzes):
        """Test first page has has_previous=False."""
        mock_get_quizzes.return_value = {
            "quizzes": [],
            "total": 50,
            "page": 1,
            "limit": 20,
            "total_pages": 3,
            "has_next": True,
            "has_previous": False
        }
        
        result = await get_user_quizzes_handler(
            current_user_id="user-1",
            user_token="test-token",
            title=None,
            start_date=None,
            end_date=None,
            source_type=None,
            mode=None,
            page=1,
            limit=20
        )
        
        assert result["has_previous"] is False
        assert result["has_next"] is True
    
    @pytest.mark.asyncio
    @patch('handlers.quiz_handlers.get_user_quizzes')
    async def test_last_page_has_no_next(self, mock_get_quizzes):
        """Test last page has has_next=False."""
        mock_get_quizzes.return_value = {
            "quizzes": [],
            "total": 50,
            "page": 3,
            "limit": 20,
            "total_pages": 3,
            "has_next": False,
            "has_previous": True
        }
        
        result = await get_user_quizzes_handler(
            current_user_id="user-1",
            user_token="test-token",
            title=None,
            start_date=None,
            end_date=None,
            source_type=None,
            mode=None,
            page=3,
            limit=20
        )
        
        assert result["has_previous"] is True
        assert result["has_next"] is False

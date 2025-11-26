"""
Unit Tests for Export API - Epic 1: Export Infrastructure

Tests cover:
- Tier validation (free/basic can't access QTI/Moodle)
- Quiz loading and transformation
- Export handler routing
- Error handling (401, 403, 404, 422, 500)
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from datetime import datetime

from fastapi import HTTPException
from fastapi.testclient import TestClient

from schemas.export import (
    ExportFormat,
    ExportRequest,
    ExportOptions,
    QuizExportData,
    ExportQuestionMCQ,
    ExportQuestionTrueFalse,
    ExportQuestionFillBlank,
    ExportQuestionMatching
)
from services.exporters.tier_validator import (
    validate_export_tier_access,
    is_format_available_for_tier,
    get_available_formats_for_tier,
    TierInsufficientError,
    PRO_ONLY_FORMATS
)
from services.exporters.base import BaseExporter, ExportError, ExportNotImplementedError


# ============================================================================
# Tier Validator Tests
# ============================================================================

class TestTierValidator:
    """Tests for tier-based export access control."""
    
    def test_free_tier_can_access_pdf(self):
        """Free tier users should be able to export PDF."""
        # Should not raise
        validate_export_tier_access("free", ExportFormat.PDF)
    
    def test_free_tier_can_access_docx(self):
        """Free tier users should be able to export DOCX."""
        validate_export_tier_access("free", ExportFormat.DOCX)
    
    def test_free_tier_can_access_csv_quizify(self):
        """Free tier users should be able to export CSV (Quizify)."""
        validate_export_tier_access("free", ExportFormat.CSV_QUIZIFY)
    
    def test_free_tier_can_access_csv_anki(self):
        """Free tier users should be able to export CSV (Anki)."""
        validate_export_tier_access("free", ExportFormat.CSV_ANKI)
    
    def test_free_tier_can_access_share_link(self):
        """Free tier users should be able to create share links."""
        validate_export_tier_access("free", ExportFormat.SHARE_LINK)
    
    def test_free_tier_cannot_access_qti(self):
        """Free tier users should NOT be able to export QTI."""
        with pytest.raises(TierInsufficientError) as exc_info:
            validate_export_tier_access("free", ExportFormat.QTI)
        
        assert exc_info.value.status_code == 403
        assert exc_info.value.detail["error"] == "tier_insufficient"
        assert exc_info.value.detail["required_tier"] == "pro"
        assert exc_info.value.detail["current_tier"] == "free"
    
    def test_free_tier_cannot_access_moodle_xml(self):
        """Free tier users should NOT be able to export Moodle XML."""
        with pytest.raises(TierInsufficientError) as exc_info:
            validate_export_tier_access("free", ExportFormat.MOODLE_XML)
        
        assert exc_info.value.status_code == 403
        assert exc_info.value.detail["requested_format"] == "moodle_xml"
    
    def test_basic_tier_cannot_access_qti(self):
        """Basic tier users should NOT be able to export QTI."""
        with pytest.raises(TierInsufficientError):
            validate_export_tier_access("basic", ExportFormat.QTI)
    
    def test_basic_tier_cannot_access_moodle_xml(self):
        """Basic tier users should NOT be able to export Moodle XML."""
        with pytest.raises(TierInsufficientError):
            validate_export_tier_access("basic", ExportFormat.MOODLE_XML)
    
    def test_pro_tier_can_access_qti(self):
        """Pro tier users should be able to export QTI."""
        # Should not raise
        validate_export_tier_access("pro", ExportFormat.QTI)
    
    def test_pro_tier_can_access_moodle_xml(self):
        """Pro tier users should be able to export Moodle XML."""
        validate_export_tier_access("pro", ExportFormat.MOODLE_XML)
    
    def test_pro_tier_can_access_all_formats(self):
        """Pro tier users should be able to access all export formats."""
        for fmt in ExportFormat:
            # Should not raise for any format
            validate_export_tier_access("pro", fmt)
    
    def test_tier_case_insensitive(self):
        """Tier validation should be case-insensitive."""
        validate_export_tier_access("FREE", ExportFormat.PDF)
        validate_export_tier_access("Free", ExportFormat.PDF)
        validate_export_tier_access("PRO", ExportFormat.QTI)
        validate_export_tier_access("Pro", ExportFormat.QTI)
    
    def test_none_tier_defaults_to_free(self):
        """None tier should default to free (most restrictive)."""
        validate_export_tier_access(None, ExportFormat.PDF)  # OK
        with pytest.raises(TierInsufficientError):
            validate_export_tier_access(None, ExportFormat.QTI)
    
    def test_invalid_tier_raises_value_error(self):
        """Invalid tier values should raise ValueError."""
        with pytest.raises(ValueError) as exc_info:
            validate_export_tier_access("invalid_tier", ExportFormat.PDF)
        assert "invalid_tier" in str(exc_info.value).lower()


class TestFormatAvailability:
    """Tests for format availability checking."""
    
    def test_is_format_available_free_pdf(self):
        """PDF should be available for free tier."""
        assert is_format_available_for_tier("free", ExportFormat.PDF) is True
    
    def test_is_format_available_free_qti(self):
        """QTI should NOT be available for free tier."""
        assert is_format_available_for_tier("free", ExportFormat.QTI) is False
    
    def test_is_format_available_pro_qti(self):
        """QTI should be available for pro tier."""
        assert is_format_available_for_tier("pro", ExportFormat.QTI) is True
    
    def test_get_available_formats_free(self):
        """Free tier should have 5 formats available."""
        formats = get_available_formats_for_tier("free")
        assert ExportFormat.PDF in formats
        assert ExportFormat.DOCX in formats
        assert ExportFormat.CSV_QUIZIFY in formats
        assert ExportFormat.CSV_ANKI in formats
        assert ExportFormat.SHARE_LINK in formats
        assert ExportFormat.QTI not in formats
        assert ExportFormat.MOODLE_XML not in formats
    
    def test_get_available_formats_pro(self):
        """Pro tier should have all formats available."""
        formats = get_available_formats_for_tier("pro")
        assert len(formats) == len(ExportFormat)
        for fmt in ExportFormat:
            assert fmt in formats


# ============================================================================
# Export Schema Tests
# ============================================================================

class TestExportSchemas:
    """Tests for export request/response schemas."""
    
    def test_export_request_valid(self):
        """Valid export request should parse correctly."""
        request = ExportRequest(
            format=ExportFormat.PDF,
            include_answer_key=True,
            include_explanations=False
        )
        assert request.format == ExportFormat.PDF
        assert request.include_answer_key is True
        assert request.include_explanations is False
    
    def test_export_request_defaults(self):
        """Export request should have sensible defaults."""
        request = ExportRequest(format=ExportFormat.PDF)
        assert request.include_answer_key is True  # Default
        assert request.include_explanations is False  # Default
    
    def test_export_request_format_string(self):
        """Export request should accept format as string."""
        request = ExportRequest(format="pdf")
        assert request.format == "pdf"
    
    def test_export_options(self):
        """Export options should parse correctly."""
        options = ExportOptions(
            include_answer_key=False,
            include_explanations=True
        )
        assert options.include_answer_key is False
        assert options.include_explanations is True


class TestQuizExportData:
    """Tests for quiz export data model."""
    
    def test_quiz_export_data_properties(self):
        """Quiz export data should compute properties correctly."""
        quiz = QuizExportData(
            quiz_id=uuid4(),
            title="Test Quiz",
            created_at=datetime.now(),
            questions=[
                ExportQuestionMCQ(
                    id=uuid4(),
                    type="multiple_choice",
                    question="What is 2+2?",
                    options=["1", "2", "3", "4"],
                    correct_answer="4"
                ),
                ExportQuestionTrueFalse(
                    id=uuid4(),
                    type="true_false",
                    question="The sky is blue.",
                    correct_answer=True
                )
            ]
        )
        
        assert quiz.question_count == 2
        assert quiz.has_mcq is True
        assert quiz.has_true_false is True
        assert quiz.has_fill_blank is False
        assert quiz.has_matching is False
    
    def test_quiz_export_data_all_types(self):
        """Quiz export data should detect all question types."""
        quiz = QuizExportData(
            quiz_id=uuid4(),
            title="Mixed Quiz",
            created_at=datetime.now(),
            questions=[
                ExportQuestionMCQ(
                    id=uuid4(),
                    type="multiple_choice",
                    question="MCQ?",
                    options=["A", "B"],
                    correct_answer="A"
                ),
                ExportQuestionTrueFalse(
                    id=uuid4(),
                    type="true_false",
                    question="T/F?",
                    correct_answer=True
                ),
                ExportQuestionFillBlank(
                    id=uuid4(),
                    type="fill_blank",
                    question="Fill ____",
                    options=["word"],
                    correct_answer="word"
                ),
                ExportQuestionMatching(
                    id=uuid4(),
                    type="matching",
                    question="Match items",
                    left=["A", "B"],
                    right=["1", "2"],
                    correct_answer=[0, 1]
                )
            ]
        )
        
        assert quiz.has_mcq is True
        assert quiz.has_true_false is True
        assert quiz.has_fill_blank is True
        assert quiz.has_matching is True


# ============================================================================
# Base Exporter Tests
# ============================================================================

class TestBaseExporter:
    """Tests for base exporter functionality."""
    
    def test_sanitize_filename_basic(self):
        """Filename sanitization should handle basic cases."""
        assert BaseExporter._sanitize_filename("My Quiz") == "my-quiz"
        assert BaseExporter._sanitize_filename("Quiz 123") == "quiz-123"
    
    def test_sanitize_filename_special_chars(self):
        """Filename sanitization should remove unsafe characters."""
        assert BaseExporter._sanitize_filename("Quiz: Test?") == "quiz-test"
        assert BaseExporter._sanitize_filename("My/Quiz\\Test") == "myquiztest"
        # Parentheses are preserved (safe for filenames)
        assert BaseExporter._sanitize_filename('<script>alert("xss")</script>') == "scriptalert(xss)script"
    
    def test_sanitize_filename_multiple_spaces(self):
        """Filename sanitization should handle multiple spaces/hyphens."""
        assert BaseExporter._sanitize_filename("My   Quiz") == "my-quiz"
        assert BaseExporter._sanitize_filename("My - - Quiz") == "my-quiz"
    
    def test_sanitize_filename_truncation(self):
        """Filename sanitization should truncate long names."""
        long_name = "A" * 100
        result = BaseExporter._sanitize_filename(long_name, max_length=20)
        assert len(result) <= 20
    
    def test_sanitize_filename_empty(self):
        """Filename sanitization should provide fallback for empty strings."""
        assert BaseExporter._sanitize_filename("") == "quiz-export"
        assert BaseExporter._sanitize_filename("   ") == "quiz-export"
        assert BaseExporter._sanitize_filename("???") == "quiz-export"


class TestExportErrors:
    """Tests for export error classes."""
    
    def test_export_error(self):
        """ExportError should include format name."""
        error = ExportError("Test error", "pdf")
        assert "pdf" in str(error)
        assert "Test error" in str(error)
    
    def test_export_not_implemented_error(self):
        """ExportNotImplementedError should include format name."""
        error = ExportNotImplementedError("qti")
        assert "qti" in str(error)
        assert "not yet implemented" in str(error).lower()


# ============================================================================
# Quiz Loader Tests
# ============================================================================

class TestQuizLoader:
    """Tests for quiz data loading functionality."""
    
    @pytest.mark.asyncio
    async def test_load_quiz_not_found(self):
        """Loading non-existent quiz should raise 404."""
        from services.exporters.quiz_loader import load_quiz_for_export
        
        with patch("services.exporters.quiz_loader.get_authed_supabase_client") as mock_client:
            mock_supabase = MagicMock()
            mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value.data = None
            mock_client.return_value = mock_supabase
            
            with pytest.raises(HTTPException) as exc_info:
                await load_quiz_for_export(
                    str(uuid4()), 
                    str(uuid4()),
                    "fake_token"
                )
            
            assert exc_info.value.status_code == 404
    
    @pytest.mark.asyncio
    async def test_load_quiz_no_questions(self):
        """Loading quiz with no questions should raise 400."""
        from services.exporters.quiz_loader import load_quiz_for_export
        
        quiz_id = str(uuid4())
        user_id = str(uuid4())
        
        with patch("services.exporters.quiz_loader.get_authed_supabase_client") as mock_client:
            mock_supabase = MagicMock()
            
            # Mock quiz exists
            quiz_response = MagicMock()
            quiz_response.data = [{
                "id": quiz_id,
                "title": "Empty Quiz",
                "created_by": user_id,
                "created_at": "2025-01-01T00:00:00Z"
            }]
            
            # Mock no questions
            questions_response = MagicMock()
            questions_response.data = []
            
            def mock_table(name):
                mock_tbl = MagicMock()
                if name == "quizzes":
                    mock_tbl.select.return_value.eq.return_value.execute.return_value = quiz_response
                else:
                    mock_tbl.select.return_value.eq.return_value.execute.return_value = questions_response
                return mock_tbl
            
            mock_supabase.table.side_effect = mock_table
            mock_client.return_value = mock_supabase
            
            with pytest.raises(HTTPException) as exc_info:
                await load_quiz_for_export(quiz_id, user_id, "fake_token")
            
            assert exc_info.value.status_code == 400
            assert "no questions" in exc_info.value.detail.lower()


# ============================================================================
# Export Handler Tests
# ============================================================================

class TestExportHandler:
    """Tests for export handler business logic."""
    
    @pytest.mark.asyncio
    async def test_handle_export_tier_denied(self):
        """Export handler should reject tier-insufficient requests."""
        from handlers.export_handler import handle_export
        
        request = ExportRequest(format=ExportFormat.QTI)
        
        with pytest.raises(HTTPException) as exc_info:
            await handle_export(
                quiz_id=str(uuid4()),
                user_id=str(uuid4()),
                user_tier="free",
                request=request,
                user_token="fake_token"
            )
        
        assert exc_info.value.status_code == 403
    
    @pytest.mark.asyncio
    async def test_handle_export_all_formats_implemented(self):
        """All export formats should now be implemented and working."""
        from handlers.export_handler import _ensure_exporters_loaded, _EXPORTER_REGISTRY
        from schemas.export import ExportFormat
        from services.exporters.placeholder import PlaceholderExporter
        
        _ensure_exporters_loaded()
        
        # Verify no placeholder exporters remain
        for fmt in ExportFormat:
            exporter_class = _EXPORTER_REGISTRY.get(fmt)
            assert exporter_class is not None, f"Format {fmt} not registered"
            assert exporter_class != PlaceholderExporter, f"Format {fmt} still using placeholder"


class TestGetExportFormats:
    """Tests for export format availability endpoint."""
    
    @pytest.mark.asyncio
    async def test_get_formats_free_tier(self):
        """Free tier should see correct format availability."""
        from handlers.export_handler import get_export_formats_for_user
        
        formats = await get_export_formats_for_user("free")
        
        assert formats["pdf"]["available"] is True
        assert formats["pdf"]["requires_pro"] is False
        assert formats["qti"]["available"] is False
        assert formats["qti"]["requires_pro"] is True
        assert formats["moodle_xml"]["available"] is False
        assert formats["moodle_xml"]["requires_pro"] is True
    
    @pytest.mark.asyncio
    async def test_get_formats_pro_tier(self):
        """Pro tier should see all formats available."""
        from handlers.export_handler import get_export_formats_for_user
        
        formats = await get_export_formats_for_user("pro")
        
        for fmt_name, fmt_info in formats.items():
            assert fmt_info["available"] is True


# ============================================================================
# Question Transformation Tests
# ============================================================================

class TestQuestionTransformation:
    """Tests for question type transformation from DB to export models."""
    
    def test_transform_mcq_question(self):
        """MCQ questions should transform correctly."""
        from services.exporters.quiz_loader import _transform_questions
        
        db_questions = [{
            "id": str(uuid4()),
            "type": "multiple_choice",
            "question": "What is 2+2?",
            "options": ["1", "2", "3", "4"],
            "correct_answer": "4",
            "explanation": "Basic math",
            "source": "Math chapter 1"
        }]
        
        result = _transform_questions(db_questions)
        
        assert len(result) == 1
        assert result[0].type == "multiple_choice"
        assert result[0].question == "What is 2+2?"
        assert result[0].options == ["1", "2", "3", "4"]
        assert result[0].correct_answer == "4"
    
    def test_transform_true_false_question(self):
        """True/False questions should transform correctly."""
        from services.exporters.quiz_loader import _transform_questions
        
        db_questions = [{
            "id": str(uuid4()),
            "type": "true_false",
            "question": "The sky is blue.",
            "correct_answer": True,
            "explanation": None,
            "source": None
        }]
        
        result = _transform_questions(db_questions)
        
        assert len(result) == 1
        assert result[0].type == "true_false"
        assert result[0].correct_answer is True
    
    def test_transform_fill_blank_question(self):
        """Fill-in-the-blank questions should transform correctly."""
        from services.exporters.quiz_loader import _transform_questions
        
        db_questions = [{
            "id": str(uuid4()),
            "type": "fill_blank",
            "question": "The ____ is blue.",
            "options": ["sky", "grass", "sun"],
            "correct_answer": "sky",
            "explanation": None,
            "source": None
        }]
        
        result = _transform_questions(db_questions)
        
        assert len(result) == 1
        assert result[0].type == "fill_blank"
        assert result[0].correct_answer == "sky"
    
    def test_transform_matching_question(self):
        """Matching questions should transform correctly."""
        from services.exporters.quiz_loader import _transform_questions
        
        db_questions = [{
            "id": str(uuid4()),
            "type": "matching",
            "question": "Match the items",
            "left": ["Dog", "Cat"],
            "right": ["Bark", "Meow"],
            "correct_answer": [0, 1],
            "explanation": None,
            "source": None
        }]
        
        result = _transform_questions(db_questions)
        
        assert len(result) == 1
        assert result[0].type == "matching"
        assert result[0].left == ["Dog", "Cat"]
        assert result[0].right == ["Bark", "Meow"]
        assert result[0].correct_answer == [0, 1]
    
    def test_transform_unknown_type_skipped(self):
        """Unknown question types should be skipped without error."""
        from services.exporters.quiz_loader import _transform_questions
        
        db_questions = [
            {
                "id": str(uuid4()),
                "type": "unknown_type",
                "question": "Unknown?",
                "correct_answer": "?"
            },
            {
                "id": str(uuid4()),
                "type": "multiple_choice",
                "question": "Valid MCQ",
                "options": ["A", "B"],
                "correct_answer": "A"
            }
        ]
        
        result = _transform_questions(db_questions)
        
        # Only the valid MCQ should be included
        assert len(result) == 1
        assert result[0].type == "multiple_choice"

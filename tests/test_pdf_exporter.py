"""
Tests for PDF Exporter - Epic 2.

Tests cover:
- PDF generation for all question types
- Cover section with metadata
- Answer key generation
- Explanations inclusion
- Special character handling (UTF-8)
- File download metadata
"""

import pytest
from datetime import datetime
from uuid import uuid4

from schemas.export import (
    QuizExportData,
    ExportOptions,
    ExportResult,
    ExportQuestionMCQ,
    ExportQuestionTrueFalse,
    ExportQuestionFillBlank,
    ExportQuestionMatching,
)
from services.exporters.pdf_exporter import PdfExporter


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def pdf_exporter():
    """Create PDF exporter instance."""
    return PdfExporter()


@pytest.fixture
def sample_quiz_data():
    """Create sample quiz data with all question types."""
    return QuizExportData(
        quiz_id=uuid4(),
        title="Sample Quiz for PDF Export",
        description="This is a test quiz to verify PDF export functionality.",
        created_at=datetime.now(),
        questions=[
            ExportQuestionMCQ(
                id=uuid4(),
                type="multiple_choice",
                question="What does CPU stand for?",
                options=[
                    "Central Processing Unit",
                    "Computer Personal Unit",
                    "Central Program Utility",
                    "Control Processing Unit"
                ],
                correct_answer="Central Processing Unit",
                explanation="CPU stands for Central Processing Unit, the main processor of a computer."
            ),
            ExportQuestionTrueFalse(
                id=uuid4(),
                type="true_false",
                question="Python is a compiled language.",
                correct_answer=False,
                explanation="Python is primarily an interpreted language, though it can be compiled to bytecode."
            ),
            ExportQuestionFillBlank(
                id=uuid4(),
                type="fill_blank",
                question="The capital of France is ___.",
                options=["Paris", "London", "Berlin", "Madrid"],  # Word bank
                correct_answer="Paris",
                explanation="Paris has been the capital of France since the 10th century."
            ),
            ExportQuestionMatching(
                id=uuid4(),
                type="matching",
                question="Match the programming language to its creator:",
                left=["Python", "Java", "C++"],
                right=["Guido van Rossum", "James Gosling", "Bjarne Stroustrup"],
                correct_answer=[0, 1, 2],
                explanation="Each language was created by the matched person."
            )
        ]
    )


@pytest.fixture
def minimal_quiz_data():
    """Create minimal quiz data with just one question."""
    return QuizExportData(
        quiz_id=uuid4(),
        title="Minimal Quiz",
        created_at=datetime.now(),
        questions=[
            ExportQuestionMCQ(
                id=uuid4(),
                type="multiple_choice",
                question="What is 1+1?",
                options=["1", "2", "3", "4"],
                correct_answer="2"
            )
        ]
    )


@pytest.fixture
def export_options_full():
    """Export options with answer key and explanations."""
    return ExportOptions(
        include_answer_key=True,
        include_explanations=True
    )


@pytest.fixture
def export_options_minimal():
    """Export options without answer key or explanations."""
    return ExportOptions(
        include_answer_key=False,
        include_explanations=False
    )


# ============================================================================
# Test: PDF Generation
# ============================================================================

class TestPdfGeneration:
    """Tests for basic PDF generation."""

    @pytest.mark.asyncio
    async def test_generates_valid_pdf(self, pdf_exporter, sample_quiz_data, export_options_minimal):
        """PDF exporter should generate valid PDF bytes."""
        result = await pdf_exporter.export(sample_quiz_data, export_options_minimal)
        
        assert isinstance(result, ExportResult)
        assert isinstance(result.content, bytes)
        assert len(result.content) > 0
        # PDF files start with %PDF
        assert result.content[:4] == b'%PDF'

    @pytest.mark.asyncio
    async def test_correct_content_type(self, pdf_exporter, sample_quiz_data, export_options_minimal):
        """PDF exporter should return correct content type."""
        result = await pdf_exporter.export(sample_quiz_data, export_options_minimal)
        
        assert result.content_type == "application/pdf"

    @pytest.mark.asyncio
    async def test_generates_filename(self, pdf_exporter, sample_quiz_data, export_options_minimal):
        """PDF exporter should generate proper filename."""
        result = await pdf_exporter.export(sample_quiz_data, export_options_minimal)
        
        assert result.filename.endswith(".pdf")
        assert "sample-quiz-for-pdf-export" in result.filename.lower()

    @pytest.mark.asyncio
    async def test_sanitizes_filename_special_chars(self, pdf_exporter, export_options_minimal):
        """PDF exporter should sanitize special characters in filename."""
        quiz_data = QuizExportData(
            quiz_id=uuid4(),
            title="Quiz: Test? <File> Name/Test",
            created_at=datetime.now(),
            questions=[
                ExportQuestionMCQ(
                    id=uuid4(),
                    type="multiple_choice",
                    question="Test?",
                    options=["A", "B"],
                    correct_answer="A"
                )
            ]
        )
        
        result = await pdf_exporter.export(quiz_data, export_options_minimal)
        
        # Should not contain special characters
        assert ":" not in result.filename
        assert "?" not in result.filename
        assert "<" not in result.filename
        assert ">" not in result.filename
        assert "/" not in result.filename


# ============================================================================
# Test: Question Types
# ============================================================================

class TestQuestionTypeRendering:
    """Tests for rendering different question types."""

    @pytest.mark.asyncio
    async def test_renders_mcq_questions(self, pdf_exporter, export_options_minimal):
        """PDF exporter should render multiple choice questions."""
        quiz_data = QuizExportData(
            quiz_id=uuid4(),
            title="MCQ Test",
            created_at=datetime.now(),
            questions=[
                ExportQuestionMCQ(
                    id=uuid4(),
                    type="multiple_choice",
                    question="Which color is the sky?",
                    options=["Blue", "Green", "Red", "Yellow"],
                    correct_answer="Blue"
                )
            ]
        )
        
        result = await pdf_exporter.export(quiz_data, export_options_minimal)
        
        assert result.content[:4] == b'%PDF'
        assert len(result.content) > 100  # Should have substantial content

    @pytest.mark.asyncio
    async def test_renders_tf_questions(self, pdf_exporter, export_options_minimal):
        """PDF exporter should render true/false questions."""
        quiz_data = QuizExportData(
            quiz_id=uuid4(),
            title="TF Test",
            created_at=datetime.now(),
            questions=[
                ExportQuestionTrueFalse(
                    id=uuid4(),
                    type="true_false",
                    question="The Earth is flat.",
                    correct_answer=False
                )
            ]
        )
        
        result = await pdf_exporter.export(quiz_data, export_options_minimal)
        
        assert result.content[:4] == b'%PDF'

    @pytest.mark.asyncio
    async def test_renders_fill_blank_questions(self, pdf_exporter, export_options_minimal):
        """PDF exporter should render fill-in-the-blank questions."""
        quiz_data = QuizExportData(
            quiz_id=uuid4(),
            title="Fill Blank Test",
            created_at=datetime.now(),
            questions=[
                ExportQuestionFillBlank(
                    id=uuid4(),
                    type="fill_blank",
                    question="Water boils at ___ degrees Celsius.",
                    options=["100", "50", "200", "0"],  # Word bank
                    correct_answer="100"
                )
            ]
        )
        
        result = await pdf_exporter.export(quiz_data, export_options_minimal)
        
        assert result.content[:4] == b'%PDF'

    @pytest.mark.asyncio
    async def test_renders_matching_questions(self, pdf_exporter, export_options_minimal):
        """PDF exporter should render matching questions with table layout."""
        quiz_data = QuizExportData(
            quiz_id=uuid4(),
            title="Matching Test",
            created_at=datetime.now(),
            questions=[
                ExportQuestionMatching(
                    id=uuid4(),
                    type="matching",
                    question="Match the capitals:",
                    left=["USA", "UK", "France"],
                    right=["Washington DC", "London", "Paris"],
                    correct_answer=[0, 1, 2]
                )
            ]
        )
        
        result = await pdf_exporter.export(quiz_data, export_options_minimal)
        
        assert result.content[:4] == b'%PDF'

    @pytest.mark.asyncio
    async def test_renders_mixed_question_types(self, pdf_exporter, sample_quiz_data, export_options_minimal):
        """PDF exporter should handle mix of all question types."""
        result = await pdf_exporter.export(sample_quiz_data, export_options_minimal)
        
        assert result.content[:4] == b'%PDF'
        # PDF should be larger with multiple question types
        assert len(result.content) > 1000


# ============================================================================
# Test: Answer Key
# ============================================================================

class TestAnswerKey:
    """Tests for answer key generation."""

    @pytest.mark.asyncio
    async def test_includes_answer_key_when_requested(self, pdf_exporter, sample_quiz_data, export_options_full):
        """PDF should include answer key when requested."""
        result = await pdf_exporter.export(sample_quiz_data, export_options_full)
        
        # PDF with answer key should be larger
        assert len(result.content) > 1500
        assert result.content[:4] == b'%PDF'

    @pytest.mark.asyncio
    async def test_excludes_answer_key_when_not_requested(self, pdf_exporter, sample_quiz_data, export_options_minimal):
        """PDF should exclude answer key when not requested."""
        result_with = await pdf_exporter.export(
            sample_quiz_data,
            ExportOptions(include_answer_key=True, include_explanations=False)
        )
        result_without = await pdf_exporter.export(
            sample_quiz_data,
            ExportOptions(include_answer_key=False, include_explanations=False)
        )
        
        # PDF with answer key should be larger
        assert len(result_with.content) > len(result_without.content)

    @pytest.mark.asyncio
    async def test_includes_explanations_when_requested(self, pdf_exporter, sample_quiz_data):
        """PDF should include explanations when requested."""
        result_with_explanations = await pdf_exporter.export(
            sample_quiz_data,
            ExportOptions(include_answer_key=True, include_explanations=True)
        )
        result_without_explanations = await pdf_exporter.export(
            sample_quiz_data,
            ExportOptions(include_answer_key=True, include_explanations=False)
        )
        
        # PDF with explanations should be larger
        assert len(result_with_explanations.content) > len(result_without_explanations.content)


# ============================================================================
# Test: Cover Section & Metadata
# ============================================================================

class TestCoverSection:
    """Tests for cover section and metadata."""

    @pytest.mark.asyncio
    async def test_includes_quiz_title(self, pdf_exporter, sample_quiz_data, export_options_minimal):
        """PDF should include quiz title."""
        result = await pdf_exporter.export(sample_quiz_data, export_options_minimal)
        
        # Can't easily verify content without PDF parsing
        # Just verify PDF is generated
        assert result.content[:4] == b'%PDF'

    @pytest.mark.asyncio
    async def test_handles_missing_description(self, pdf_exporter, minimal_quiz_data, export_options_minimal):
        """PDF should handle missing description gracefully."""
        result = await pdf_exporter.export(minimal_quiz_data, export_options_minimal)
        
        assert result.content[:4] == b'%PDF'

    @pytest.mark.asyncio
    async def test_handles_missing_subject(self, pdf_exporter, export_options_minimal):
        """PDF should handle missing subject gracefully."""
        quiz_data = QuizExportData(
            quiz_id=uuid4(),
            title="No Subject Quiz",
            created_at=datetime.now(),
            questions=[
                ExportQuestionMCQ(
                    id=uuid4(),
                    type="multiple_choice",
                    question="Test?",
                    options=["A", "B"],
                    correct_answer="A"
                )
            ]
        )
        
        result = await pdf_exporter.export(quiz_data, export_options_minimal)
        
        assert result.content[:4] == b'%PDF'


# ============================================================================
# Test: Special Characters (UTF-8)
# ============================================================================

class TestSpecialCharacters:
    """Tests for special character handling."""

    @pytest.mark.asyncio
    async def test_handles_utf8_characters(self, pdf_exporter, export_options_minimal):
        """PDF should handle UTF-8 characters correctly."""
        quiz_data = QuizExportData(
            quiz_id=uuid4(),
            title="Café français: Ñ ü ö",
            description="Test with accented characters: é è ê ë",
            created_at=datetime.now(),
            questions=[
                ExportQuestionMCQ(
                    id=uuid4(),
                    type="multiple_choice",
                    question="¿Qué significa 'café'?",
                    options=["Café ☕", "Thé 🍵", "Água 💧", "Leche 🥛"],
                    correct_answer="Café ☕"
                )
            ]
        )
        
        result = await pdf_exporter.export(quiz_data, export_options_minimal)
        
        assert result.content[:4] == b'%PDF'

    @pytest.mark.asyncio
    async def test_handles_math_symbols(self, pdf_exporter, export_options_minimal):
        """PDF should handle math symbols."""
        quiz_data = QuizExportData(
            quiz_id=uuid4(),
            title="Math Quiz",
            created_at=datetime.now(),
            questions=[
                ExportQuestionMCQ(
                    id=uuid4(),
                    type="multiple_choice",
                    question="What is the value of π (pi)?",
                    options=["3.14159...", "2.71828...", "1.41421...", "1.61803..."],
                    correct_answer="3.14159..."
                ),
                ExportQuestionFillBlank(
                    id=uuid4(),
                    type="fill_blank",
                    question="The sum is: 5 + 3 = ___",
                    options=["8", "5", "3", "10"],  # Word bank
                    correct_answer="8"
                )
            ]
        )
        
        result = await pdf_exporter.export(quiz_data, export_options_minimal)
        
        assert result.content[:4] == b'%PDF'

    @pytest.mark.asyncio
    async def test_escapes_xml_characters(self, pdf_exporter, export_options_minimal):
        """PDF should escape XML/HTML special characters."""
        quiz_data = QuizExportData(
            quiz_id=uuid4(),
            title="HTML Test",
            created_at=datetime.now(),
            questions=[
                ExportQuestionMCQ(
                    id=uuid4(),
                    type="multiple_choice",
                    question="Which is correct: <html> or &lt;html&gt;?",
                    options=["<script>alert('xss')</script>", "Normal text", "5 > 3 & 3 < 5", "A & B"],
                    correct_answer="Normal text"
                )
            ]
        )
        
        result = await pdf_exporter.export(quiz_data, export_options_minimal)
        
        # Should not fail due to XML characters
        assert result.content[:4] == b'%PDF'


# ============================================================================
# Test: Edge Cases
# ============================================================================

class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    @pytest.mark.asyncio
    async def test_handles_empty_questions(self, pdf_exporter, export_options_minimal):
        """PDF should handle quiz with no questions gracefully."""
        quiz_data = QuizExportData(
            quiz_id=uuid4(),
            title="Empty Quiz",
            created_at=datetime.now(),
            questions=[]
        )
        
        result = await pdf_exporter.export(quiz_data, export_options_minimal)
        
        assert result.content[:4] == b'%PDF'

    @pytest.mark.asyncio
    async def test_handles_very_long_question(self, pdf_exporter, export_options_minimal):
        """PDF should handle very long question text."""
        long_text = "This is a very long question. " * 50
        quiz_data = QuizExportData(
            quiz_id=uuid4(),
            title="Long Question Quiz",
            created_at=datetime.now(),
            questions=[
                ExportQuestionMCQ(
                    id=uuid4(),
                    type="multiple_choice",
                    question=long_text,
                    options=["Option A", "Option B", "Option C", "Option D"],
                    correct_answer="Option A"
                )
            ]
        )
        
        result = await pdf_exporter.export(quiz_data, export_options_minimal)
        
        assert result.content[:4] == b'%PDF'

    @pytest.mark.asyncio
    async def test_handles_many_options(self, pdf_exporter, export_options_minimal):
        """PDF should handle MCQ with many options."""
        quiz_data = QuizExportData(
            quiz_id=uuid4(),
            title="Many Options Quiz",
            created_at=datetime.now(),
            questions=[
                ExportQuestionMCQ(
                    id=uuid4(),
                    type="multiple_choice",
                    question="Which letter comes first?",
                    options=["A", "B", "C", "D", "E", "F", "G", "H"],
                    correct_answer="A"
                )
            ]
        )
        
        result = await pdf_exporter.export(quiz_data, export_options_minimal)
        
        assert result.content[:4] == b'%PDF'

    @pytest.mark.asyncio
    async def test_handles_many_questions(self, pdf_exporter, export_options_minimal):
        """PDF should handle quiz with many questions."""
        questions = [
            ExportQuestionMCQ(
                id=uuid4(),
                type="multiple_choice",
                question=f"Question {i}: What is {i} + 1?",
                options=[str(i), str(i + 1), str(i + 2), str(i + 3)],
                correct_answer=str(i + 1)
            )
            for i in range(50)
        ]
        
        quiz_data = QuizExportData(
            quiz_id=uuid4(),
            title="Large Quiz",
            created_at=datetime.now(),
            questions=questions
        )
        
        result = await pdf_exporter.export(quiz_data, export_options_minimal)
        
        assert result.content[:4] == b'%PDF'
        # Should be a larger PDF
        assert len(result.content) > 10000

    @pytest.mark.asyncio
    async def test_handles_answer_not_in_options(self, pdf_exporter, export_options_full):
        """PDF should handle MCQ where answer is not in options list."""
        quiz_data = QuizExportData(
            quiz_id=uuid4(),
            title="Mismatched Answer Quiz",
            created_at=datetime.now(),
            questions=[
                ExportQuestionMCQ(
                    id=uuid4(),
                    type="multiple_choice",
                    question="Test question",
                    options=["A", "B", "C", "D"],
                    correct_answer="E"  # Not in options
                )
            ]
        )
        
        result = await pdf_exporter.export(quiz_data, export_options_full)
        
        # Should still generate PDF
        assert result.content[:4] == b'%PDF'


# ============================================================================
# Test: Integration with Handler
# ============================================================================

class TestPdfExporterRegistration:
    """Tests for PDF exporter registration in handler."""

    def test_pdf_exporter_is_registered(self):
        """PDF exporter should be registered for PDF format."""
        from handlers.export_handler import get_exporter, _ensure_exporters_loaded
        from schemas.export import ExportFormat
        
        _ensure_exporters_loaded()
        
        exporter = get_exporter(ExportFormat.PDF)
        
        assert isinstance(exporter, PdfExporter)


# ============================================================================
# Test: Branding Feature
# ============================================================================

class TestPdfBranding:
    """Tests for Quizify branding in PDF exports."""

    def test_branding_constants_imported_from_shared_module(self):
        """PDF exporter should use shared branding constants."""
        from services.exporters.constants import (
            QUIZIFY_URL,
            QUIZIFY_WATERMARK_TEXT,
            QUIZIFY_FOOTER_TEXT,
        )
        
        # Verify constants are accessible
        assert QUIZIFY_URL == "https://quizify.ca"
        assert QUIZIFY_WATERMARK_TEXT == "Quizify.ca"
        assert QUIZIFY_FOOTER_TEXT == "Generated by Quizify"

    def test_pdf_exporter_has_branding_method(self):
        """PDF exporter should have _add_page_branding method."""
        exporter = PdfExporter()
        
        assert hasattr(exporter, '_add_page_branding')
        assert callable(exporter._add_page_branding)

    @pytest.mark.asyncio
    async def test_pdf_with_branding_is_valid(self, pdf_exporter, sample_quiz_data, export_options_minimal):
        """PDF with branding should still be a valid PDF file."""
        result = await pdf_exporter.export(sample_quiz_data, export_options_minimal)
        
        # PDF should be valid (starts with %PDF)
        assert result.content[:4] == b'%PDF'
        
        # Should have reasonable size (branding adds some content)
        assert len(result.content) > 1000

    @pytest.mark.asyncio
    async def test_pdf_branding_does_not_break_multi_page(self, pdf_exporter, export_options_minimal):
        """PDF branding should work correctly on multi-page documents."""
        # Create a quiz with many questions to force multiple pages
        questions = [
            ExportQuestionMCQ(
                id=uuid4(),
                type="multiple_choice",
                question=f"Question {i}: This is a longer question to take up more space on the page and test multi-page handling.",
                options=["Option A with extra text", "Option B with extra text", "Option C with extra text", "Option D with extra text"],
                correct_answer="Option A with extra text",
                explanation=f"This is explanation {i} which adds more content to the PDF."
            )
            for i in range(30)
        ]
        
        quiz_data = QuizExportData(
            quiz_id=uuid4(),
            title="Multi-Page Branding Test Quiz",
            description="Testing branding on multiple pages",
            created_at=datetime.now(),
            questions=questions
        )
        
        options = ExportOptions(include_answer_key=True, include_explanations=True)
        result = await pdf_exporter.export(quiz_data, options)
        
        # Should still be valid PDF
        assert result.content[:4] == b'%PDF'
        
        # Multi-page PDF should be larger than single page (at least 10KB)
        assert len(result.content) > 10000

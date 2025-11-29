"""
Tests for DOCX Exporter - Epic 3.

Tests cover:
- DOCX generation for all question types
- Cover section with metadata
- Answer key generation
- Explanations inclusion
- File structure validation
- Special character handling
"""

import pytest
from datetime import datetime
from uuid import uuid4
from io import BytesIO
from zipfile import ZipFile

from schemas.export import (
    QuizExportData,
    ExportOptions,
    ExportResult,
    ExportQuestionMCQ,
    ExportQuestionTrueFalse,
    ExportQuestionFillBlank,
    ExportQuestionMatching,
)
from services.exporters.docx_exporter import DocxExporter


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def docx_exporter():
    """Create DOCX exporter instance."""
    return DocxExporter()


@pytest.fixture
def sample_quiz_data():
    """Create sample quiz data with all question types."""
    return QuizExportData(
        quiz_id=uuid4(),
        title="Sample Quiz for DOCX Export",
        description="This is a test quiz to verify DOCX export functionality.",
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
                explanation="CPU stands for Central Processing Unit."
            ),
            ExportQuestionTrueFalse(
                id=uuid4(),
                type="true_false",
                question="Python is a compiled language.",
                correct_answer=False,
                explanation="Python is primarily an interpreted language."
            ),
            ExportQuestionFillBlank(
                id=uuid4(),
                type="fill_blank",
                question="The capital of France is ___.",
                options=["Paris", "London", "Berlin", "Madrid"],
                correct_answer="Paris",
                explanation="Paris is the capital of France."
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
# Test: DOCX Generation
# ============================================================================

class TestDocxGeneration:
    """Tests for basic DOCX generation."""

    @pytest.mark.asyncio
    async def test_generates_valid_docx(self, docx_exporter, sample_quiz_data, export_options_minimal):
        """DOCX exporter should generate valid DOCX bytes (zip file)."""
        result = await docx_exporter.export(sample_quiz_data, export_options_minimal)
        
        assert isinstance(result, ExportResult)
        assert isinstance(result.content, bytes)
        assert len(result.content) > 0
        
        # DOCX files are zip files starting with PK
        assert result.content[:2] == b'PK'
        
        # Verify it's a valid zip file
        buffer = BytesIO(result.content)
        with ZipFile(buffer, 'r') as zf:
            # DOCX must contain these files
            assert '[Content_Types].xml' in zf.namelist()
            assert 'word/document.xml' in zf.namelist()

    @pytest.mark.asyncio
    async def test_correct_content_type(self, docx_exporter, sample_quiz_data, export_options_minimal):
        """DOCX exporter should return correct content type."""
        result = await docx_exporter.export(sample_quiz_data, export_options_minimal)
        
        assert result.content_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

    @pytest.mark.asyncio
    async def test_generates_filename(self, docx_exporter, sample_quiz_data, export_options_minimal):
        """DOCX exporter should generate proper filename."""
        result = await docx_exporter.export(sample_quiz_data, export_options_minimal)
        
        assert result.filename.endswith(".docx")
        assert "sample-quiz-for-docx-export" in result.filename.lower()

    @pytest.mark.asyncio
    async def test_sanitizes_filename_special_chars(self, docx_exporter, export_options_minimal):
        """DOCX exporter should sanitize special characters in filename."""
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
        
        result = await docx_exporter.export(quiz_data, export_options_minimal)
        
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
    async def test_renders_mcq_questions(self, docx_exporter, export_options_minimal):
        """DOCX exporter should render multiple choice questions."""
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
        
        result = await docx_exporter.export(quiz_data, export_options_minimal)
        
        assert result.content[:2] == b'PK'  # Valid DOCX/ZIP

    @pytest.mark.asyncio
    async def test_renders_tf_questions(self, docx_exporter, export_options_minimal):
        """DOCX exporter should render true/false questions."""
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
        
        result = await docx_exporter.export(quiz_data, export_options_minimal)
        
        assert result.content[:2] == b'PK'

    @pytest.mark.asyncio
    async def test_renders_fill_blank_questions(self, docx_exporter, export_options_minimal):
        """DOCX exporter should render fill-in-the-blank questions."""
        quiz_data = QuizExportData(
            quiz_id=uuid4(),
            title="Fill Blank Test",
            created_at=datetime.now(),
            questions=[
                ExportQuestionFillBlank(
                    id=uuid4(),
                    type="fill_blank",
                    question="Water boils at ___ degrees Celsius.",
                    options=["100", "50", "200", "0"],
                    correct_answer="100"
                )
            ]
        )
        
        result = await docx_exporter.export(quiz_data, export_options_minimal)
        
        assert result.content[:2] == b'PK'

    @pytest.mark.asyncio
    async def test_renders_matching_questions(self, docx_exporter, export_options_minimal):
        """DOCX exporter should render matching questions with table layout."""
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
        
        result = await docx_exporter.export(quiz_data, export_options_minimal)
        
        assert result.content[:2] == b'PK'

    @pytest.mark.asyncio
    async def test_renders_mixed_question_types(self, docx_exporter, sample_quiz_data, export_options_minimal):
        """DOCX exporter should handle mix of all question types."""
        result = await docx_exporter.export(sample_quiz_data, export_options_minimal)
        
        assert result.content[:2] == b'PK'
        # DOCX should be larger with multiple question types
        assert len(result.content) > 1000


# ============================================================================
# Test: Answer Key
# ============================================================================

class TestAnswerKey:
    """Tests for answer key generation."""

    @pytest.mark.asyncio
    async def test_includes_answer_key_when_requested(self, docx_exporter, sample_quiz_data, export_options_full):
        """DOCX should include answer key when requested."""
        result = await docx_exporter.export(sample_quiz_data, export_options_full)
        
        # DOCX with answer key should be larger
        assert len(result.content) > 1500
        assert result.content[:2] == b'PK'

    @pytest.mark.asyncio
    async def test_excludes_answer_key_when_not_requested(self, docx_exporter, sample_quiz_data, export_options_minimal):
        """DOCX should exclude answer key when not requested."""
        result_with = await docx_exporter.export(
            sample_quiz_data,
            ExportOptions(include_answer_key=True, include_explanations=False)
        )
        result_without = await docx_exporter.export(
            sample_quiz_data,
            ExportOptions(include_answer_key=False, include_explanations=False)
        )
        
        # DOCX with answer key should be larger
        assert len(result_with.content) > len(result_without.content)

    @pytest.mark.asyncio
    async def test_includes_explanations_when_requested(self, docx_exporter, sample_quiz_data):
        """DOCX should include explanations when requested."""
        result_with_explanations = await docx_exporter.export(
            sample_quiz_data,
            ExportOptions(include_answer_key=True, include_explanations=True)
        )
        result_without_explanations = await docx_exporter.export(
            sample_quiz_data,
            ExportOptions(include_answer_key=True, include_explanations=False)
        )
        
        # DOCX with explanations should be larger
        assert len(result_with_explanations.content) > len(result_without_explanations.content)


# ============================================================================
# Test: Cover Section & Metadata
# ============================================================================

class TestCoverSection:
    """Tests for cover section and metadata."""

    @pytest.mark.asyncio
    async def test_handles_missing_description(self, docx_exporter, minimal_quiz_data, export_options_minimal):
        """DOCX should handle missing description gracefully."""
        result = await docx_exporter.export(minimal_quiz_data, export_options_minimal)
        
        assert result.content[:2] == b'PK'

    @pytest.mark.asyncio
    async def test_handles_content_source(self, docx_exporter, export_options_minimal):
        """DOCX should include content source when available."""
        quiz_data = QuizExportData(
            quiz_id=uuid4(),
            title="Source Quiz",
            content_source_type="url",
            content_source_reference="https://example.com",
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
        
        result = await docx_exporter.export(quiz_data, export_options_minimal)
        
        assert result.content[:2] == b'PK'


# ============================================================================
# Test: Special Characters
# ============================================================================

class TestSpecialCharacters:
    """Tests for special character handling."""

    @pytest.mark.asyncio
    async def test_handles_utf8_characters(self, docx_exporter, export_options_minimal):
        """DOCX should handle UTF-8 characters correctly."""
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
        
        result = await docx_exporter.export(quiz_data, export_options_minimal)
        
        assert result.content[:2] == b'PK'

    @pytest.mark.asyncio
    async def test_handles_math_symbols(self, docx_exporter, export_options_minimal):
        """DOCX should handle math symbols."""
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
                    options=["8", "5", "3", "10"],
                    correct_answer="8"
                )
            ]
        )
        
        result = await docx_exporter.export(quiz_data, export_options_minimal)
        
        assert result.content[:2] == b'PK'


# ============================================================================
# Test: Edge Cases
# ============================================================================

class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    @pytest.mark.asyncio
    async def test_handles_empty_questions(self, docx_exporter, export_options_minimal):
        """DOCX should handle quiz with no questions gracefully."""
        quiz_data = QuizExportData(
            quiz_id=uuid4(),
            title="Empty Quiz",
            created_at=datetime.now(),
            questions=[]
        )
        
        result = await docx_exporter.export(quiz_data, export_options_minimal)
        
        assert result.content[:2] == b'PK'

    @pytest.mark.asyncio
    async def test_handles_very_long_question(self, docx_exporter, export_options_minimal):
        """DOCX should handle very long question text."""
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
        
        result = await docx_exporter.export(quiz_data, export_options_minimal)
        
        assert result.content[:2] == b'PK'

    @pytest.mark.asyncio
    async def test_handles_many_options(self, docx_exporter, export_options_minimal):
        """DOCX should handle MCQ with many options."""
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
        
        result = await docx_exporter.export(quiz_data, export_options_minimal)
        
        assert result.content[:2] == b'PK'

    @pytest.mark.asyncio
    async def test_handles_many_questions(self, docx_exporter, export_options_minimal):
        """DOCX should handle quiz with many questions."""
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
        
        result = await docx_exporter.export(quiz_data, export_options_minimal)
        
        assert result.content[:2] == b'PK'
        # Should be a larger DOCX
        assert len(result.content) > 10000


# ============================================================================
# Test: Integration with Handler
# ============================================================================

class TestDocxExporterRegistration:
    """Tests for DOCX exporter registration in handler."""

    def test_docx_exporter_is_registered(self):
        """DOCX exporter should be registered for DOCX format."""
        from handlers.export_handler import get_exporter, _ensure_exporters_loaded
        from schemas.export import ExportFormat
        
        _ensure_exporters_loaded()
        
        exporter = get_exporter(ExportFormat.DOCX)
        
        assert isinstance(exporter, DocxExporter)


# ============================================================================
# Test: Branding Feature
# ============================================================================

class TestDocxBranding:
    """Tests for Quizify branding in DOCX exports."""

    def test_branding_constants_imported_from_shared_module(self):
        """DOCX exporter should use shared branding constants."""
        from services.exporters.constants import QUIZIFY_URL, QUIZIFY_FOOTER_TEXT
        
        # Verify constants are accessible
        assert QUIZIFY_URL == "https://quizify.ca"
        assert QUIZIFY_FOOTER_TEXT == "Generated by Quizify"

    def test_docx_exporter_has_branding_methods(self):
        """DOCX exporter should have branding methods."""
        exporter = DocxExporter()
        
        assert hasattr(exporter, '_add_branding_footer')
        assert callable(exporter._add_branding_footer)
        assert hasattr(exporter, '_add_hyperlink')
        assert callable(exporter._add_hyperlink)

    @pytest.mark.asyncio
    async def test_docx_with_branding_is_valid(self, docx_exporter, sample_quiz_data, export_options_minimal):
        """DOCX with branding should still be a valid DOCX file."""
        result = await docx_exporter.export(sample_quiz_data, export_options_minimal)
        
        # DOCX files are ZIP archives (PK magic bytes)
        assert result.content[:2] == b'PK'
        
        # Should have reasonable size
        assert len(result.content) > 1000

    @pytest.mark.asyncio
    async def test_docx_branding_footer_in_document(self, docx_exporter, sample_quiz_data, export_options_minimal):
        """DOCX export should include branding in footer."""
        from docx import Document
        
        result = await docx_exporter.export(sample_quiz_data, export_options_minimal)
        
        # Parse the DOCX file
        doc = Document(BytesIO(result.content))
        
        # Check that footer exists and has content
        section = doc.sections[0]
        footer = section.footer
        
        # Footer should not be linked to previous (we set it explicitly)
        assert footer.is_linked_to_previous is False
        
        # Footer should have paragraphs
        assert len(footer.paragraphs) > 0

    @pytest.mark.asyncio
    async def test_docx_footer_contains_branding_text(self, docx_exporter, sample_quiz_data, export_options_minimal):
        """DOCX footer should contain 'Generated by' text."""
        from docx import Document
        
        result = await docx_exporter.export(sample_quiz_data, export_options_minimal)
        
        # Parse the DOCX file
        doc = Document(BytesIO(result.content))
        section = doc.sections[0]
        footer = section.footer
        
        # Get all text from footer
        footer_text = ""
        for para in footer.paragraphs:
            footer_text += para.text
        
        # Footer should contain "Generated by" (the hyperlink "Quizify" may not appear in plain text)
        assert "Generated by" in footer_text

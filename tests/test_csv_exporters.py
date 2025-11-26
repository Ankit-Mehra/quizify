"""
Tests for CSV Exporters - Epic 4.

Tests cover:
- Quizify CSV export for all question types
- Anki CSV (TSV) export for all question types
- UTF-8 encoding and BOM handling
- CSV escaping for special characters
- Proper format structure
"""

import pytest
from datetime import datetime
from uuid import uuid4
import csv
from io import StringIO

from schemas.export import (
    QuizExportData,
    ExportOptions,
    ExportResult,
    ExportQuestionMCQ,
    ExportQuestionTrueFalse,
    ExportQuestionFillBlank,
    ExportQuestionMatching,
)
from services.exporters.csv_quizify_exporter import CsvQuizifyExporter
from services.exporters.csv_anki_exporter import CsvAnkiExporter
from services.exporters.csv_utils import (
    escape_csv_value,
    generate_csv_bytes,
    generate_tsv_bytes,
    format_multiline_text,
)


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def csv_quizify_exporter():
    """Create Quizify CSV exporter instance."""
    return CsvQuizifyExporter()


@pytest.fixture
def csv_anki_exporter():
    """Create Anki CSV exporter instance."""
    return CsvAnkiExporter()


@pytest.fixture
def sample_quiz_data():
    """Create sample quiz data with all question types."""
    return QuizExportData(
        quiz_id=uuid4(),
        title="Sample Quiz for CSV Export",
        description="Test quiz description.",
        created_at=datetime.now(),
        questions=[
            ExportQuestionMCQ(
                id=uuid4(),
                type="multiple_choice",
                question="What is the capital of France?",
                options=["Paris", "London", "Berlin", "Madrid"],
                correct_answer="Paris",
                explanation="Paris is the capital of France."
            ),
            ExportQuestionTrueFalse(
                id=uuid4(),
                type="true_false",
                question="The Earth is flat.",
                correct_answer=False,
                explanation="The Earth is approximately spherical."
            ),
            ExportQuestionFillBlank(
                id=uuid4(),
                type="fill_blank",
                question="Water boils at ___ degrees Celsius.",
                options=["100", "50", "200", "0"],
                correct_answer="100",
                explanation="Water boils at 100°C at sea level."
            ),
            ExportQuestionMatching(
                id=uuid4(),
                type="matching",
                question="Match the country to its capital:",
                left=["France", "UK", "Germany"],
                right=["Paris", "London", "Berlin"],
                correct_answer=[0, 1, 2],
                explanation="Each country is matched with its capital city."
            )
        ]
    )


@pytest.fixture
def export_options_full():
    """Export options with answer key and explanations."""
    return ExportOptions(include_answer_key=True, include_explanations=True)


@pytest.fixture
def export_options_minimal():
    """Export options without answers."""
    return ExportOptions(include_answer_key=False, include_explanations=False)


# ============================================================================
# Test: CSV Utils
# ============================================================================

class TestCsvUtils:
    """Tests for CSV utility functions."""

    def test_escape_csv_value_none(self):
        """None values should return empty string."""
        assert escape_csv_value(None) == ""

    def test_escape_csv_value_string(self):
        """String values should pass through."""
        assert escape_csv_value("hello") == "hello"

    def test_escape_csv_value_number(self):
        """Numbers should be converted to strings."""
        assert escape_csv_value(123) == "123"

    def test_format_multiline_text(self):
        """Newlines should be converted to HTML breaks."""
        text = "Line 1\nLine 2\nLine 3"
        result = format_multiline_text(text)
        assert result == "Line 1<br>Line 2<br>Line 3"

    def test_format_multiline_text_empty(self):
        """Empty text should return empty string."""
        assert format_multiline_text("") == ""

    def test_generate_csv_bytes_with_bom(self):
        """CSV should include UTF-8 BOM when requested."""
        rows = [["Header1", "Header2"], ["Value1", "Value2"]]
        result = generate_csv_bytes(rows, include_bom=True)
        
        # Check for UTF-8 BOM
        assert result[:3] == b'\xef\xbb\xbf'
        
        # Check content
        content = result[3:].decode('utf-8')
        assert "Header1" in content
        assert "Value1" in content

    def test_generate_csv_bytes_without_bom(self):
        """CSV should not include BOM when not requested."""
        rows = [["Header1", "Header2"], ["Value1", "Value2"]]
        result = generate_csv_bytes(rows, include_bom=False)
        
        # Should not have BOM
        assert result[:3] != b'\xef\xbb\xbf'
        
        # Check content
        content = result.decode('utf-8')
        assert "Header1" in content

    def test_generate_tsv_bytes(self):
        """TSV should use tab separators."""
        rows = [["Col1", "Col2"], ["A", "B"]]
        result = generate_tsv_bytes(rows)
        
        content = result.decode('utf-8')
        assert "\t" in content
        assert "Col1\tCol2" in content


# ============================================================================
# Test: Quizify CSV Exporter
# ============================================================================

class TestQuizifyCsvExporter:
    """Tests for Quizify Native CSV export."""

    @pytest.mark.asyncio
    async def test_generates_valid_csv(self, csv_quizify_exporter, sample_quiz_data, export_options_full):
        """Should generate valid CSV bytes."""
        result = await csv_quizify_exporter.export(sample_quiz_data, export_options_full)
        
        assert isinstance(result, ExportResult)
        assert isinstance(result.content, bytes)
        assert len(result.content) > 0

    @pytest.mark.asyncio
    async def test_correct_content_type(self, csv_quizify_exporter, sample_quiz_data, export_options_full):
        """Should return correct content type."""
        result = await csv_quizify_exporter.export(sample_quiz_data, export_options_full)
        
        assert result.content_type == "text/csv; charset=utf-8"

    @pytest.mark.asyncio
    async def test_generates_filename(self, csv_quizify_exporter, sample_quiz_data, export_options_full):
        """Should generate proper filename."""
        result = await csv_quizify_exporter.export(sample_quiz_data, export_options_full)
        
        assert result.filename.endswith(".csv")

    @pytest.mark.asyncio
    async def test_includes_headers(self, csv_quizify_exporter, sample_quiz_data, export_options_full):
        """CSV should include header row."""
        result = await csv_quizify_exporter.export(sample_quiz_data, export_options_full)
        
        # Skip BOM and decode
        content = result.content[3:].decode('utf-8')
        
        assert "quiz_title" in content
        assert "question_type" in content
        assert "correct_answer" in content

    @pytest.mark.asyncio
    async def test_mcq_multiple_rows(self, csv_quizify_exporter, export_options_full):
        """MCQ questions should create multiple rows (one per option)."""
        quiz_data = QuizExportData(
            quiz_id=uuid4(),
            title="MCQ Test",
            created_at=datetime.now(),
            questions=[
                ExportQuestionMCQ(
                    id=uuid4(),
                    type="multiple_choice",
                    question="Test question?",
                    options=["A", "B", "C", "D"],
                    correct_answer="A"
                )
            ]
        )
        
        result = await csv_quizify_exporter.export(quiz_data, export_options_full)
        content = result.content[3:].decode('utf-8')
        
        # Parse CSV
        reader = csv.reader(StringIO(content))
        rows = list(reader)
        
        # 1 header + 4 option rows
        assert len(rows) == 5

    @pytest.mark.asyncio
    async def test_tf_single_row(self, csv_quizify_exporter, export_options_full):
        """True/False questions should create single row."""
        quiz_data = QuizExportData(
            quiz_id=uuid4(),
            title="TF Test",
            created_at=datetime.now(),
            questions=[
                ExportQuestionTrueFalse(
                    id=uuid4(),
                    type="true_false",
                    question="Is this true?",
                    correct_answer=True
                )
            ]
        )
        
        result = await csv_quizify_exporter.export(quiz_data, export_options_full)
        content = result.content[3:].decode('utf-8')
        
        reader = csv.reader(StringIO(content))
        rows = list(reader)
        
        # 1 header + 1 question row
        assert len(rows) == 2

    @pytest.mark.asyncio
    async def test_hides_answers_when_not_requested(self, csv_quizify_exporter, sample_quiz_data, export_options_minimal):
        """Should hide answers when include_answer_key is False."""
        result = await csv_quizify_exporter.export(sample_quiz_data, export_options_minimal)
        content = result.content[3:].decode('utf-8')
        
        # The correct_answer column should be empty (but header still present)
        reader = csv.reader(StringIO(content))
        rows = list(reader)
        
        # Check data rows (skip header)
        for row in rows[1:]:
            # correct_answer is column 9
            if len(row) > 9:
                assert row[9] == "", "Correct answer should be hidden"

    @pytest.mark.asyncio
    async def test_handles_special_characters(self, csv_quizify_exporter, export_options_full):
        """Should handle special characters correctly."""
        quiz_data = QuizExportData(
            quiz_id=uuid4(),
            title="Café Quiz, with \"quotes\" and commas",
            description="Description with <special> & 'chars'",
            created_at=datetime.now(),
            questions=[
                ExportQuestionMCQ(
                    id=uuid4(),
                    type="multiple_choice",
                    question="What is π?",
                    options=["3.14", "2.71", "1.41", "1.62"],
                    correct_answer="3.14"
                )
            ]
        )
        
        result = await csv_quizify_exporter.export(quiz_data, export_options_full)
        
        # Should not fail
        assert len(result.content) > 0
        
        # Content should be parseable
        content = result.content[3:].decode('utf-8')
        reader = csv.reader(StringIO(content))
        rows = list(reader)
        assert len(rows) > 1


# ============================================================================
# Test: Anki CSV Exporter
# ============================================================================

class TestAnkiCsvExporter:
    """Tests for Anki CSV export."""

    @pytest.mark.asyncio
    async def test_generates_valid_tsv(self, csv_anki_exporter, sample_quiz_data, export_options_full):
        """Should generate valid TSV bytes."""
        result = await csv_anki_exporter.export(sample_quiz_data, export_options_full)
        
        assert isinstance(result, ExportResult)
        assert isinstance(result.content, bytes)
        assert len(result.content) > 0

    @pytest.mark.asyncio
    async def test_correct_content_type(self, csv_anki_exporter, sample_quiz_data, export_options_full):
        """Should return TSV content type."""
        result = await csv_anki_exporter.export(sample_quiz_data, export_options_full)
        
        assert "tab-separated" in result.content_type

    @pytest.mark.asyncio
    async def test_txt_extension(self, csv_anki_exporter, sample_quiz_data, export_options_full):
        """Should generate .txt filename for Anki compatibility."""
        result = await csv_anki_exporter.export(sample_quiz_data, export_options_full)
        
        assert result.filename.endswith(".txt")
        assert "anki" in result.filename.lower()

    @pytest.mark.asyncio
    async def test_two_columns_per_row(self, csv_anki_exporter, export_options_full):
        """Anki format should have exactly 2 columns (Front, Back)."""
        quiz_data = QuizExportData(
            quiz_id=uuid4(),
            title="Anki Test",
            created_at=datetime.now(),
            questions=[
                ExportQuestionMCQ(
                    id=uuid4(),
                    type="multiple_choice",
                    question="Test?",
                    options=["A", "B", "C", "D"],
                    correct_answer="A"
                )
            ]
        )
        
        result = await csv_anki_exporter.export(quiz_data, export_options_full)
        content = result.content.decode('utf-8')
        
        # Parse TSV
        reader = csv.reader(StringIO(content), delimiter='\t')
        rows = list(reader)
        
        # Each row should have 2 columns
        for row in rows:
            assert len(row) == 2, f"Row should have 2 columns, got {len(row)}"

    @pytest.mark.asyncio
    async def test_mcq_single_card(self, csv_anki_exporter, export_options_full):
        """MCQ should create single flashcard."""
        quiz_data = QuizExportData(
            quiz_id=uuid4(),
            title="MCQ Anki Test",
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
        
        result = await csv_anki_exporter.export(quiz_data, export_options_full)
        content = result.content.decode('utf-8')
        
        reader = csv.reader(StringIO(content), delimiter='\t')
        rows = list(reader)
        
        # 1 card for MCQ
        assert len(rows) == 1

    @pytest.mark.asyncio
    async def test_matching_multiple_cards(self, csv_anki_exporter, export_options_full):
        """Matching should create one card per pair."""
        quiz_data = QuizExportData(
            quiz_id=uuid4(),
            title="Matching Anki Test",
            created_at=datetime.now(),
            questions=[
                ExportQuestionMatching(
                    id=uuid4(),
                    type="matching",
                    question="Match items",
                    left=["A", "B", "C"],
                    right=["1", "2", "3"],
                    correct_answer=[0, 1, 2]
                )
            ]
        )
        
        result = await csv_anki_exporter.export(quiz_data, export_options_full)
        content = result.content.decode('utf-8')
        
        reader = csv.reader(StringIO(content), delimiter='\t')
        rows = list(reader)
        
        # 3 cards for 3 pairs
        assert len(rows) == 3

    @pytest.mark.asyncio
    async def test_includes_html_formatting(self, csv_anki_exporter, export_options_full):
        """Anki cards should include HTML formatting."""
        quiz_data = QuizExportData(
            quiz_id=uuid4(),
            title="HTML Test",
            created_at=datetime.now(),
            questions=[
                ExportQuestionMCQ(
                    id=uuid4(),
                    type="multiple_choice",
                    question="Test?",
                    options=["A", "B"],
                    correct_answer="A",
                    explanation="Test explanation"
                )
            ]
        )
        
        result = await csv_anki_exporter.export(quiz_data, export_options_full)
        content = result.content.decode('utf-8')
        
        # Should contain HTML formatting
        assert "<br>" in content or "<b>" in content

    @pytest.mark.asyncio
    async def test_includes_explanation_when_requested(self, csv_anki_exporter, sample_quiz_data, export_options_full):
        """Should include explanation in back of card."""
        result = await csv_anki_exporter.export(sample_quiz_data, export_options_full)
        content = result.content.decode('utf-8')
        
        assert "Explanation:" in content

    @pytest.mark.asyncio
    async def test_excludes_explanation_when_not_requested(self, csv_anki_exporter, sample_quiz_data):
        """Should exclude explanation when not requested."""
        options = ExportOptions(include_answer_key=True, include_explanations=False)
        result = await csv_anki_exporter.export(sample_quiz_data, options)
        content = result.content.decode('utf-8')
        
        assert "Explanation:" not in content


# ============================================================================
# Test: Integration with Handler
# ============================================================================

class TestCsvExporterRegistration:
    """Tests for CSV exporter registration in handler."""

    def test_csv_quizify_exporter_is_registered(self):
        """Quizify CSV exporter should be registered."""
        from handlers.export_handler import get_exporter, _ensure_exporters_loaded
        from schemas.export import ExportFormat
        
        _ensure_exporters_loaded()
        
        exporter = get_exporter(ExportFormat.CSV_QUIZIFY)
        
        assert isinstance(exporter, CsvQuizifyExporter)

    def test_csv_anki_exporter_is_registered(self):
        """Anki CSV exporter should be registered."""
        from handlers.export_handler import get_exporter, _ensure_exporters_loaded
        from schemas.export import ExportFormat
        
        _ensure_exporters_loaded()
        
        exporter = get_exporter(ExportFormat.CSV_ANKI)
        
        assert isinstance(exporter, CsvAnkiExporter)

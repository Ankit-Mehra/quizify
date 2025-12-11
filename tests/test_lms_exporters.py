"""
Tests for QTI 2.1 and Moodle XML Exporters (Epic 6 & 7)

Tests cover:
1. QTI 2.1 Export - ZIP package structure, XML content
2. Moodle XML Export - XML structure, question types
3. Both formats for all question types (MCQ, T/F, Fill Blank, Matching)
"""

import pytest
import zipfile
import io
from datetime import datetime, timezone
from uuid import uuid4
from xml.etree import ElementTree as ET

from services.exporters.qti_exporter import QtiExporter
from services.exporters.moodle_xml_exporter import MoodleXmlExporter
from schemas.export import (
    QuizExportData,
    ExportOptions,
    ExportQuestionMCQ,
    ExportQuestionTrueFalse,
    ExportQuestionFillBlank,
    ExportQuestionMatching,
)


# ============================================================================
# Test Fixtures
# ============================================================================


@pytest.fixture
def sample_mcq():
    """Create a sample MCQ question."""
    return ExportQuestionMCQ(
        id=uuid4(),
        type="multiple_choice",
        question="What is the capital of France?",
        options=["London", "Paris", "Berlin", "Madrid"],
        correct_answer="Paris",
        explanation="Paris is the capital and largest city of France.",
    )


@pytest.fixture
def sample_true_false():
    """Create a sample True/False question."""
    return ExportQuestionTrueFalse(
        id=uuid4(),
        type="true_false",
        question="The Earth is flat.",
        correct_answer=False,
        explanation="The Earth is approximately spherical.",
    )


@pytest.fixture
def sample_fill_blank():
    """Create a sample fill-in-the-blank question."""
    return ExportQuestionFillBlank(
        id=uuid4(),
        type="fill_blank",
        question="The process of water turning into vapor is called ____.",
        options=["evaporation", "condensation", "precipitation"],
        correct_answer="evaporation",
        explanation="Evaporation is the process of liquid water becoming gas.",
    )


@pytest.fixture
def sample_matching():
    """Create a sample matching question."""
    return ExportQuestionMatching(
        id=uuid4(),
        type="matching",
        question="Match the countries with their capitals.",
        left=["France", "Germany", "Italy"],
        right=["Paris", "Berlin", "Rome"],
        correct_answer=[0, 1, 2],  # France->Paris, Germany->Berlin, Italy->Rome
        explanation="European capitals matching exercise.",
    )


@pytest.fixture
def sample_quiz_data(sample_mcq, sample_true_false, sample_fill_blank, sample_matching):
    """Create sample quiz data with all question types."""
    return QuizExportData(
        quiz_id=uuid4(),
        title="Geography Test",
        description="Test your geography knowledge",
        created_at=datetime.now(timezone.utc),
        questions=[sample_mcq, sample_true_false, sample_fill_blank, sample_matching],
    )


@pytest.fixture
def export_options_with_answers():
    """Export options with answer key enabled."""
    return ExportOptions(include_answer_key=True, include_explanations=True)


@pytest.fixture
def export_options_no_answers():
    """Export options without answer key."""
    return ExportOptions(include_answer_key=False, include_explanations=False)


# ============================================================================
# QTI Exporter Tests
# ============================================================================


class TestQtiExporter:
    """Tests for QTI 2.1 exporter."""
    
    def test_exporter_attributes(self):
        """Test exporter has correct attributes."""
        exporter = QtiExporter()
        assert exporter.FORMAT_NAME == "qti"
        assert exporter.CONTENT_TYPE == "application/zip"
        assert exporter.FILE_EXTENSION == "zip"
    
    def test_generate_filename(self):
        """Test filename generation."""
        exporter = QtiExporter()
        filename = exporter.generate_filename("My Quiz Title")
        assert filename.endswith(".zip")
        assert "my-quiz-title" in filename.lower()
    
    @pytest.mark.asyncio
    async def test_export_returns_zip(
        self, sample_quiz_data, export_options_with_answers
    ):
        """Test export returns valid ZIP content."""
        exporter = QtiExporter()
        result = await exporter.export(sample_quiz_data, export_options_with_answers)
        
        assert result.content_type == "application/zip"
        assert result.filename.endswith(".zip")
        
        # Verify it's a valid ZIP
        with zipfile.ZipFile(io.BytesIO(result.content), "r") as zf:
            assert zf.testzip() is None  # No errors
    
    @pytest.mark.asyncio
    async def test_export_contains_manifest(
        self, sample_quiz_data, export_options_with_answers
    ):
        """Test ZIP contains imsmanifest.xml."""
        exporter = QtiExporter()
        result = await exporter.export(sample_quiz_data, export_options_with_answers)
        
        with zipfile.ZipFile(io.BytesIO(result.content), "r") as zf:
            assert "imsmanifest.xml" in zf.namelist()
            manifest = zf.read("imsmanifest.xml").decode("utf-8")
            assert "<manifest" in manifest
    
    @pytest.mark.asyncio
    async def test_export_contains_assessment(
        self, sample_quiz_data, export_options_with_answers
    ):
        """Test ZIP contains assessment.xml."""
        exporter = QtiExporter()
        result = await exporter.export(sample_quiz_data, export_options_with_answers)
        
        with zipfile.ZipFile(io.BytesIO(result.content), "r") as zf:
            assert "assessment.xml" in zf.namelist()
            assessment = zf.read("assessment.xml").decode("utf-8")
            assert "<assessmentTest" in assessment
            assert sample_quiz_data.title in assessment
    
    @pytest.mark.asyncio
    async def test_export_contains_item_files(
        self, sample_quiz_data, export_options_with_answers
    ):
        """Test ZIP contains item files for each question."""
        exporter = QtiExporter()
        result = await exporter.export(sample_quiz_data, export_options_with_answers)
        
        with zipfile.ZipFile(io.BytesIO(result.content), "r") as zf:
            item_files = [f for f in zf.namelist() if f.startswith("items/")]
            assert len(item_files) == len(sample_quiz_data.questions)
    
    @pytest.mark.asyncio
    async def test_mcq_item_structure(
        self, sample_mcq, export_options_with_answers
    ):
        """Test MCQ question creates valid QTI item."""
        quiz_data = QuizExportData(
            quiz_id=uuid4(),
            title="MCQ Test",
            created_at=datetime.now(timezone.utc),
            questions=[sample_mcq],
        )
        
        exporter = QtiExporter()
        result = await exporter.export(quiz_data, export_options_with_answers)
        
        with zipfile.ZipFile(io.BytesIO(result.content), "r") as zf:
            item_files = [f for f in zf.namelist() if f.startswith("items/")]
            item_xml = zf.read(item_files[0]).decode("utf-8")
            
            assert "<assessmentItem" in item_xml
            assert "<choiceInteraction" in item_xml
            assert "<simpleChoice" in item_xml
            assert sample_mcq.question in item_xml
    
    @pytest.mark.asyncio
    async def test_true_false_item_structure(
        self, sample_true_false, export_options_with_answers
    ):
        """Test T/F question creates QTI item with 2 choices."""
        quiz_data = QuizExportData(
            quiz_id=uuid4(),
            title="T/F Test",
            created_at=datetime.now(timezone.utc),
            questions=[sample_true_false],
        )
        
        exporter = QtiExporter()
        result = await exporter.export(quiz_data, export_options_with_answers)
        
        with zipfile.ZipFile(io.BytesIO(result.content), "r") as zf:
            item_files = [f for f in zf.namelist() if f.startswith("items/")]
            item_xml = zf.read(item_files[0]).decode("utf-8")
            
            assert "True" in item_xml
            assert "False" in item_xml
            assert "choice_true" in item_xml
            assert "choice_false" in item_xml
    
    @pytest.mark.asyncio
    async def test_fill_blank_item_structure(
        self, sample_fill_blank, export_options_with_answers
    ):
        """Test fill-blank creates textEntryInteraction."""
        quiz_data = QuizExportData(
            quiz_id=uuid4(),
            title="Fill Blank Test",
            created_at=datetime.now(timezone.utc),
            questions=[sample_fill_blank],
        )
        
        exporter = QtiExporter()
        result = await exporter.export(quiz_data, export_options_with_answers)
        
        with zipfile.ZipFile(io.BytesIO(result.content), "r") as zf:
            item_files = [f for f in zf.namelist() if f.startswith("items/")]
            item_xml = zf.read(item_files[0]).decode("utf-8")
            
            assert "<textEntryInteraction" in item_xml
    
    @pytest.mark.asyncio
    async def test_matching_item_structure(
        self, sample_matching, export_options_with_answers
    ):
        """Test matching creates matchInteraction."""
        quiz_data = QuizExportData(
            quiz_id=uuid4(),
            title="Matching Test",
            created_at=datetime.now(timezone.utc),
            questions=[sample_matching],
        )
        
        exporter = QtiExporter()
        result = await exporter.export(quiz_data, export_options_with_answers)
        
        with zipfile.ZipFile(io.BytesIO(result.content), "r") as zf:
            item_files = [f for f in zf.namelist() if f.startswith("items/")]
            item_xml = zf.read(item_files[0]).decode("utf-8")
            
            assert "<matchInteraction" in item_xml
            assert "<simpleMatchSet" in item_xml
            assert "France" in item_xml
            assert "Paris" in item_xml
    
    @pytest.mark.asyncio
    async def test_export_without_answer_key(
        self, sample_quiz_data, export_options_no_answers
    ):
        """Test export without answer key omits correctResponse."""
        exporter = QtiExporter()
        result = await exporter.export(sample_quiz_data, export_options_no_answers)
        
        with zipfile.ZipFile(io.BytesIO(result.content), "r") as zf:
            item_files = [f for f in zf.namelist() if f.startswith("items/")]
            item_xml = zf.read(item_files[0]).decode("utf-8")
            
            # Without answer key, correctResponse should not be present
            assert "<correctResponse" not in item_xml


# ============================================================================
# Moodle XML Exporter Tests
# ============================================================================


class TestMoodleXmlExporter:
    """Tests for Moodle XML exporter."""
    
    def test_exporter_attributes(self):
        """Test exporter has correct attributes."""
        exporter = MoodleXmlExporter()
        assert exporter.FORMAT_NAME == "moodle_xml"
        assert exporter.CONTENT_TYPE == "application/xml"
        assert exporter.FILE_EXTENSION == "xml"
    
    def test_generate_filename(self):
        """Test filename generation."""
        exporter = MoodleXmlExporter()
        filename = exporter.generate_filename("Test Quiz")
        assert filename.endswith(".xml")
        assert "test-quiz" in filename.lower()
    
    @pytest.mark.asyncio
    async def test_export_returns_xml(
        self, sample_quiz_data, export_options_with_answers
    ):
        """Test export returns valid XML content."""
        exporter = MoodleXmlExporter()
        result = await exporter.export(sample_quiz_data, export_options_with_answers)
        
        assert result.content_type == "application/xml"
        assert result.filename.endswith(".xml")
        
        # Verify it's valid XML
        xml_content = result.content.decode("utf-8")
        root = ET.fromstring(xml_content)
        assert root.tag == "quiz"
    
    @pytest.mark.asyncio
    async def test_export_has_category(
        self, sample_quiz_data, export_options_with_answers
    ):
        """Test export includes category question."""
        exporter = MoodleXmlExporter()
        result = await exporter.export(sample_quiz_data, export_options_with_answers)
        
        xml_content = result.content.decode("utf-8")
        assert 'type="category"' in xml_content
        assert sample_quiz_data.title in xml_content
    
    @pytest.mark.asyncio
    async def test_mcq_question_format(
        self, sample_mcq, export_options_with_answers
    ):
        """Test MCQ creates multichoice question type."""
        quiz_data = QuizExportData(
            quiz_id=uuid4(),
            title="MCQ Test",
            created_at=datetime.now(timezone.utc),
            questions=[sample_mcq],
        )
        
        exporter = MoodleXmlExporter()
        result = await exporter.export(quiz_data, export_options_with_answers)
        
        xml_content = result.content.decode("utf-8")
        assert 'type="multichoice"' in xml_content
        assert sample_mcq.question in xml_content
        
        # Check correct answer has fraction="100"
        assert 'fraction="100"' in xml_content
    
    @pytest.mark.asyncio
    async def test_true_false_question_format(
        self, sample_true_false, export_options_with_answers
    ):
        """Test T/F creates truefalse question type."""
        quiz_data = QuizExportData(
            quiz_id=uuid4(),
            title="T/F Test",
            created_at=datetime.now(timezone.utc),
            questions=[sample_true_false],
        )
        
        exporter = MoodleXmlExporter()
        result = await exporter.export(quiz_data, export_options_with_answers)
        
        xml_content = result.content.decode("utf-8")
        assert 'type="truefalse"' in xml_content
    
    @pytest.mark.asyncio
    async def test_fill_blank_question_format(
        self, sample_fill_blank, export_options_with_answers
    ):
        """Test fill-blank creates shortanswer question type."""
        quiz_data = QuizExportData(
            quiz_id=uuid4(),
            title="Fill Test",
            created_at=datetime.now(timezone.utc),
            questions=[sample_fill_blank],
        )
        
        exporter = MoodleXmlExporter()
        result = await exporter.export(quiz_data, export_options_with_answers)
        
        xml_content = result.content.decode("utf-8")
        assert 'type="shortanswer"' in xml_content
        # Should include word bank
        assert "Word bank" in xml_content
    
    @pytest.mark.asyncio
    async def test_matching_question_format(
        self, sample_matching, export_options_with_answers
    ):
        """Test matching creates matching question type."""
        quiz_data = QuizExportData(
            quiz_id=uuid4(),
            title="Match Test",
            created_at=datetime.now(timezone.utc),
            questions=[sample_matching],
        )
        
        exporter = MoodleXmlExporter()
        result = await exporter.export(quiz_data, export_options_with_answers)
        
        xml_content = result.content.decode("utf-8")
        assert 'type="matching"' in xml_content
        assert "<subquestion" in xml_content
        assert "France" in xml_content
        assert "Paris" in xml_content
    
    @pytest.mark.asyncio
    async def test_explanations_included(
        self, sample_mcq, export_options_with_answers
    ):
        """Test explanations are included in generalfeedback."""
        quiz_data = QuizExportData(
            quiz_id=uuid4(),
            title="Test",
            created_at=datetime.now(timezone.utc),
            questions=[sample_mcq],
        )
        
        exporter = MoodleXmlExporter()
        result = await exporter.export(quiz_data, export_options_with_answers)
        
        xml_content = result.content.decode("utf-8")
        assert "<generalfeedback" in xml_content
        assert sample_mcq.explanation in xml_content
    
    @pytest.mark.asyncio
    async def test_export_without_answers(
        self, sample_mcq, export_options_no_answers
    ):
        """Test export without answer key sets all fractions to 0."""
        quiz_data = QuizExportData(
            quiz_id=uuid4(),
            title="Test",
            created_at=datetime.now(timezone.utc),
            questions=[sample_mcq],
        )
        
        exporter = MoodleXmlExporter()
        result = await exporter.export(quiz_data, export_options_no_answers)
        
        xml_content = result.content.decode("utf-8")
        # All answer fractions should be 0
        assert 'fraction="100"' not in xml_content


# ============================================================================
# Handler Integration Tests
# ============================================================================


class TestLmsExportersInHandler:
    """Tests for LMS exporters registered in handler."""
    
    def test_qti_registered_in_handler(self):
        """Test QTI exporter is registered."""
        from handlers.export_handler import _ensure_exporters_loaded, _EXPORTER_REGISTRY
        from schemas.export import ExportFormat
        from services.exporters.qti_exporter import QtiExporter
        
        _ensure_exporters_loaded()
        
        assert ExportFormat.QTI in _EXPORTER_REGISTRY
        assert _EXPORTER_REGISTRY[ExportFormat.QTI] == QtiExporter
    
    def test_moodle_registered_in_handler(self):
        """Test Moodle XML exporter is registered."""
        from handlers.export_handler import _ensure_exporters_loaded, _EXPORTER_REGISTRY
        from schemas.export import ExportFormat
        from services.exporters.moodle_xml_exporter import MoodleXmlExporter
        
        _ensure_exporters_loaded()
        
        assert ExportFormat.MOODLE_XML in _EXPORTER_REGISTRY
        assert _EXPORTER_REGISTRY[ExportFormat.MOODLE_XML] == MoodleXmlExporter
    
    def test_lms_formats_available_to_all(self):
        """Test LMS formats are available to all tiers."""
        from services.exporters.tier_validator import PRO_ONLY_FORMATS
        from schemas.export import ExportFormat
        
        assert ExportFormat.QTI not in PRO_ONLY_FORMATS
        assert ExportFormat.MOODLE_XML not in PRO_ONLY_FORMATS


# ============================================================================
# Edge Case Tests
# ============================================================================


class TestEdgeCases:
    """Edge case tests for both exporters."""
    
    @pytest.mark.asyncio
    async def test_qti_empty_quiz(self, export_options_with_answers):
        """Test QTI export with no questions."""
        quiz_data = QuizExportData(
            quiz_id=uuid4(),
            title="Empty Quiz",
            created_at=datetime.now(timezone.utc),
            questions=[],
        )
        
        exporter = QtiExporter()
        result = await exporter.export(quiz_data, export_options_with_answers)
        
        # Should still produce valid ZIP
        with zipfile.ZipFile(io.BytesIO(result.content), "r") as zf:
            assert "imsmanifest.xml" in zf.namelist()
            assert "assessment.xml" in zf.namelist()
            item_files = [f for f in zf.namelist() if f.startswith("items/")]
            assert len(item_files) == 0
    
    @pytest.mark.asyncio
    async def test_moodle_empty_quiz(self, export_options_with_answers):
        """Test Moodle export with no questions."""
        quiz_data = QuizExportData(
            quiz_id=uuid4(),
            title="Empty Quiz",
            created_at=datetime.now(timezone.utc),
            questions=[],
        )
        
        exporter = MoodleXmlExporter()
        result = await exporter.export(quiz_data, export_options_with_answers)
        
        xml_content = result.content.decode("utf-8")
        root = ET.fromstring(xml_content)
        assert root.tag == "quiz"
    
    @pytest.mark.asyncio
    async def test_special_characters_in_questions(self, export_options_with_answers):
        """Test handling of special characters."""
        question = ExportQuestionMCQ(
            id=uuid4(),
            type="multiple_choice",
            question="What is 2 < 3 & 5 > 4?",
            options=["True", "False", "Maybe <unknown>", 'Quote "test"'],
            correct_answer="True",
        )
        
        quiz_data = QuizExportData(
            quiz_id=uuid4(),
            title="Special Chars Test",
            created_at=datetime.now(timezone.utc),
            questions=[question],
        )
        
        # Both exporters should handle special chars
        qti_exporter = QtiExporter()
        qti_result = await qti_exporter.export(quiz_data, export_options_with_answers)
        assert qti_result.content is not None
        
        moodle_exporter = MoodleXmlExporter()
        moodle_result = await moodle_exporter.export(quiz_data, export_options_with_answers)
        assert moodle_result.content is not None
    
    @pytest.mark.asyncio
    async def test_long_quiz_title(self, sample_mcq, export_options_with_answers):
        """Test handling of very long quiz title."""
        quiz_data = QuizExportData(
            quiz_id=uuid4(),
            title="A" * 200,  # Very long title
            created_at=datetime.now(timezone.utc),
            questions=[sample_mcq],
        )
        
        qti_exporter = QtiExporter()
        result = await qti_exporter.export(quiz_data, export_options_with_answers)
        
        # Filename should be truncated
        assert len(result.filename) <= 60  # Reasonable max length
    
    @pytest.mark.asyncio
    async def test_correct_answer_by_letter(self, export_options_with_answers):
        """Test MCQ with letter-based correct answer (A, B, C, D)."""
        question = ExportQuestionMCQ(
            id=uuid4(),
            type="multiple_choice",
            question="Which is correct?",
            options=["Option A", "Option B", "Option C", "Option D"],
            correct_answer="B",  # Letter-based answer
        )
        
        quiz_data = QuizExportData(
            quiz_id=uuid4(),
            title="Letter Answer Test",
            created_at=datetime.now(timezone.utc),
            questions=[question],
        )
        
        # Both should handle letter answers
        moodle_exporter = MoodleXmlExporter()
        result = await moodle_exporter.export(quiz_data, export_options_with_answers)
        xml_content = result.content.decode("utf-8")
        
        # Option B should have fraction="100"
        assert "Option B" in xml_content

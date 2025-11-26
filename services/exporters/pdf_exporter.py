"""
PDF Exporter for Quiz Export Feature.

Uses ReportLab to generate professional PDF documents with:
- Quiz title and metadata cover section
- Numbered questions with proper formatting for all types
- Optional answer key on separate pages
- Optional explanations
"""

import io
import logging
from datetime import datetime
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    PageBreak,
    ListFlowable,
    ListItem,
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from schemas.export import (
    QuizExportData,
    ExportOptions,
    ExportResult,
    ExportQuestionMCQ,
    ExportQuestionTrueFalse,
    ExportQuestionFillBlank,
    ExportQuestionMatching,
)
from services.exporters.base import BaseExporter

logger = logging.getLogger(__name__)


class PdfExporter(BaseExporter):
    """
    PDF Exporter using ReportLab.
    
    Generates printable PDF quizzes with professional formatting for:
    - Multiple choice questions (A, B, C, D options)
    - True/False questions
    - Fill-in-the-blank questions
    - Matching questions (two-column layout)
    """

    def __init__(self):
        """Initialize PDF exporter with styles."""
        self.styles = getSampleStyleSheet()
        self._setup_custom_styles()

    def _setup_custom_styles(self) -> None:
        """Set up custom paragraph styles for quiz elements."""
        # Title style
        self.styles.add(ParagraphStyle(
            name='QuizTitle',
            parent=self.styles['Heading1'],
            fontSize=24,
            spaceAfter=12,
            alignment=1,  # Center
            textColor=colors.HexColor('#1a1a2e'),
        ))
        
        # Subtitle/description style
        self.styles.add(ParagraphStyle(
            name='QuizDescription',
            parent=self.styles['Normal'],
            fontSize=12,
            spaceAfter=20,
            alignment=1,  # Center
            textColor=colors.HexColor('#4a4a4a'),
        ))
        
        # Metadata style
        self.styles.add(ParagraphStyle(
            name='QuizMeta',
            parent=self.styles['Normal'],
            fontSize=10,
            spaceAfter=6,
            alignment=1,
            textColor=colors.HexColor('#666666'),
        ))
        
        # Question number style
        self.styles.add(ParagraphStyle(
            name='QuestionNumber',
            parent=self.styles['Normal'],
            fontSize=12,
            fontName='Helvetica-Bold',
            spaceBefore=16,
            spaceAfter=4,
            textColor=colors.HexColor('#1a1a2e'),
        ))
        
        # Question text style
        self.styles.add(ParagraphStyle(
            name='QuestionText',
            parent=self.styles['Normal'],
            fontSize=11,
            spaceAfter=8,
            leading=14,
        ))
        
        # Option style
        self.styles.add(ParagraphStyle(
            name='OptionText',
            parent=self.styles['Normal'],
            fontSize=10,
            leftIndent=20,
            spaceAfter=4,
            leading=12,
        ))
        
        # Answer key header style
        self.styles.add(ParagraphStyle(
            name='AnswerKeyHeader',
            parent=self.styles['Heading2'],
            fontSize=18,
            spaceBefore=20,
            spaceAfter=16,
            alignment=1,
            textColor=colors.HexColor('#1a1a2e'),
        ))
        
        # Answer style
        self.styles.add(ParagraphStyle(
            name='AnswerText',
            parent=self.styles['Normal'],
            fontSize=10,
            spaceAfter=4,
            textColor=colors.HexColor('#2d6a4f'),
        ))
        
        # Explanation style
        self.styles.add(ParagraphStyle(
            name='ExplanationText',
            parent=self.styles['Normal'],
            fontSize=9,
            leftIndent=20,
            spaceAfter=8,
            textColor=colors.HexColor('#4a4a4a'),
            fontName='Helvetica-Oblique',
        ))
        
        # Section divider style
        self.styles.add(ParagraphStyle(
            name='SectionDivider',
            parent=self.styles['Normal'],
            fontSize=14,
            spaceBefore=20,
            spaceAfter=12,
            fontName='Helvetica-Bold',
            textColor=colors.HexColor('#1a1a2e'),
            borderWidth=1,
            borderColor=colors.HexColor('#cccccc'),
            borderPadding=6,
        ))

    async def export(
        self,
        quiz_data: QuizExportData,
        options: ExportOptions
    ) -> ExportResult:
        """
        Export quiz to PDF format.
        
        Args:
            quiz_data: Quiz data with questions
            options: Export options (include_answer_key, include_explanations)
            
        Returns:
            ExportResult with PDF bytes
        """
        logger.info(f"Exporting quiz '{quiz_data.title}' to PDF with {len(quiz_data.questions)} questions")
        
        # Create PDF buffer
        buffer = io.BytesIO()
        
        # Create document
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            rightMargin=0.75 * inch,
            leftMargin=0.75 * inch,
            topMargin=0.75 * inch,
            bottomMargin=0.75 * inch,
        )
        
        # Build content
        story = []
        
        # Add cover section
        self._add_cover_section(story, quiz_data)
        
        # Add questions
        self._add_questions_section(story, quiz_data)
        
        # Add answer key if requested
        if options.include_answer_key:
            story.append(PageBreak())
            self._add_answer_key_section(story, quiz_data, options.include_explanations)
        
        # Build PDF
        doc.build(story)
        
        # Get bytes
        pdf_bytes = buffer.getvalue()
        buffer.close()
        
        # Generate filename
        filename = self._sanitize_filename(quiz_data.title) + ".pdf"
        
        logger.info(f"PDF generated: {len(pdf_bytes)} bytes, filename: {filename}")
        
        return ExportResult(
            content=pdf_bytes,
            content_type="application/pdf",
            filename=filename
        )

    def _add_cover_section(
        self,
        story: list,
        quiz_data: QuizExportData
    ) -> None:
        """Add quiz title and metadata cover section."""
        # Title
        story.append(Paragraph(
            self._escape_text(quiz_data.title),
            self.styles['QuizTitle']
        ))
        
        # Description if available
        if quiz_data.description:
            story.append(Paragraph(
                self._escape_text(quiz_data.description),
                self.styles['QuizDescription']
            ))
        
        # Metadata
        meta_parts = []
        meta_parts.append(f"Questions: {len(quiz_data.questions)}")
        
        # Content source info if available
        if quiz_data.content_source_type:
            meta_parts.append(f"Source: {quiz_data.content_source_type.title()}")
        
        story.append(Paragraph(
            " | ".join(meta_parts),
            self.styles['QuizMeta']
        ))
        
        # Generated date
        story.append(Paragraph(
            f"Generated: {datetime.now().strftime('%B %d, %Y')}",
            self.styles['QuizMeta']
        ))
        
        # Divider space
        story.append(Spacer(1, 30))

    def _add_questions_section(
        self,
        story: list,
        quiz_data: QuizExportData
    ) -> None:
        """Add all questions to the PDF."""
        for idx, question in enumerate(quiz_data.questions, start=1):
            self._add_question(story, question, idx)

    def _add_question(
        self,
        story: list,
        question,
        number: int
    ) -> None:
        """Add a single question based on its type."""
        if isinstance(question, ExportQuestionMCQ):
            self._add_mcq_question(story, question, number)
        elif isinstance(question, ExportQuestionTrueFalse):
            self._add_tf_question(story, question, number)
        elif isinstance(question, ExportQuestionFillBlank):
            self._add_fill_question(story, question, number)
        elif isinstance(question, ExportQuestionMatching):
            self._add_matching_question(story, question, number)
        else:
            logger.warning(f"Unknown question type: {type(question)}")

    def _add_mcq_question(
        self,
        story: list,
        question: ExportQuestionMCQ,
        number: int
    ) -> None:
        """Add multiple choice question."""
        # Question number and text
        story.append(Paragraph(
            f"<b>Question {number}</b> (Multiple Choice)",
            self.styles['QuestionNumber']
        ))
        story.append(Paragraph(
            self._escape_text(question.question),
            self.styles['QuestionText']
        ))
        
        # Options with letters
        option_letters = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H']
        for i, option in enumerate(question.options[:len(option_letters)]):
            letter = option_letters[i]
            story.append(Paragraph(
                f"○  {letter}. {self._escape_text(option)}",
                self.styles['OptionText']
            ))
        
        story.append(Spacer(1, 8))

    def _add_tf_question(
        self,
        story: list,
        question: ExportQuestionTrueFalse,
        number: int
    ) -> None:
        """Add true/false question."""
        story.append(Paragraph(
            f"<b>Question {number}</b> (True/False)",
            self.styles['QuestionNumber']
        ))
        story.append(Paragraph(
            self._escape_text(question.question),
            self.styles['QuestionText']
        ))
        story.append(Paragraph(
            "○  True     ○  False",
            self.styles['OptionText']
        ))
        story.append(Spacer(1, 8))

    def _add_fill_question(
        self,
        story: list,
        question: ExportQuestionFillBlank,
        number: int
    ) -> None:
        """Add fill-in-the-blank question."""
        story.append(Paragraph(
            f"<b>Question {number}</b> (Fill in the Blank)",
            self.styles['QuestionNumber']
        ))
        
        # Format question with blanks
        question_text = question.question
        # The question already contains blanks or we show the answer slot
        story.append(Paragraph(
            self._escape_text(question_text),
            self.styles['QuestionText']
        ))
        
        # Add answer line
        story.append(Paragraph(
            "Answer: _______________________________________________",
            self.styles['OptionText']
        ))
        story.append(Spacer(1, 8))

    def _add_matching_question(
        self,
        story: list,
        question: ExportQuestionMatching,
        number: int
    ) -> None:
        """Add matching question with two-column layout."""
        story.append(Paragraph(
            f"<b>Question {number}</b> (Matching)",
            self.styles['QuestionNumber']
        ))
        story.append(Paragraph(
            self._escape_text(question.question),
            self.styles['QuestionText']
        ))
        
        # Create two-column table
        # Left column: numbered items, Right column: lettered options
        left_items = question.left
        right_items = question.right
        
        # Prepare table data
        table_data = [["Column A", "Column B"]]  # Header
        
        max_len = max(len(left_items), len(right_items))
        letters = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h']
        
        for i in range(max_len):
            left_text = f"___ {i + 1}. {left_items[i]}" if i < len(left_items) else ""
            right_text = f"{letters[i]}. {right_items[i]}" if i < len(right_items) else ""
            table_data.append([left_text, right_text])
        
        # Create table
        table = Table(table_data, colWidths=[3.25 * inch, 3.25 * inch])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f0f0f0')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#1a1a2e')),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cccccc')),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))
        
        story.append(table)
        story.append(Spacer(1, 12))

    def _add_answer_key_section(
        self,
        story: list,
        quiz_data: QuizExportData,
        include_explanations: bool
    ) -> None:
        """Add answer key section on a new page."""
        story.append(Paragraph(
            "Answer Key",
            self.styles['AnswerKeyHeader']
        ))
        
        story.append(Spacer(1, 10))
        
        for idx, question in enumerate(quiz_data.questions, start=1):
            answer_text = self._get_answer_text(question, idx)
            story.append(Paragraph(
                answer_text,
                self.styles['AnswerText']
            ))
            
            # Add explanation if requested and available
            if include_explanations:
                explanation = getattr(question, 'explanation', None)
                if explanation:
                    story.append(Paragraph(
                        f"<i>Explanation: {self._escape_text(explanation)}</i>",
                        self.styles['ExplanationText']
                    ))

    def _get_answer_text(self, question, number: int) -> str:
        """Get formatted answer text for answer key."""
        if isinstance(question, ExportQuestionMCQ):
            # Find the correct answer letter
            correct = question.correct_answer
            option_letters = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H']
            try:
                idx = question.options.index(correct)
                letter = option_letters[idx]
                return f"<b>{number}.</b> {letter}. {self._escape_text(correct)}"
            except (ValueError, IndexError):
                return f"<b>{number}.</b> {self._escape_text(correct)}"
        
        elif isinstance(question, ExportQuestionTrueFalse):
            answer = "True" if question.correct_answer else "False"
            return f"<b>{number}.</b> {answer}"
        
        elif isinstance(question, ExportQuestionFillBlank):
            return f"<b>{number}.</b> {self._escape_text(question.correct_answer)}"
        
        elif isinstance(question, ExportQuestionMatching):
            # Format matching pairs
            pairs = []
            for i, left in enumerate(question.left):
                if i < len(question.correct_answer):
                    right_idx = question.correct_answer[i]
                    if right_idx < len(question.right):
                        pairs.append(f"{i + 1}-{chr(97 + right_idx)}")
            return f"<b>{number}.</b> {', '.join(pairs)}"
        
        return f"<b>{number}.</b> (Unknown format)"

    def _escape_text(self, text: str) -> str:
        """Escape special XML characters for ReportLab."""
        if not text:
            return ""
        text = str(text)
        # ReportLab uses XML-like markup, escape special chars
        text = text.replace('&', '&amp;')
        text = text.replace('<', '&lt;')
        text = text.replace('>', '&gt;')
        return text

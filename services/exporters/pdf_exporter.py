"""
PDF Exporter for Quiz Export Feature.

Uses ReportLab to generate professional PDF documents with:
- Quiz title and metadata cover section
- Numbered questions with proper formatting for all types
- Optional answer key on separate pages
- Optional explanations
- Quizify branding watermark and footer link

PERFORMANCE: PDF generation is CPU-bound; uses asyncio.to_thread to avoid
blocking the event loop during doc.build() calls.
"""

import asyncio
import io
import logging
import random
from datetime import datetime
from typing import Dict, List

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
)

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
from services.exporters.constants import (
    QUIZIFY_URL,
    QUIZIFY_WATERMARK_TEXT,
    QUIZIFY_FOOTER_TEXT,
)

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
        # Stores shuffle mappings for matching questions: {question_number: shuffled_indices}
        # Used to translate correct answers in the answer key section
        self._matching_shuffle_maps: Dict[int, List[int]] = {}

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
        
        # Run CPU-bound PDF generation in thread to avoid blocking event loop
        pdf_bytes, filename = await asyncio.to_thread(
            self._build_pdf_sync,
            quiz_data,
            options
        )
        
        logger.info(f"PDF generated: {len(pdf_bytes)} bytes, filename: {filename}")
        
        return ExportResult(
            content=pdf_bytes,
            content_type="application/pdf",
            filename=filename
        )

    def _build_pdf_sync(
        self,
        quiz_data: QuizExportData,
        options: ExportOptions
    ) -> tuple[bytes, str]:
        """
        Synchronous PDF building logic.
        
        This method is CPU-bound and should be called via asyncio.to_thread()
        to avoid blocking the event loop.
        
        Args:
            quiz_data: Quiz data with questions
            options: Export options
            
        Returns:
            Tuple of (pdf_bytes, filename)
        """
        # Clear shuffle mappings from any previous builds
        self._matching_shuffle_maps.clear()
        
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
        
        # Build PDF with branding callbacks (CPU-bound operation)
        doc.build(
            story,
            onFirstPage=self._add_page_branding,
            onLaterPages=self._add_page_branding
        )
        
        # Get bytes
        pdf_bytes = buffer.getvalue()
        buffer.close()
        
        # Generate filename
        filename = self._sanitize_filename(quiz_data.title) + ".pdf"
        
        return pdf_bytes, filename

    def _add_page_branding(self, canvas, doc) -> None:
        """
        Add branding elements to each page.
        
        Includes:
        - Subtle watermark in the center
        - Footer with "Generated by Quizify" link
        - Page number
        """
        canvas.saveState()
        
        page_width, page_height = letter
        
        # Add subtle watermark in center (very light gray, rotated)
        canvas.setFillColor(colors.Color(0.95, 0.95, 0.95))  # Very light gray
        canvas.setFont("Helvetica-Bold", 60)
        canvas.translate(page_width / 2, page_height / 2)
        canvas.rotate(45)
        canvas.drawCentredString(0, 0, QUIZIFY_WATERMARK_TEXT)
        
        canvas.restoreState()
        canvas.saveState()
        
        # Add footer with branding and page number
        footer_y = 0.4 * inch
        
        # Left side: "Generated by Quizify" with link
        canvas.setFont("Helvetica", 9)
        canvas.setFillColor(colors.HexColor('#666666'))
        
        # Create clickable link
        link_text = QUIZIFY_FOOTER_TEXT
        text_width = canvas.stringWidth(link_text, "Helvetica", 9)
        link_x = 0.75 * inch
        
        # Draw the text
        canvas.drawString(link_x, footer_y, link_text)
        
        # Add hyperlink rectangle (slightly padded)
        canvas.linkURL(
            QUIZIFY_URL,
            (link_x - 2, footer_y - 2, link_x + text_width + 2, footer_y + 12),
            relative=0
        )
        
        # Underline the link text for visual cue
        canvas.setStrokeColor(colors.HexColor('#666666'))
        canvas.setLineWidth(0.5)
        canvas.line(link_x, footer_y - 1, link_x + text_width, footer_y - 1)
        
        # Right side: Page number
        page_num = doc.page
        canvas.drawRightString(page_width - 0.75 * inch, footer_y, f"Page {page_num}")
        
        canvas.restoreState()

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
        """Add matching question with two-column layout.
        
        SECURITY: Right column is shuffled to prevent answer leakage.
        The correct pairing is only shown in the answer key section.
        The shuffle mapping is stored in self._matching_shuffle_maps for
        translating answer indices in the answer key.
        """
        story.append(Paragraph(
            f"<b>Question {number}</b> (Matching)",
            self.styles['QuestionNumber']
        ))
        story.append(Paragraph(
            self._escape_text(question.question),
            self.styles['QuestionText']
        ))
        
        # Create two-column table
        # Left column: numbered items, Right column: SHUFFLED lettered options
        left_items = question.left
        right_items = list(question.right)  # Make a copy
        
        # SECURITY: Shuffle right column to prevent answer leakage
        # Store shuffle order for answer key reference
        shuffled_indices = list(range(len(right_items)))
        random.shuffle(shuffled_indices)
        shuffled_right = [right_items[i] for i in shuffled_indices]
        
        # Store the shuffle mapping for answer key generation
        # shuffled_indices[new_position] = original_index
        # We need inverse: original_index -> new_position for answer key
        inverse_mapping = [0] * len(shuffled_indices)
        for new_pos, orig_idx in enumerate(shuffled_indices):
            inverse_mapping[orig_idx] = new_pos
        self._matching_shuffle_maps[number] = inverse_mapping
        
        # Prepare table data
        table_data = [["Column A", "Column B"]]  # Header
        
        max_len = max(len(left_items), len(shuffled_right))
        letters = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h']
        
        for i in range(max_len):
            left_text = f"___ {i + 1}. {self._escape_text(left_items[i])}" if i < len(left_items) else ""
            right_text = f"{letters[i]}. {self._escape_text(shuffled_right[i])}" if i < len(shuffled_right) else ""
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
        """Get formatted answer text for answer key.
        
        For matching questions, uses the shuffle mapping stored during
        question rendering to translate original indices to shuffled positions.
        """
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
            # Format matching pairs using the shuffle mapping
            # The mapping translates original right-column indices to shuffled positions
            shuffle_map = self._matching_shuffle_maps.get(number, [])
            pairs = []
            for i, left in enumerate(question.left):
                if i < len(question.correct_answer):
                    original_right_idx = question.correct_answer[i]
                    # Translate to shuffled position if mapping exists
                    if shuffle_map and original_right_idx < len(shuffle_map):
                        shuffled_pos = shuffle_map[original_right_idx]
                        pairs.append(f"{i + 1}-{chr(97 + shuffled_pos)}")
                    elif original_right_idx < len(question.right):
                        # Fallback if no mapping (shouldn't happen)
                        pairs.append(f"{i + 1}-{chr(97 + original_right_idx)}")
            return f"<b>{number}.</b> {', '.join(pairs)}"
        
        return f"<b>{number}.</b> (Unknown format)"

    def _escape_text(self, text: str) -> str:
        """
        Escape XML special characters for ReportLab's Paragraph markup.
        
        ReportLab's Paragraph class uses XML-like markup for formatting
        (e.g., <b>, <i>, <font>). This method escapes user content to prevent
        it from being interpreted as markup, avoiding rendering issues.
        
        Note: This escapes &, <, > which are sufficient for ReportLab's
        XML parser. Single quotes and other chars don't need escaping
        in this context as they're not special in ReportLab's markup.
        
        Args:
            text: Raw text that may contain special characters
            
        Returns:
            Text safe for use in ReportLab Paragraph elements
        """
        if not text:
            return ""
        text = str(text)
        # ReportLab uses XML-like markup, escape special chars
        text = text.replace('&', '&amp;')
        text = text.replace('<', '&lt;')
        text = text.replace('>', '&gt;')
        return text

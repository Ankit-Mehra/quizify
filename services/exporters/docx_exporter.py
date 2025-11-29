"""
DOCX Exporter for Quiz Export Feature.

Uses python-docx to generate editable Word documents with:
- Professional formatting compatible with Word and Google Docs
- Quiz title and metadata header
- Numbered questions with proper formatting for all types
- Optional answer key section
- Optional explanations
- Quizify branding footer with hyperlink
"""

import io
import logging
from datetime import datetime

from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

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
from services.exporters.constants import QUIZIFY_URL, QUIZIFY_FOOTER_TEXT, QUIZIFY_WATERMARK_TEXT

logger = logging.getLogger(__name__)


class DocxExporter(BaseExporter):
    """
    DOCX Exporter using python-docx.
    
    Generates editable Word documents with professional formatting for:
    - Multiple choice questions (A, B, C, D options)
    - True/False questions
    - Fill-in-the-blank questions
    - Matching questions (two-column table layout)
    """

    FORMAT_NAME = "docx"
    CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    FILE_EXTENSION = "docx"

    def __init__(self):
        """Initialize DOCX exporter."""
        pass

    async def export(
        self,
        quiz_data: QuizExportData,
        options: ExportOptions
    ) -> ExportResult:
        """
        Export quiz to DOCX format.
        
        Args:
            quiz_data: Quiz data with questions
            options: Export options (include_answer_key, include_explanations)
            
        Returns:
            ExportResult with DOCX bytes
        """
        logger.info(f"Exporting quiz '{quiz_data.title}' to DOCX with {len(quiz_data.questions)} questions")
        
        # Create document
        doc = Document()
        
        # Set up custom styles
        self._setup_styles(doc)
        
        # Add watermark to document header
        self._add_watermark(doc)
        
        # Add cover section
        self._add_cover_section(doc, quiz_data)
        
        # Add questions
        self._add_questions_section(doc, quiz_data)
        
        # Add answer key if requested
        if options.include_answer_key:
            self._add_answer_key_section(doc, quiz_data, options.include_explanations)
        
        # Add branding footer
        self._add_branding_footer(doc)
        
        # Save to bytes
        buffer = io.BytesIO()
        doc.save(buffer)
        docx_bytes = buffer.getvalue()
        buffer.close()
        
        # Generate filename
        filename = self._sanitize_filename(quiz_data.title) + ".docx"
        
        logger.info(f"DOCX generated: {len(docx_bytes)} bytes, filename: {filename}")
        
        return ExportResult(
            content=docx_bytes,
            content_type=self.CONTENT_TYPE,
            filename=filename
        )

    def _setup_styles(self, doc: Document) -> None:
        """Set up custom styles for the document."""
        styles = doc.styles
        
        # Quiz Title style
        try:
            title_style = styles.add_style('QuizTitle', WD_STYLE_TYPE.PARAGRAPH)
            title_style.font.size = Pt(24)
            title_style.font.bold = True
            title_style.font.color.rgb = RGBColor(0x1a, 0x1a, 0x2e)
            title_style.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
            title_style.paragraph_format.space_after = Pt(12)
        except ValueError:
            pass  # Style already exists
        
        # Quiz Description style
        try:
            desc_style = styles.add_style('QuizDescription', WD_STYLE_TYPE.PARAGRAPH)
            desc_style.font.size = Pt(12)
            desc_style.font.italic = True
            desc_style.font.color.rgb = RGBColor(0x4a, 0x4a, 0x4a)
            desc_style.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
            desc_style.paragraph_format.space_after = Pt(20)
        except ValueError:
            pass  # Style already exists
        
        # Question Number style
        try:
            qnum_style = styles.add_style('QuestionNumber', WD_STYLE_TYPE.PARAGRAPH)
            qnum_style.font.size = Pt(12)
            qnum_style.font.bold = True
            qnum_style.font.color.rgb = RGBColor(0x1a, 0x1a, 0x2e)
            qnum_style.paragraph_format.space_before = Pt(16)
            qnum_style.paragraph_format.space_after = Pt(4)
        except ValueError:
            pass  # Style already exists
        
        # Answer Key Header style
        try:
            answer_style = styles.add_style('AnswerKeyHeader', WD_STYLE_TYPE.PARAGRAPH)
            answer_style.font.size = Pt(18)
            answer_style.font.bold = True
            answer_style.font.color.rgb = RGBColor(0x1a, 0x1a, 0x2e)
            answer_style.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
            answer_style.paragraph_format.space_before = Pt(24)
            answer_style.paragraph_format.space_after = Pt(16)
        except ValueError:
            pass  # Style already exists

    def _add_cover_section(
        self,
        doc: Document,
        quiz_data: QuizExportData
    ) -> None:
        """Add quiz title and metadata cover section."""
        # Title
        title_para = doc.add_paragraph(quiz_data.title)
        try:
            title_para.style = 'QuizTitle'
        except KeyError:
            title_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = title_para.runs[0]
            run.font.size = Pt(24)
            run.font.bold = True
        
        # Description if available
        if quiz_data.description:
            desc_para = doc.add_paragraph(quiz_data.description)
            try:
                desc_para.style = 'QuizDescription'
            except KeyError:
                desc_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
                run = desc_para.runs[0]
                run.font.size = Pt(12)
                run.font.italic = True
        
        # Metadata line
        meta_parts = [f"Questions: {len(quiz_data.questions)}"]
        if quiz_data.content_source_type:
            meta_parts.append(f"Source: {quiz_data.content_source_type.title()}")
        meta_parts.append(f"Generated: {datetime.now().strftime('%B %d, %Y')}")
        
        meta_para = doc.add_paragraph(" | ".join(meta_parts))
        meta_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = meta_para.runs[0]
        run.font.size = Pt(10)
        run.font.color.rgb = RGBColor(0x66, 0x66, 0x66)
        
        # Add spacing
        doc.add_paragraph()

    def _add_questions_section(
        self,
        doc: Document,
        quiz_data: QuizExportData
    ) -> None:
        """Add all questions to the document."""
        for idx, question in enumerate(quiz_data.questions, start=1):
            self._add_question(doc, question, idx)

    def _add_question(
        self,
        doc: Document,
        question,
        number: int
    ) -> None:
        """Add a single question based on its type."""
        if isinstance(question, ExportQuestionMCQ):
            self._add_mcq_question(doc, question, number)
        elif isinstance(question, ExportQuestionTrueFalse):
            self._add_tf_question(doc, question, number)
        elif isinstance(question, ExportQuestionFillBlank):
            self._add_fill_question(doc, question, number)
        elif isinstance(question, ExportQuestionMatching):
            self._add_matching_question(doc, question, number)
        else:
            logger.warning(f"Unknown question type: {type(question)}")

    def _add_mcq_question(
        self,
        doc: Document,
        question: ExportQuestionMCQ,
        number: int
    ) -> None:
        """Add multiple choice question."""
        # Question header with number and type
        q_para = doc.add_paragraph()
        run = q_para.add_run(f"Question {number} ")
        run.font.bold = True
        run.font.size = Pt(12)
        
        type_run = q_para.add_run("(Multiple Choice)")
        type_run.font.size = Pt(10)
        type_run.font.color.rgb = RGBColor(0x66, 0x66, 0x66)
        
        # Question text
        q_text = doc.add_paragraph(question.question)
        q_text.paragraph_format.space_after = Pt(8)
        
        # Options with letters
        option_letters = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H']
        for i, option in enumerate(question.options[:len(option_letters)]):
            letter = option_letters[i]
            opt_para = doc.add_paragraph()
            opt_para.paragraph_format.left_indent = Inches(0.5)
            
            run = opt_para.add_run(f"○  {letter}. ")
            run.font.size = Pt(11)
            
            opt_run = opt_para.add_run(option)
            opt_run.font.size = Pt(11)
        
        # Add spacing after question
        doc.add_paragraph()

    def _add_tf_question(
        self,
        doc: Document,
        question: ExportQuestionTrueFalse,
        number: int
    ) -> None:
        """Add true/false question."""
        # Question header
        q_para = doc.add_paragraph()
        run = q_para.add_run(f"Question {number} ")
        run.font.bold = True
        run.font.size = Pt(12)
        
        type_run = q_para.add_run("(True/False)")
        type_run.font.size = Pt(10)
        type_run.font.color.rgb = RGBColor(0x66, 0x66, 0x66)
        
        # Question text
        q_text = doc.add_paragraph(question.question)
        q_text.paragraph_format.space_after = Pt(8)
        
        # True/False options
        opt_para = doc.add_paragraph()
        opt_para.paragraph_format.left_indent = Inches(0.5)
        opt_para.add_run("○  True          ○  False")
        
        # Add spacing
        doc.add_paragraph()

    def _add_fill_question(
        self,
        doc: Document,
        question: ExportQuestionFillBlank,
        number: int
    ) -> None:
        """Add fill-in-the-blank question."""
        # Question header
        q_para = doc.add_paragraph()
        run = q_para.add_run(f"Question {number} ")
        run.font.bold = True
        run.font.size = Pt(12)
        
        type_run = q_para.add_run("(Fill in the Blank)")
        type_run.font.size = Pt(10)
        type_run.font.color.rgb = RGBColor(0x66, 0x66, 0x66)
        
        # Question text
        q_text = doc.add_paragraph(question.question)
        q_text.paragraph_format.space_after = Pt(8)
        
        # Answer line
        ans_para = doc.add_paragraph()
        ans_para.paragraph_format.left_indent = Inches(0.5)
        ans_para.add_run("Answer: _______________________________________________")
        
        # Word bank if available
        if question.options:
            wb_para = doc.add_paragraph()
            wb_para.paragraph_format.left_indent = Inches(0.5)
            wb_run = wb_para.add_run("Word Bank: ")
            wb_run.font.italic = True
            wb_run.font.size = Pt(10)
            
            words_run = wb_para.add_run(", ".join(question.options))
            words_run.font.size = Pt(10)
            words_run.font.color.rgb = RGBColor(0x66, 0x66, 0x66)
        
        # Add spacing
        doc.add_paragraph()

    def _add_matching_question(
        self,
        doc: Document,
        question: ExportQuestionMatching,
        number: int
    ) -> None:
        """Add matching question with two-column table."""
        # Question header
        q_para = doc.add_paragraph()
        run = q_para.add_run(f"Question {number} ")
        run.font.bold = True
        run.font.size = Pt(12)
        
        type_run = q_para.add_run("(Matching)")
        type_run.font.size = Pt(10)
        type_run.font.color.rgb = RGBColor(0x66, 0x66, 0x66)
        
        # Question text
        q_text = doc.add_paragraph(question.question)
        q_text.paragraph_format.space_after = Pt(8)
        
        # Create two-column table
        left_items = question.left
        right_items = question.right
        max_rows = max(len(left_items), len(right_items))
        
        # Add table with header row + data rows
        table = doc.add_table(rows=max_rows + 1, cols=2)
        table.style = 'Table Grid'
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        
        # Header row
        header_cells = table.rows[0].cells
        header_cells[0].text = "Column A"
        header_cells[1].text = "Column B"
        
        # Style header
        for cell in header_cells:
            cell.paragraphs[0].runs[0].font.bold = True
            cell.paragraphs[0].runs[0].font.size = Pt(11)
        
        # Data rows
        letters = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h']
        for i in range(max_rows):
            row_cells = table.rows[i + 1].cells
            
            # Left column (numbered with blank for answer)
            if i < len(left_items):
                row_cells[0].text = f"___ {i + 1}. {left_items[i]}"
            
            # Right column (lettered)
            if i < len(right_items):
                row_cells[1].text = f"{letters[i]}. {right_items[i]}"
        
        # Add spacing after table
        doc.add_paragraph()
        doc.add_paragraph()

    def _add_answer_key_section(
        self,
        doc: Document,
        quiz_data: QuizExportData,
        include_explanations: bool
    ) -> None:
        """Add answer key section."""
        # Page break before answer key
        doc.add_page_break()
        
        # Answer Key Header
        header_para = doc.add_paragraph("Answer Key")
        try:
            header_para.style = 'AnswerKeyHeader'
        except KeyError:
            header_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = header_para.runs[0]
            run.font.size = Pt(18)
            run.font.bold = True
        
        # Add answers
        for idx, question in enumerate(quiz_data.questions, start=1):
            answer_text = self._get_answer_text(question, idx)
            
            ans_para = doc.add_paragraph()
            run = ans_para.add_run(f"{idx}. ")
            run.font.bold = True
            
            ans_run = ans_para.add_run(answer_text)
            ans_run.font.color.rgb = RGBColor(0x2d, 0x6a, 0x4f)  # Green
            
            # Add explanation if requested and available
            if include_explanations:
                explanation = getattr(question, 'explanation', None)
                if explanation:
                    exp_para = doc.add_paragraph()
                    exp_para.paragraph_format.left_indent = Inches(0.5)
                    
                    exp_run = exp_para.add_run(f"Explanation: {explanation}")
                    exp_run.font.size = Pt(10)
                    exp_run.font.italic = True
                    exp_run.font.color.rgb = RGBColor(0x4a, 0x4a, 0x4a)

    def _get_answer_text(self, question, number: int) -> str:
        """Get formatted answer text for answer key."""
        if isinstance(question, ExportQuestionMCQ):
            # Find the correct answer letter
            correct = question.correct_answer
            option_letters = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H']
            try:
                idx = question.options.index(correct)
                letter = option_letters[idx]
                return f"{letter}. {correct}"
            except (ValueError, IndexError):
                return correct
        
        elif isinstance(question, ExportQuestionTrueFalse):
            return "True" if question.correct_answer else "False"
        
        elif isinstance(question, ExportQuestionFillBlank):
            return question.correct_answer
        
        elif isinstance(question, ExportQuestionMatching):
            # Format matching pairs
            pairs = []
            for i, left in enumerate(question.left):
                if i < len(question.correct_answer):
                    right_idx = question.correct_answer[i]
                    if right_idx < len(question.right):
                        pairs.append(f"{i + 1}-{chr(97 + right_idx)}")
            return ", ".join(pairs)
        
        return "(Unknown format)"

    def _add_watermark(self, doc: Document) -> None:
        """
        Add a diagonal watermark to the document.
        
        Creates a semi-transparent text watermark in the document header
        that appears on every page. Uses raw lxml elements for VML shapes.
        """
        from lxml import etree
        
        section = doc.sections[0]
        header = section.header
        header.is_linked_to_previous = False
        
        # Get or create header paragraph
        if header.paragraphs:
            para = header.paragraphs[0]
        else:
            para = header.add_paragraph()
        
        # Define VML namespace
        nsmap = {
            'v': 'urn:schemas-microsoft-com:vml',
            'o': 'urn:schemas-microsoft-com:office:office',
            'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
        }
        
        # Create the pict element using Word namespace
        pict = etree.Element('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}pict', nsmap=nsmap)
        
        # Create VML shape for the watermark
        shape = etree.SubElement(pict, '{urn:schemas-microsoft-com:vml}shape')
        shape.set('id', 'PowerPlusWaterMarkObject')
        shape.set('type', '#_x0000_t136')  # Text shape type
        shape.set('style', 
            'position:absolute;'
            'margin-left:0;margin-top:0;'
            'width:500pt;height:100pt;'
            'rotation:315;'  # Diagonal rotation (-45 degrees)
            'z-index:-251658752;'
            'mso-position-horizontal:center;'
            'mso-position-horizontal-relative:margin;'
            'mso-position-vertical:center;'
            'mso-position-vertical-relative:margin'
        )
        shape.set('fillcolor', '#E0E0E0')  # Light gray color
        shape.set('stroked', 'f')  # No stroke/border
        
        # Add fill element for transparency
        fill = etree.SubElement(shape, '{urn:schemas-microsoft-com:vml}fill')
        fill.set('opacity', '.15')  # 15% opacity for subtle watermark
        
        # Add textpath for the watermark text
        textpath = etree.SubElement(shape, '{urn:schemas-microsoft-com:vml}textpath')
        textpath.set('style', 'font-family:"Arial";font-size:60pt')
        textpath.set('string', QUIZIFY_WATERMARK_TEXT)
        
        # Add to paragraph via run using python-docx's mechanism
        run = para.add_run()
        run._r.append(pict)

    def _add_branding_footer(self, doc: Document) -> None:
        """
        Add Quizify branding footer with hyperlink to each section.
        
        Uses document footer to add "Generated by Quizify" with a clickable link.
        """
        # Get the default section (or first section)
        section = doc.sections[0]
        
        # Access or create footer
        footer = section.footer
        footer.is_linked_to_previous = False
        
        # Clear any existing footer content
        for para in footer.paragraphs:
            para.clear()
        
        # Use the first paragraph in footer (or add one if empty)
        if footer.paragraphs:
            footer_para = footer.paragraphs[0]
        else:
            footer_para = footer.add_paragraph()
        
        footer_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        
        # Add "Generated by " text
        run1 = footer_para.add_run("Generated by ")
        run1.font.size = Pt(9)
        run1.font.color.rgb = RGBColor(0x66, 0x66, 0x66)
        
        # Add hyperlink for "Quizify"
        self._add_hyperlink(footer_para, QUIZIFY_URL, "Quizify")

    def _add_hyperlink(self, paragraph, url: str, text: str) -> None:
        """
        Add a hyperlink to a paragraph.
        
        python-docx doesn't have built-in hyperlink support, so we use raw XML.
        """
        # Get the document part for the relationship
        part = paragraph.part
        r_id = part.relate_to(
            url,
            "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink",
            is_external=True
        )
        
        # Create the hyperlink element
        hyperlink = OxmlElement('w:hyperlink')
        hyperlink.set(qn('r:id'), r_id)
        
        # Create the run element
        new_run = OxmlElement('w:r')
        
        # Add run properties for styling
        rPr = OxmlElement('w:rPr')
        
        # Font size
        sz = OxmlElement('w:sz')
        sz.set(qn('w:val'), '18')  # Half-points, so 18 = 9pt
        rPr.append(sz)
        
        # Color (blue for link)
        color = OxmlElement('w:color')
        color.set(qn('w:val'), '0066CC')
        rPr.append(color)
        
        # Underline
        u = OxmlElement('w:u')
        u.set(qn('w:val'), 'single')
        rPr.append(u)
        
        new_run.append(rPr)
        
        # Add text
        text_elem = OxmlElement('w:t')
        text_elem.text = text
        new_run.append(text_elem)
        
        hyperlink.append(new_run)
        paragraph._p.append(hyperlink)

"""
Moodle XML Exporter - Export quizzes in Moodle XML format.

Moodle XML is Moodle's native format for importing/exporting questions.
It's simpler than QTI and widely used in educational institutions that
run Moodle as their LMS.

Reference: https://docs.moodle.org/en/Moodle_XML_format
"""

import logging
from typing import TYPE_CHECKING, List
from xml.etree import ElementTree as ET
from xml.dom import minidom

from services.exporters.base import BaseExporter, ExportError
from schemas.export import ExportResult

# Module logger for Moodle XML export operations
logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from schemas.export import (
        QuizExportData,
        ExportOptions,
        ExportQuestionMCQ,
        ExportQuestionTrueFalse,
        ExportQuestionFillBlank,
        ExportQuestionMatching,
    )


class MoodleXmlExporter(BaseExporter):
    """
    Export quizzes in Moodle XML format.
    
    Creates a single XML file that can be imported directly into Moodle's
    question bank. Supports all standard Moodle question types.
    
    Supported question types:
    - Multiple Choice (multichoice)
    - True/False (truefalse)
    - Short Answer (shortanswer) - for fill in blank
    - Matching (matching)
    """
    
    FORMAT_NAME = "moodle_xml"
    CONTENT_TYPE = "application/xml"
    FILE_EXTENSION = "xml"
    
    async def export(
        self,
        quiz_data: "QuizExportData",
        options: "ExportOptions"
    ) -> ExportResult:
        """
        Export quiz to Moodle XML format.
        
        Args:
            quiz_data: Quiz data with questions
            options: Export options
            
        Returns:
            ExportResult with XML file bytes
        """
        logger.info(f"Exporting quiz '{quiz_data.title}' to Moodle XML format ({len(quiz_data.questions)} questions)")
        
        try:
            # Create root quiz element
            root = ET.Element("quiz")
            
            # Add category question (defines where questions go in Moodle)
            self._add_category(root, quiz_data.title)
            
            # Add each question
            for idx, question in enumerate(quiz_data.questions, 1):
                self._add_question(root, question, idx, options)
            
            # Convert to pretty XML
            xml_content = self._prettify_xml(root)
            
            logger.info(f"Moodle XML export successful for quiz '{quiz_data.title}'")
            
            return ExportResult(
                content=xml_content.encode("utf-8"),
                content_type=self.CONTENT_TYPE,
                filename=self.generate_filename(quiz_data.title),
            )
            
        except Exception as e:
            logger.error(f"Moodle XML export failed for quiz '{quiz_data.title}': {str(e)}", exc_info=True)
            raise ExportError(f"Moodle XML export failed: {str(e)}", self.FORMAT_NAME)
    
    def _add_category(self, root: ET.Element, quiz_title: str):
        """Add category pseudo-question to define question bank category."""
        question = ET.SubElement(root, "question", {"type": "category"})
        category = ET.SubElement(question, "category")
        text = ET.SubElement(category, "text")
        text.text = f"$course$/Imported/{quiz_title}"
    
    def _add_question(
        self,
        root: ET.Element,
        question,
        question_num: int,
        options: "ExportOptions"
    ):
        """Add a question to the quiz XML."""
        
        if question.type == "multiple_choice":
            self._add_mcq_question(root, question, question_num, options)
        elif question.type == "true_false":
            self._add_true_false_question(root, question, question_num, options)
        elif question.type == "fill_blank":
            self._add_fill_blank_question(root, question, question_num, options)
        elif question.type == "matching":
            self._add_matching_question(root, question, question_num, options)
        else:
            # Fallback to MCQ
            self._add_mcq_question(root, question, question_num, options)
    
    def _add_mcq_question(
        self,
        root: ET.Element,
        question: "ExportQuestionMCQ",
        question_num: int,
        options: "ExportOptions"
    ):
        """Add multiple choice question in Moodle XML format."""
        
        q_elem = ET.SubElement(root, "question", {"type": "multichoice"})
        
        # Question name
        name = ET.SubElement(q_elem, "name")
        text = ET.SubElement(name, "text")
        text.text = f"Question {question_num}"
        
        # Question text
        q_text = ET.SubElement(q_elem, "questiontext", {"format": "html"})
        text = ET.SubElement(q_text, "text")
        text.text = f"<![CDATA[<p>{self._escape_html(question.question)}</p>]]>"
        
        # Default grade
        default_grade = ET.SubElement(q_elem, "defaultgrade")
        default_grade.text = "1"
        
        # Single answer
        single = ET.SubElement(q_elem, "single")
        single.text = "true"
        
        # Shuffle answers
        shuffle = ET.SubElement(q_elem, "shuffleanswers")
        shuffle.text = "true"
        
        # Answer numbering
        answer_numbering = ET.SubElement(q_elem, "answernumbering")
        answer_numbering.text = "abc"
        
        # Find correct answer index
        correct_idx = self._find_correct_option_index(
            question.options, question.correct_answer
        )
        
        # Add answers
        for idx, opt in enumerate(question.options):
            is_correct = (idx == correct_idx)
            fraction = "100" if is_correct and options.include_answer_key else "0"
            
            answer = ET.SubElement(q_elem, "answer", {
                "fraction": fraction,
                "format": "html"
            })
            text = ET.SubElement(answer, "text")
            text.text = f"<![CDATA[{self._escape_html(opt)}]]>"
            
            # Add feedback
            feedback = ET.SubElement(answer, "feedback", {"format": "html"})
            fb_text = ET.SubElement(feedback, "text")
            if is_correct and options.include_answer_key:
                fb_text.text = "<![CDATA[Correct!]]>"
            else:
                fb_text.text = "<![CDATA[]]>"
        
        # General feedback (explanation)
        if options.include_explanations:
            explanation = getattr(question, 'explanation', None)
            distractors = getattr(question, 'distractor_explanations', None)
            
            if explanation or distractors:
                general_fb = ET.SubElement(q_elem, "generalfeedback", {"format": "html"})
                text = ET.SubElement(general_fb, "text")
                
                fb_html = ""
                if explanation:
                    fb_html += f"<p><b>Explanation:</b> {self._escape_html(explanation)}</p>"
                
                if distractors and isinstance(distractors, dict):
                    # Filter out the correct answer from distractor explanations to avoid confusion
                    correct_answer = getattr(question, "correct_answer", None)
                    filtered_items = [
                        (opt, reason)
                        for opt, reason in distractors.items()
                        if opt != correct_answer
                    ]
                    if filtered_items:
                        fb_html += "<p><b>Why other options are incorrect:</b></p><ul>"
                        for opt, reason in filtered_items:
                            fb_html += f"<li><b>{self._escape_html(opt)}:</b> {self._escape_html(reason)}</li>"
                        fb_html += "</ul>"
                
                text.text = f"<![CDATA[{fb_html}]]>"
    
    def _add_true_false_question(
        self,
        root: ET.Element,
        question: "ExportQuestionTrueFalse",
        question_num: int,
        options: "ExportOptions"
    ):
        """Add true/false question in Moodle XML format."""
        
        q_elem = ET.SubElement(root, "question", {"type": "truefalse"})
        
        # Question name
        name = ET.SubElement(q_elem, "name")
        text = ET.SubElement(name, "text")
        text.text = f"Question {question_num}"
        
        # Question text
        q_text = ET.SubElement(q_elem, "questiontext", {"format": "html"})
        text = ET.SubElement(q_text, "text")
        text.text = f"<![CDATA[<p>{self._escape_html(question.question)}</p>]]>"
        
        # Default grade
        default_grade = ET.SubElement(q_elem, "defaultgrade")
        default_grade.text = "1"
        
        # True answer
        true_fraction = "100" if question.correct_answer and options.include_answer_key else "0"
        true_answer = ET.SubElement(q_elem, "answer", {
            "fraction": true_fraction,
            "format": "moodle_auto_format"
        })
        true_text = ET.SubElement(true_answer, "text")
        true_text.text = "true"
        
        # False answer
        false_fraction = "100" if not question.correct_answer and options.include_answer_key else "0"
        false_answer = ET.SubElement(q_elem, "answer", {
            "fraction": false_fraction,
            "format": "moodle_auto_format"
        })
        false_text = ET.SubElement(false_answer, "text")
        false_text.text = "false"
        
        # General feedback
        if options.include_explanations and question.explanation:
            general_fb = ET.SubElement(q_elem, "generalfeedback", {"format": "html"})
            text = ET.SubElement(general_fb, "text")
            text.text = f"<![CDATA[<p>{self._escape_html(question.explanation)}</p>]]>"
    
    def _add_fill_blank_question(
        self,
        root: ET.Element,
        question: "ExportQuestionFillBlank",
        question_num: int,
        options: "ExportOptions"
    ):
        """Add fill-in-the-blank as short answer question."""
        
        q_elem = ET.SubElement(root, "question", {"type": "shortanswer"})
        
        # Question name
        name = ET.SubElement(q_elem, "name")
        text = ET.SubElement(name, "text")
        text.text = f"Question {question_num}"
        
        # Question text (include word bank if available)
        question_html = f"<p>{self._escape_html(question.question)}</p>"
        if question.options:
            word_bank = ", ".join(question.options)
            question_html += f"<p><em>Word bank: {self._escape_html(word_bank)}</em></p>"
        
        q_text = ET.SubElement(q_elem, "questiontext", {"format": "html"})
        text = ET.SubElement(q_text, "text")
        text.text = f"<![CDATA[{question_html}]]>"
        
        # Default grade
        default_grade = ET.SubElement(q_elem, "defaultgrade")
        default_grade.text = "1"
        
        # Case sensitivity
        usecase = ET.SubElement(q_elem, "usecase")
        usecase.text = "0"  # Case insensitive
        
        # Correct answer
        if options.include_answer_key:
            answer = ET.SubElement(q_elem, "answer", {
                "fraction": "100",
                "format": "moodle_auto_format"
            })
            text = ET.SubElement(answer, "text")
            text.text = question.correct_answer
            
            feedback = ET.SubElement(answer, "feedback", {"format": "html"})
            fb_text = ET.SubElement(feedback, "text")
            fb_text.text = "<![CDATA[Correct!]]>"
        
        # General feedback
        if options.include_explanations:
            explanation = getattr(question, 'explanation', None)
            distractors = getattr(question, 'distractor_explanations', None)
            
            if explanation or distractors:
                general_fb = ET.SubElement(q_elem, "generalfeedback", {"format": "html"})
                text = ET.SubElement(general_fb, "text")
                
                fb_html = ""
                if explanation:
                    fb_html += f"<p><b>Explanation:</b> {self._escape_html(explanation)}</p>"
                
                if distractors and isinstance(distractors, dict):
                    # Filter out the correct answer from distractor explanations to avoid confusion
                    correct_answer = getattr(question, "correct_answer", None)
                    filtered_items = [
                        (opt, reason)
                        for opt, reason in distractors.items()
                        if opt != correct_answer
                    ]
                    if filtered_items:
                        fb_html += "<p><b>Why other options are incorrect:</b></p><ul>"
                        for opt, reason in filtered_items:
                            fb_html += f"<li><b>{self._escape_html(opt)}:</b> {self._escape_html(reason)}</li>"
                        fb_html += "</ul>"
                
                text.text = f"<![CDATA[{fb_html}]]>"
    
    def _add_matching_question(
        self,
        root: ET.Element,
        question: "ExportQuestionMatching",
        question_num: int,
        options: "ExportOptions"
    ):
        """Add matching question in Moodle XML format."""
        
        q_elem = ET.SubElement(root, "question", {"type": "matching"})
        
        # Question name
        name = ET.SubElement(q_elem, "name")
        text = ET.SubElement(name, "text")
        text.text = f"Question {question_num}"
        
        # Question text
        q_text = ET.SubElement(q_elem, "questiontext", {"format": "html"})
        text = ET.SubElement(q_text, "text")
        text.text = f"<![CDATA[<p>{self._escape_html(question.question)}</p>]]>"
        
        # Default grade
        default_grade = ET.SubElement(q_elem, "defaultgrade")
        default_grade.text = "1"
        
        # Shuffle
        shuffle = ET.SubElement(q_elem, "shuffleanswers")
        shuffle.text = "true"
        
        # Add subquestions (matching pairs)
        for idx, left_item in enumerate(question.left):
            subquestion = ET.SubElement(q_elem, "subquestion", {"format": "html"})
            
            # Left side (question)
            text = ET.SubElement(subquestion, "text")
            text.text = f"<![CDATA[{self._escape_html(left_item)}]]>"
            
            # Right side (answer) - use correct_answer mapping
            if options.include_answer_key and idx < len(question.correct_answer):
                right_idx = question.correct_answer[idx]
                if right_idx < len(question.right):
                    answer = ET.SubElement(subquestion, "answer")
                    answer_text = ET.SubElement(answer, "text")
                    answer_text.text = question.right[right_idx]
                else:
                    answer = ET.SubElement(subquestion, "answer")
                    answer_text = ET.SubElement(answer, "text")
                    answer_text.text = ""
            else:
                answer = ET.SubElement(subquestion, "answer")
                answer_text = ET.SubElement(answer, "text")
                answer_text.text = ""
        
        # General feedback
        if options.include_explanations and question.explanation:
            general_fb = ET.SubElement(q_elem, "generalfeedback", {"format": "html"})
            text = ET.SubElement(general_fb, "text")
            text.text = f"<![CDATA[<p>{self._escape_html(question.explanation)}</p>]]>"
    
    def _find_correct_option_index(self, options: List[str], correct_answer: str) -> int:
        """Find index of correct answer in options list."""
        # Try exact match first
        for idx, opt in enumerate(options):
            if opt == correct_answer:
                return idx
        
        # Try case-insensitive match
        correct_lower = correct_answer.lower().strip()
        for idx, opt in enumerate(options):
            if opt.lower().strip() == correct_lower:
                return idx
        
        # Try letter matching (A, B, C, D)
        if correct_answer.upper() in "ABCD":
            letter_idx = ord(correct_answer.upper()) - ord("A")
            if 0 <= letter_idx < len(options):
                return letter_idx
        
        # Default to first option
        return 0
    
    def _escape_html(self, text: str) -> str:
        """Escape HTML special characters."""
        if not text:
            return ""
        return (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )
    
    def _prettify_xml(self, elem: ET.Element) -> str:
        """Convert ElementTree element to pretty-printed XML string."""
        rough_string = ET.tostring(elem, encoding="unicode")
        # Handle CDATA sections - minidom doesn't preserve them well
        # So we do a simple prettify instead
        reparsed = minidom.parseString(rough_string)
        pretty = reparsed.toprettyxml(indent="  ", encoding="UTF-8").decode("utf-8")
        # Remove extra blank lines
        lines = [line for line in pretty.split("\n") if line.strip()]
        return "\n".join(lines)

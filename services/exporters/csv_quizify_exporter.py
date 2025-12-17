"""
Quizify Native CSV Exporter.

Exports quizzes to CSV format with full question data, suitable for:
- Spreadsheet editing
- Data backup
- Future re-import functionality

CSV Structure:
- One row per question option (MCQ has multiple rows)
- All metadata preserved
"""

import logging
from typing import List

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
from services.exporters.csv_utils import generate_csv_bytes

logger = logging.getLogger(__name__)


class CsvQuizifyExporter(BaseExporter):
    """
    Quizify Native CSV Exporter.
    
    Exports quiz data in a detailed CSV format with all question metadata,
    suitable for spreadsheet editing and data portability.
    
    CSV Columns:
    - quiz_title, quiz_description
    - question_number, question_id, question_type
    - question_text, option_label, option_text
    - is_correct, correct_answer, explanation
    """

    FORMAT_NAME = "csv_quizify"
    CONTENT_TYPE = "text/csv; charset=utf-8"
    FILE_EXTENSION = "csv"

    # CSV Header row
    HEADERS = [
        "quiz_title",
        "quiz_description",
        "question_number",
        "question_id",
        "question_type",
        "question_text",
        "option_label",
        "option_text",
        "is_correct",
        "correct_answer",
        "explanation",
        "distractor_explanation",
    ]

    async def export(
        self,
        quiz_data: QuizExportData,
        options: ExportOptions
    ) -> ExportResult:
        """
        Export quiz to Quizify CSV format.
        
        Args:
            quiz_data: Quiz data with questions
            options: Export options (answer key affects what data is included)
            
        Returns:
            ExportResult with CSV bytes
        """
        logger.info(f"Exporting quiz '{quiz_data.title}' to Quizify CSV with {len(quiz_data.questions)} questions")
        
        # Build CSV rows
        rows = [self.HEADERS]  # Start with headers
        
        for idx, question in enumerate(quiz_data.questions, start=1):
            question_rows = self._question_to_rows(
                quiz_data, 
                question, 
                idx, 
                include_answers=options.include_answer_key
            )
            rows.extend(question_rows)
        
        # Generate CSV bytes with UTF-8 BOM for Excel compatibility
        csv_bytes = generate_csv_bytes(rows, include_bom=True)
        
        # Generate filename
        filename = self._sanitize_filename(quiz_data.title) + ".csv"
        
        logger.info(f"CSV generated: {len(csv_bytes)} bytes, filename: {filename}")
        
        return ExportResult(
            content=csv_bytes,
            content_type=self.CONTENT_TYPE,
            filename=filename
        )

    def _question_to_rows(
        self,
        quiz_data: QuizExportData,
        question,
        question_number: int,
        include_answers: bool
    ) -> List[List[str]]:
        """Convert a question to CSV rows."""
        if isinstance(question, ExportQuestionMCQ):
            return self._mcq_to_rows(quiz_data, question, question_number, include_answers)
        elif isinstance(question, ExportQuestionTrueFalse):
            return self._tf_to_rows(quiz_data, question, question_number, include_answers)
        elif isinstance(question, ExportQuestionFillBlank):
            return self._fill_to_rows(quiz_data, question, question_number, include_answers)
        elif isinstance(question, ExportQuestionMatching):
            return self._matching_to_rows(quiz_data, question, question_number, include_answers)
        else:
            logger.warning(f"Unknown question type: {type(question)}")
            return []

    def _mcq_to_rows(
        self,
        quiz_data: "QuizExportData",
        question: "ExportQuestionMCQ",
        question_number: int,
        include_answers: bool
    ) -> List[List[str]]:
        """Convert MCQ question to CSV rows (one row per option)."""
        rows = []
        option_letters = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H']
        
        for i, option in enumerate(question.options):
            letter = option_letters[i] if i < len(option_letters) else str(i + 1)
            is_correct = option == question.correct_answer if include_answers else ""
            
            distractor_expl = ""
            if include_answers and question.distractor_explanations:
                distractor_expl = question.distractor_explanations.get(option, "")
            
            row = [
                quiz_data.title,
                quiz_data.description or "",
                str(question_number),
                str(question.id),
                "multiple_choice",
                question.question,
                letter,
                option,
                str(is_correct) if include_answers else "",
                question.correct_answer if include_answers else "",
                question.explanation or "" if include_answers else "",
                distractor_expl,
            ]
            rows.append(row)
        
        return rows

    def _tf_to_rows(
        self,
        quiz_data: "QuizExportData",
        question: "ExportQuestionTrueFalse",
        question_number: int,
        include_answers: bool
    ) -> List[List[str]]:
        """Convert True/False question to single CSV row."""
        answer = "True" if question.correct_answer else "False"
        
        row = [
            quiz_data.title,
            quiz_data.description or "",
            str(question_number),
            str(question.id),
            "true_false",
            question.question,
            "",  # No option label
            "",  # No option text
            "",  # No is_correct flag for T/F
            answer if include_answers else "",
            question.explanation or "" if include_answers else "",
            "",  # No distractor explanation
        ]
        
        return [row]

    def _fill_to_rows(
        self,
        quiz_data: "QuizExportData",
        question: "ExportQuestionFillBlank",
        question_number: int,
        include_answers: bool
    ) -> List[List[str]]:
        """Convert Fill-in-the-blank question to CSV rows."""
        # Main row with the answer
        main_row = [
            quiz_data.title,
            quiz_data.description or "",
            str(question_number),
            str(question.id),
            "fill_blank",
            question.question,
            "",  # No option label
            "",  # No option text
            "",  # No is_correct flag
            question.correct_answer if include_answers else "",
            question.explanation or "" if include_answers else "",
            "",  # No distractor explanation for main row
        ]
        
        rows = [main_row]
        
        # Add word bank options as additional rows
        for i, word in enumerate(question.options):
            distractor_expl = ""
            if include_answers and question.distractor_explanations:
                distractor_expl = question.distractor_explanations.get(word, "")

            word_row = [
                quiz_data.title,
                quiz_data.description or "",
                str(question_number),
                str(question.id),
                "fill_blank_wordbank",
                question.question,
                str(i + 1),  # Word number
                word,  # Word from bank
                str(word == question.correct_answer) if include_answers else "",
                question.correct_answer if include_answers else "",
                "",  # No explanation on word bank rows
                distractor_expl,
            ]
            rows.append(word_row)
        
        return rows

    def _matching_to_rows(
        self,
        quiz_data: "QuizExportData",
        question: "ExportQuestionMatching",
        question_number: int,
        include_answers: bool
    ) -> List[List[str]]:
        """Convert Matching question to CSV rows (one row per pair)."""
        rows = []
        letters = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h']
        
        for i, left_item in enumerate(question.left):
            # Get the matching right item
            correct_idx = question.correct_answer[i] if i < len(question.correct_answer) else -1
            right_item = question.right[correct_idx] if 0 <= correct_idx < len(question.right) else ""
            right_letter = letters[correct_idx] if 0 <= correct_idx < len(letters) else ""
            
            row = [
                quiz_data.title,
                quiz_data.description or "",
                str(question_number),
                str(question.id),
                "matching",
                question.question,
                f"{i + 1}",  # Left item number
                left_item,  # Left item text
                right_letter if include_answers else "",  # Matching letter
                right_item if include_answers else "",  # Matching right text
                question.explanation or "" if (include_answers and i == 0) else "",  # Explanation only on first row
                "",  # No distractor explanation
            ]
            rows.append(row)
        
        return rows

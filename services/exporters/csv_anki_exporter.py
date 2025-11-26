"""
Anki CSV Exporter.

Exports quizzes to Anki-compatible format for spaced repetition learning.
Creates flashcard-style exports with Front/Back columns.

Format: Tab-separated values (TSV) or comma-separated
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
from services.exporters.csv_utils import generate_tsv_bytes

logger = logging.getLogger(__name__)


class CsvAnkiExporter(BaseExporter):
    """
    Anki CSV Exporter.
    
    Exports quiz as flashcards in Anki-compatible TSV format.
    Each question becomes one or more flashcards.
    
    Card Format:
    - Front: Question (with options for MCQ)
    - Back: Answer with optional explanation
    """

    FORMAT_NAME = "csv_anki"
    CONTENT_TYPE = "text/tab-separated-values; charset=utf-8"
    FILE_EXTENSION = "txt"  # Anki prefers .txt extension

    async def export(
        self,
        quiz_data: QuizExportData,
        options: ExportOptions
    ) -> ExportResult:
        """
        Export quiz to Anki TSV format.
        
        Args:
            quiz_data: Quiz data with questions
            options: Export options (explanations can be included)
            
        Returns:
            ExportResult with TSV bytes
        """
        logger.info(f"Exporting quiz '{quiz_data.title}' to Anki format with {len(quiz_data.questions)} questions")
        
        # Build rows (no header - Anki doesn't need it)
        rows = []
        
        for question in quiz_data.questions:
            question_cards = self._question_to_cards(
                question, 
                include_explanations=options.include_explanations
            )
            rows.extend(question_cards)
        
        # Generate TSV bytes (Anki prefers TSV)
        tsv_bytes = generate_tsv_bytes(rows, include_bom=False)
        
        # Generate filename with .txt extension for Anki
        filename = self._sanitize_filename(quiz_data.title) + "-anki.txt"
        
        logger.info(f"Anki export generated: {len(tsv_bytes)} bytes, {len(rows)} cards, filename: {filename}")
        
        return ExportResult(
            content=tsv_bytes,
            content_type=self.CONTENT_TYPE,
            filename=filename
        )

    def _question_to_cards(
        self,
        question,
        include_explanations: bool
    ) -> List[List[str]]:
        """Convert a question to Anki flashcard rows (Front, Back)."""
        if isinstance(question, ExportQuestionMCQ):
            return self._mcq_to_cards(question, include_explanations)
        elif isinstance(question, ExportQuestionTrueFalse):
            return self._tf_to_cards(question, include_explanations)
        elif isinstance(question, ExportQuestionFillBlank):
            return self._fill_to_cards(question, include_explanations)
        elif isinstance(question, ExportQuestionMatching):
            return self._matching_to_cards(question, include_explanations)
        else:
            logger.warning(f"Unknown question type: {type(question)}")
            return []

    def _mcq_to_cards(
        self,
        question: ExportQuestionMCQ,
        include_explanations: bool
    ) -> List[List[str]]:
        """
        Convert MCQ to single flashcard.
        
        Front: Question with all options
        Back: Correct answer with explanation
        """
        option_letters = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H']
        
        # Build front with question and options
        front_parts = [question.question, ""]
        for i, option in enumerate(question.options):
            letter = option_letters[i] if i < len(option_letters) else str(i + 1)
            front_parts.append(f"{letter}. {option}")
        
        front = "<br>".join(front_parts)
        
        # Build back with correct answer
        try:
            correct_idx = question.options.index(question.correct_answer)
            correct_letter = option_letters[correct_idx]
            back_parts = [f"<b>Correct: {correct_letter}. {question.correct_answer}</b>"]
        except (ValueError, IndexError):
            back_parts = [f"<b>Correct: {question.correct_answer}</b>"]
        
        # Add explanation if requested
        if include_explanations and question.explanation:
            back_parts.append("")
            back_parts.append(f"<i>Explanation: {question.explanation}</i>")
        
        back = "<br>".join(back_parts)
        
        return [[front, back]]

    def _tf_to_cards(
        self,
        question: ExportQuestionTrueFalse,
        include_explanations: bool
    ) -> List[List[str]]:
        """
        Convert True/False to single flashcard.
        
        Front: Question with "True or False?"
        Back: Answer with explanation
        """
        front = f"{question.question}<br><br><i>True or False?</i>"
        
        answer = "True" if question.correct_answer else "False"
        back_parts = [f"<b>{answer}</b>"]
        
        if include_explanations and question.explanation:
            back_parts.append("")
            back_parts.append(f"<i>Explanation: {question.explanation}</i>")
        
        back = "<br>".join(back_parts)
        
        return [[front, back]]

    def _fill_to_cards(
        self,
        question: ExportQuestionFillBlank,
        include_explanations: bool
    ) -> List[List[str]]:
        """
        Convert Fill-in-the-blank to single flashcard.
        
        Front: Question with blank
        Back: Answer with explanation
        """
        # Add word bank if available
        if question.options:
            word_bank = f"<br><br><i>Word Bank: {', '.join(question.options)}</i>"
            front = f"{question.question}{word_bank}"
        else:
            front = question.question
        
        back_parts = [f"<b>{question.correct_answer}</b>"]
        
        if include_explanations and question.explanation:
            back_parts.append("")
            back_parts.append(f"<i>Explanation: {question.explanation}</i>")
        
        back = "<br>".join(back_parts)
        
        return [[front, back]]

    def _matching_to_cards(
        self,
        question: ExportQuestionMatching,
        include_explanations: bool
    ) -> List[List[str]]:
        """
        Convert Matching question to multiple flashcards.
        
        Creates one card per pair for spaced repetition of each match.
        """
        cards = []
        
        for i, left_item in enumerate(question.left):
            # Get the matching right item
            correct_idx = question.correct_answer[i] if i < len(question.correct_answer) else -1
            right_item = question.right[correct_idx] if 0 <= correct_idx < len(question.right) else "?"
            
            # Front: Left term with context
            front = f"<b>Match:</b> {left_item}<br><br><i>{question.question}</i>"
            
            # Back: Matching right term
            back_parts = [f"<b>{right_item}</b>"]
            
            # Add explanation only on first card to avoid repetition
            if include_explanations and question.explanation and i == 0:
                back_parts.append("")
                back_parts.append(f"<i>Explanation: {question.explanation}</i>")
            
            back = "<br>".join(back_parts)
            
            cards.append([front, back])
        
        return cards

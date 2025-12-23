"""
Anki CSV Exporter.

Exports quizzes and flashcards to Anki-compatible format for spaced repetition learning.
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
    FlashcardDeckExportData,
    ExportFlashcard,
)
from services.exporters.base import BaseExporter
from services.exporters.csv_utils import generate_tsv_bytes

logger = logging.getLogger(__name__)


class CsvAnkiExporter(BaseExporter):
    """
    Anki CSV Exporter.
    
    Exports quizzes and flashcard decks in Anki-compatible TSV format.
    
    For quizzes: Each question becomes one or more flashcards.
    For flashcard decks: Direct export of Front/Back cards.
    
    Card Format:
    - Front: Question or prompt
    - Back: Answer with optional explanation/hint
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

    async def export_flashcards(
        self,
        deck_data: FlashcardDeckExportData,
        include_hints: bool = True
    ) -> ExportResult:
        """
        Export flashcard deck to Anki TSV format.
        
        This method handles native flashcard exports directly.
        Cards are exported as Front/Back pairs, with optional hints
        appended to the back.
        
        Args:
            deck_data: Flashcard deck data with cards
            include_hints: Whether to include hints in the back
            
        Returns:
            ExportResult with TSV bytes
        """
        logger.info(f"Exporting flashcard deck '{deck_data.title}' to Anki format with {deck_data.card_count} cards")
        
        # Build rows (no header - Anki doesn't need it)
        rows = []
        
        for card in deck_data.cards:
            card_row = self._flashcard_to_card(card, include_hints)
            rows.append(card_row)
        
        # Generate TSV bytes (Anki prefers TSV)
        tsv_bytes = generate_tsv_bytes(rows, include_bom=False)
        
        # Generate filename with .txt extension for Anki
        filename = self._sanitize_filename(deck_data.title) + "-flashcards-anki.txt"
        
        logger.info(f"Anki flashcard export generated: {len(tsv_bytes)} bytes, {len(rows)} cards, filename: {filename}")
        
        return ExportResult(
            content=tsv_bytes,
            content_type=self.CONTENT_TYPE,
            filename=filename
        )

    def _flashcard_to_card(
        self,
        card: ExportFlashcard,
        include_hints: bool
    ) -> List[str]:
        """
        Convert a native flashcard to Anki row (Front, Back).
        
        Args:
            card: The flashcard to convert
            include_hints: Whether to include the hint in the back
            
        Returns:
            List of [front, back] strings
        """
        front = card.front
        
        # Build back with answer and optional hint
        back_parts = [f"<b>{card.back}</b>"]
        
        if include_hints and card.hint:
            back_parts.append("")
            back_parts.append(f"<i>Hint: {card.hint}</i>")
        
        back = "<br>".join(back_parts)
        
        return [front, back]

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
        if include_explanations:
            if question.explanation:
                back_parts.append("")
                back_parts.append(f"<i>Explanation: {question.explanation}</i>")
            
            if question.distractor_explanations:
                # Filter out the correct answer from distractor explanations (case-insensitive)
                correct_answer_lower = (
                    question.correct_answer.lower()
                    if isinstance(question.correct_answer, str)
                    else None
                )
                distractor_items = [
                    (opt, reason)
                    for opt, reason in question.distractor_explanations.items()
                    if not (
                        isinstance(opt, str)
                        and correct_answer_lower is not None
                        and opt.lower() == correct_answer_lower
                    )
                ]
                
                if distractor_items:
                    back_parts.append("")
                    back_parts.append("<i>Why other options are incorrect:</i>")
                    back_parts.append("<ul>")
                    for opt, reason in distractor_items:
                        back_parts.append(f"<li><b>{opt}:</b> {reason}</li>")
                    back_parts.append("</ul>")
        
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
        
        if include_explanations:
            if question.explanation:
                back_parts.append("")
                back_parts.append(f"<i>Explanation: {question.explanation}</i>")
            
            if question.distractor_explanations:
                # Filter out the correct answer (case-insensitive)
                correct = question.correct_answer.strip().lower()
                distractor_items = [
                    (opt, reason)
                    for opt, reason in question.distractor_explanations.items()
                    if opt.strip().lower() != correct
                ]
                
                if distractor_items:
                    back_parts.append("")
                    back_parts.append("<i>Why other options are incorrect:</i>")
                    back_parts.append("<ul>")
                    for opt, reason in distractor_items:
                        back_parts.append(f"<li><b>{opt}:</b> {reason}</li>")
                    back_parts.append("</ul>")
        
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

from uuid import UUID
from schemas.quiz import Question, MCQQuestion, TrueFalseQuestion, FillBlankQuestion, MatchingQuestion, Quizzes
from schemas.quizzes_parsed import QuizzesParsed
from typing import List

def convert_parsed_to_quizzes(parsed: QuizzesParsed, quiz_id: UUID) -> Quizzes:
    questions: List[Question] = []

    for q in parsed.quizzes:
        common = {
            "quiz_id": quiz_id,
            "explanation": q.explanation,
            "source": q.source
        }

        if q.type == "multiple_choice":
            questions.append(MCQQuestion(**common, question=q.question, options=q.options, correct_answer=q.correct_answer,type="multiple_choice"))
        elif q.type == "true_false":
            questions.append(TrueFalseQuestion(**common, question=q.question, correct_answer=q.correct_answer,type="true_false"))
        elif q.type == "fill_blank":
            questions.append(FillBlankQuestion(**common, question=q.question, options=q.options, correct_answer=q.correct_answer,type="fill_blank"))
        elif q.type == "matching":
            questions.append(MatchingQuestion(**common, question=q.question, left=q.left, right=q.right, correct_answer=q.correct_answer,type="matching"))

    return Quizzes(quizzes=questions)

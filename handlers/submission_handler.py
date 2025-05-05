## Submission Handler
from typing import List, Dict, Any
from schemas.quiz import MCQQuestion, TrueFalseQuestion, FillBlankQuestion, MatchingQuestion, Question
from schemas.submission import QuizSubmission, QuizAnswer, QuizSubmissionRequest
from pydantic import ValidationError
from fastapi import HTTPException, Depends
from uuid import UUID, uuid4
from datetime import datetime
from services.db_services.supabase_submission import get_question, save_submission, save_answer, get_submission_by_id
from dependencies.auth_dependencies import get_current_user_id
from services.logger import app_logger as logger


TYPE_TO_MODEL = {
    "multiple_choice": MCQQuestion,
    "true_false": TrueFalseQuestion,
    "fill_blank": FillBlankQuestion,
    "matching": MatchingQuestion,
}

def parse_question_models(raw_questions: List[Dict[str, Any]]) -> List[Question]:
    """
    Converts list of raw dicts (from Supabase) into strongly-typed Pydantic question models.
    """
    parsed_questions = []

    for q in raw_questions:
        model_cls = TYPE_TO_MODEL.get(q.get("type"))
        if not model_cls:
            logger.warning(f"Unknown question type: {q.get('type')}")
            continue
        try:
            parsed_questions.append(model_cls(**q))
        except ValidationError as e:
            logger.warning(f"Failed to parse question {q.get('id')}: {e}")
            continue

    return parsed_questions


async def submit_quiz(
    submission: QuizSubmissionRequest,
    user_id: UUID = Depends(get_current_user_id)
):
    correct = 0
    wrong = 0
    detailed_results = []

    # Fetch raw questions
    question_ids = [a.question_id for a in submission.answers]
    try:
        raw_questions = get_question(question_ids)
        questions = parse_question_models(raw_questions)
        question_map = {q.id: q for q in questions}
    except Exception as e:
        logger.error(f"Error fetching or parsing questions: {e}")
        raise HTTPException(status_code=500, detail="Error processing questions")

    # Evaluate answers
    for ans in submission.answers:
        q = question_map.get(ans.question_id)
        if not q:
            continue

        is_correct = str(ans.user_answer).strip().lower() == str(q.correct_answer).strip().lower()
        if is_correct:
            correct += 1
        else:
            wrong += 1

        detailed_results.append({
            "question_id": str(q.id),
            "question": q.question,
            "your_answer": ans.user_answer,
            "correct_answer": q.correct_answer,
            "is_correct": is_correct,
        })

    score = round((correct / submission.total_questions) * 100, 2)

    new_submission = QuizSubmission(
        id=uuid4(),
        user_id=user_id,
        quiz_id=submission.quiz_id,
        correct_count=correct,
        wrong_count=wrong,
        score=score,
        total_questions=submission.total_questions,
        submitted_at=datetime.now()
    )

    save_submission(new_submission)

    for result in detailed_results:
        save_answer(QuizAnswer(
            id=uuid4(),
            submission_id=new_submission.id,
            question_id=result["question_id"],
            user_answer=result["your_answer"],
            correct_answer=result["correct_answer"],
            is_correct=result["is_correct"]
        ))

    return {
        "id": new_submission.id,
        "total_questions": submission.total_questions,
        "correct_count": correct,
        "wrong_count": wrong,
        "score": score,
        "detailed_results": detailed_results
    }


async def get_submission(submission_id: UUID, user_id: UUID = Depends(get_current_user_id)):
    submission = get_submission_by_id(submission_id)
    if submission["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="You are not authorized to access this submission")
    return submission

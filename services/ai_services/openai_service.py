from openai import AsyncOpenAI
from schemas.quiz import Quizzes, Question
from schemas.quizzes_parsed import QuizzesParsed
from services.ai_services.prompt_smart import (
    build_quiz_prompt_mcq,
    build_quiz_prompt_true_false,
    build_quiz_prompt_fill_blank,
    build_quiz_prompt_matching,
)
from services.ai_services.prompts import build_quiz_prompt_mixed
from dotenv import load_dotenv
from typing import List
import os
import re
from services.logger import ai_logger as logger
from uuid import uuid4
from schemas.conversion import convert_parsed_to_quizzes

logger.info("OpenAI service initialized")
load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = AsyncOpenAI(api_key=OPENAI_API_KEY)

# Mapping from type -> prompt builder
QUESTION_TYPE_PROMPTS = {
    "mcq": build_quiz_prompt_mcq,
    "true_false": build_quiz_prompt_true_false,
    "fill_blank": build_quiz_prompt_fill_blank,
    "matching": build_quiz_prompt_matching,
}

async def generate_quiz_for_type(qtype: str, text: str, num_questions: int) -> List[Question]:
    logger.info(f"Generating {num_questions} questions of type: {qtype}")
    prompt_builder = QUESTION_TYPE_PROMPTS[qtype]
    prompt = prompt_builder(text, num_questions)

    response = await client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        response_format= { "type": "json_object" }
    )

    raw_json = response.choices[0].message.content.strip()

    # 🔥 Strip triple backticks and "json" if present
    if raw_json.startswith("```json") and raw_json.endswith("```"):
        raw_json = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw_json.strip())

    logger.debug(f"Raw JSON response for {qtype}: {raw_json}")

    parsed = Quizzes.model_validate_json(raw_json)
    return parsed.quizzes

async def generate_quiz_async(text: str, num_questions: int, question_types: List[str]) -> Quizzes:
    prompt = build_quiz_prompt_mixed(text, num_questions, question_types)
    
    logger.info(f"Generating quiz with prompt: {prompt}")
    response = await client.beta.chat.completions.parse(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        response_format= QuizzesParsed
    )
    parsed_response = response.choices[0].message.parsed

    if not parsed_response or not parsed_response.quizzes:
        return []
    quiz_id = uuid4()
    parsed_quizzes = convert_parsed_to_quizzes(parsed_response, quiz_id)
    return parsed_quizzes.quizzes


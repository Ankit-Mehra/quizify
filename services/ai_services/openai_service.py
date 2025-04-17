from openai import AsyncOpenAI
from schemas.quiz import Quizzes
from services.ai_services.prompts import build_quiz_prompt_mcq, build_quiz_prompt_mixed
from dotenv import load_dotenv
import os
from typing import List
load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = AsyncOpenAI(api_key=OPENAI_API_KEY)

def generate_quiz(text: str, num_questions: int) -> Quizzes:
    prompt = build_quiz_prompt_mcq(text, num_questions)

    response = client.beta.chat.completions.parse(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        response_format= Quizzes
    )
    parsed_response = response.choices[0].message.parsed

    if not parsed_response or not parsed_response.quizzes:
        return []
    
    return parsed_response.quizzes

async def generate_quiz_async(text: str, num_questions: int, question_types: List[str]) -> Quizzes:
    prompt = build_quiz_prompt_mixed(text, num_questions, question_types)

    response = await client.beta.chat.completions.parse(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        response_format= Quizzes
    )
    parsed_response = response.choices[0].message.parsed

    if not parsed_response or not parsed_response.quizzes:
        return []

    return parsed_response.quizzes
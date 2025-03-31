import os
from google import genai
from dotenv import load_dotenv
from schemas.quiz import QuizQuestion

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

client = genai.Client(api_key=GEMINI_API_KEY)


def generate_quiz(text: str) -> QuizQuestion:

    prompt = f"""
    You are an AI assistant helping generate quiz questions from study content.

    From the following text, generate one multiple-choice question in JSON format using the following schema:

    - question: a concise, clear question that tests understanding of the content.
    - options: a list of 4 distinct, plausible answer choices.
    - correct_answer: exactly one correct option from the list.
    - source: the specific sentence or phrase from the input text that justifies the correct answer.
    - explanation: a short explanation of why the correct answer is correct in the context of the question.

    Text:
    \"\"\"
    {text}
    \"\"\"

    Return a quiz that is challenging but fair, based directly on the text above.
    """


    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=prompt,
        config= {
            "response_mime_type": "application/json",
            "response_schema": QuizQuestion
        }
    )
    return response.parsed



import logging
import os
from google import genai
from dotenv import load_dotenv
from schemas.quiz import Quizzes

load_dotenv()

# Module logger for Gemini AI operations
logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

client = genai.Client(api_key=GEMINI_API_KEY)


def generate_quiz(text: str, num_questions: int) -> Quizzes:
    """
    Generate a quiz from text using Google Gemini AI.
    
    Args:
        text: The source text to generate questions from
        num_questions: Number of questions to generate
        
    Returns:
        Quizzes object with generated questions
        
    Raises:
        Exception: If Gemini API call fails
    """
    logger.info(f"Generating {num_questions} quiz questions using Gemini (text length: {len(text)} chars)")

    prompt = f"""
    You are an AI assistant helping generate quiz questions from study content.

    From the following text, generate {num_questions} multiple-choice questions in JSON format using the following schema:

    {{
        "quizzes": [
            {{
                "question": "A clear, concise question that tests understanding of the provided content.",
                "options": ["A list of four distinct and plausible answer choices."],
                "correct_answer": "Exactly one of the options listed above, which is the correct answer.",
                "source": "The sentence or phrase from the text that directly supports the correct answer.",
                "explanation": "A short explanation of why the correct answer is correct, based on the source."
            }}
        ]
    }}

    Text:
    \"\"\"
    {text}
    \"\"\"

    Return a quiz that is challenging but fair, based directly on the text above.
    """

    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
            config= {
                "response_mime_type": "application/json",
                "response_schema": Quizzes
            }
        )
        logger.info(f"Gemini quiz generation successful: {num_questions} questions")
        return response.parsed
    except Exception as e:
        logger.error(f"Gemini quiz generation failed: {str(e)}", exc_info=True)
        raise



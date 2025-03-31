import os
from google import genai
from dotenv import load_dotenv
from schemas.quiz import QuizQuestions

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

client = genai.Client(api_key=GEMINI_API_KEY)


def generate_quiz(text: str, num_questions: int) -> QuizQuestions:

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


    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=prompt,
        config= {
            "response_mime_type": "application/json",
            "response_schema": QuizQuestions
        }
    )
    print(response)
    return response.parsed



from openai import OpenAI
from schemas.quiz import QuizQuestion
from dotenv import load_dotenv
import os

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY)

def generate_quiz(text: str) -> QuizQuestion:
    prompt = f"""
    You are an AI tutor that creates quiz questions based on educational content.

    From the text below, generate **one multiple-choice question**. Format the response according to the following schema:

    - question: A clear, concise question that tests understanding of the provided content.
    - options: A list of four distinct and plausible answer choices.
    - correct_answer: Exactly one of the options listed above, which is the correct answer.
    - source: The sentence or phrase from the text that directly supports the correct answer.
    - explanation: A short explanation of why the correct answer is correct, based on the source.

    Text:
    \"\"\"
    {text}
    \"\"\"

    Make the question moderately challenging and relevant. Do not include any text outside of the JSON schema.
    """

    response = client.beta.chat.completions.parse(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        response_format=QuizQuestion
    )
    return response.choices[0].message.parsed

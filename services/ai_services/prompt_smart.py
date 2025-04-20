from textwrap import dedent
import json


def build_prompt(
    text: str,
    num_questions: int,
    question_type: str,
    sample_question: dict,
    extra_instructions: str = "",
) -> str:
    return dedent(f"""
    You are an AI tutor generating {question_type.replace("_", " ")} questions.

    Generate exactly {num_questions} {question_type.replace("_", " ")} question(s) in the JSON format:

    {{
      "quizzes": [
        {json.dumps(sample_question, indent=2)}
      ]
    }}

    Text:
    \"\"\"{text}\"\"\"

    Rules:
    - Output only valid JSON, no comments, no markdown.
    {extra_instructions.strip()}
    """).strip()


def build_quiz_prompt_mcq(text: str, num_questions: int) -> str:
    sample = {
        "type": "multiple_choice",
        "question": "What is the capital of Japan?",
        "options": ["Beijing", "Seoul", "Tokyo", "Bangkok"],
        "correct_answer": "Tokyo",
        "explanation": "Tokyo is the capital city of Japan.",
        "source": "Geography section"
    }
    return build_prompt(
        text,
        num_questions,
        "multiple_choice",
        sample,
        extra_instructions="""
        - Include exactly 4 plausible options.
        - Avoid labels like A., B), or 1:
        - "correct_answer" must match one of the options exactly.
        """
    )


def build_quiz_prompt_true_false(text: str, num_questions: int) -> str:
    sample = {
        "type": "true_false",
        "question": "The Earth is flat.",
        "correct_answer": False,
        "explanation": "The Earth is an oblate spheroid.",
        "source": "Astronomy section"
    }
    return build_prompt(
        text,
        num_questions,
        "true_false",
        sample,
        extra_instructions="""
        - "correct_answer" must be either true or false (Boolean).
        """
    )


def build_quiz_prompt_fill_blank(text: str, num_questions: int) -> str:
    sample = {
        "type": "fill_blank",
        "question": "______ discovered gravity.",
        "options": ["Einstein", "Newton", "Galileo", "Bohr"],
        "correct_answer": "Newton",
        "explanation": "Newton is credited with gravity theory.",
        "source": "Physics section"
    }
    return build_prompt(
        text,
        num_questions,
        "fill_blank",
        sample,
        extra_instructions="""
        These fields are REQUIRED:
        - "question" must include "_____" (blank)
        - "options": A list of exactly 4 string options, no `null`
        - "correct_answer": must be one of the options
        """
    )


def build_quiz_prompt_matching(text: str, num_questions: int) -> str:
    sample = {
        "type": "matching",
        "question": "Match the scientist with their discovery.",
        "left": ["Einstein", "Newton", "Curie", "Darwin"],
        "right": ["Relativity", "Gravity", "Radioactivity", "Evolution"],
        "correct_answer": [0, 1, 2, 3],
        "explanation": "Each scientist is correctly matched.",
        "source": "Science chart"
    }
    return build_prompt(
        text,
        num_questions,
        "matching",
        sample,
        extra_instructions="""
        - Include 4 items in both "left" and "right" lists.
        - "correct_answer" must be a list of integers (0–3) representing the correct index matches.
        """
    )

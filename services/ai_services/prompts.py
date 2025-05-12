from typing import List
from services.logger import ai_logger as logger

def build_quiz_prompt_mixed(text: str, num_questions: int, types: List[str]) -> str:
    logger.info(f"Building mixed quiz prompt with {num_questions} questions, types: {types}")
    
    all_types = ["multiple_choice", "true_false", "fill_blank", "matching"]
    final_types = all_types if "mixed" in types else types
    type_str = ", ".join(final_types)

    prompt = f"""
    You are an AI assistant that generates quiz questions in strict JSON format only.

    Generate exactly {num_questions} questions of the following types: {type_str}.
    Use only the information from the input text.

    Respond in this JSON structure:
    {{
      "quizzes": [{{ ... }}]
    }}

    Each object in "quizzes" must:
    - Include all required fields for its type.
    - Follow strict formatting rules per type (shown below).
    - Be factual, clear, and based on the provided text.

    Formatting rules:
    - "multiple_choice":
        - 4 plausible answers in `options`
        - No prefixes like A. or 1)
    - "true_false":
        - `correct_answer` must be a boolean: true or false
    - "fill_blank":
        - `question` must contain a blank: "______"
        - `options` must be a list of 4 strings
        - `correct_answer` must match one of the options
    - "matching":
        - Provide `left` and `right` lists (4 items each)
        - `correct_answer` should be a list of matching indices like [0, 1, 2, 3]

    Rules:
    - Do not include explanations or content outside the JSON.
    - Do not copy any examples.
    - Do not return sample or placeholder questions.

    Text to use:
    \"\"\"
    {text}
    \"\"\"
    """.strip()

    return prompt

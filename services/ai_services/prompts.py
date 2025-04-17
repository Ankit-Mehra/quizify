from typing import List
from services.logger import ai_logger as logger

def build_quiz_prompt_mixed(text: str, num_questions: int, types: List[str]) -> str:
    logger.info(f"Building mixed quiz prompt with {num_questions} questions, types: {types}")
    all_types = ["multiple_choice", "true_false", "fill_blank", "matching"]
    final_types = all_types if "mixed" in types else types
    type_str = ", ".join(final_types)

    schema_sample = """
    {
      "quizzes": [
        {  
          "type": "multiple_choice",
          "question": "...",
          "options": ["A", "B", "C", "D"],
          "correct_answer": "B",
          "explanation": "...",
          "source": "..."
        },
        {
          "type": "true_false",
          "question": "...",
          "correct_answer": true,
          "explanation": "...",
          "source": "..."
        },
        {
          "type": "fill_blank",
          "question": "______ discovered gravity.",
          "correct_answer": "Newton",
          "explanation": "...",
          "source": "..."
        },
        {
          "type": "matching",
          "question": "Match scientists to discoveries.",
          "left": ["Einstein", "Newton", "Darwin", "Curie"],
          "right": ["Relativity", "Gravity", "Evolution", "Radioactivity"],
          "correct_answer": [0, 1, 2, 3],
          "explanation": "...",
          "source": "..."
        }
      ]
    }
    """

    prompt = f"""
    You are an AI assistant that generates quiz questions in strict JSON format only, without any extra text.Focus on structure and accuracy.

    Generate exactly {num_questions} questions of the following types: {type_str}.

    Your response MUST match the following JSON structure exactly:
    {schema_sample}

    Text:
    \"\"\"
    {text}
    \"\"\"

    Formatting rules:
    - If type is "multiple_choice", return exactly 4 options with NO lettered prefixes (no A/B/C/D prefixes)", "1.", etc.).
      Avoid labels like "A.", "B)", or "1:" – just provide the option text.
    - If type is "true_false", the answer must be true or false (lowercase).
    - If type is "fill_blank", provide only the correct word/phrase as the answer.
    - If type is "matching", generate exactly 4 items in each list and match them with correct index order.

    Return ONLY the JSON – no explanation, markdown, or commentary outside the JSON.
    Make the questions moderately challenging and accurate.
    """
    return prompt.strip()
 

def build_quiz_prompt_mcq(text: str, num_questions: int) -> str:
    logger.info(f"Building MCQ quiz prompt with {num_questions} questions")
    prompt = f"""
    You are an AI tutor that creates quiz questions.

    From the text below, generate ** {num_questions} multiple-choice questions**. Return them as a list under a single JSON object using this format:
    {{
        "quizzes": [
            {{
                "question": "A clear, concise question that tests understanding of the provided content.",
                "options": ["A list of four distinct and plausible answer choices."],
                "correct_answer": "Exactly one of the options listed above, which is the correct answer.",
                "explanation": "A short explanation of why the correct answer is correct, based on the source.",
                "source": "The sentence or phrase from the text that directly supports the correct answer."
            }},
            ...
        ]
    }}
    Text:
    \"\"\"
    {text}
    \"\"\"

    Make the question challenging and relevant. Do not include any text outside of the JSON schema.
    """ 
    return prompt.strip()
    
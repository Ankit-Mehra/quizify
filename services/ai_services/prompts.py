from typing import List
from services.logger import ai_logger as logger

def build_quiz_prompt_mixed(text: str, num_questions: int, types: List[str]) -> str:
    from services.logger import ai_logger as logger

    logger.info(f"Building mixed quiz prompt with {num_questions} questions, types: {types}")
    all_types = ["multiple_choice", "true_false", "fill_blank", "matching"]
    final_types = all_types if "mixed" in types else types
    type_str = ", ".join(final_types)

    schema_sample = """
    {
      "quizzes": [
        {
          "type": "multiple_choice",
          "question": "What is the capital of Japan?",
          "options": ["Beijing", "Seoul", "Tokyo", "Bangkok"],
          "correct_answer": "Tokyo",
          "explanation": "Tokyo is the capital city of Japan.",
          "source": "The paragraph discussing Asian capitals."
        },
        {
          "type": "true_false",
          "question": "The Earth is flat.",
          "correct_answer": false,
          "explanation": "The Earth is an oblate spheroid.",
          "source": "Section on planetary shape."
        },
        {
          "type": "fill_blank",
          "question": "______ discovered gravity.",
          "options": ["Einstein", "Newton", "Galileo", "Bohr"],
          "correct_answer": "Newton",
          "explanation": "Newton is credited with the theory of gravity.",
          "source": "Textbook on classical physics"
        },
        {
          "type": "fill_blank",
          "question": "The chemical symbol for water is ______.",
          "options": ["CO2", "O2", "H2O", "NaCl"],
          "correct_answer": "H2O",
          "explanation": "H2O represents water.",
          "source": "Chemistry fundamentals"
        },
        {
          // ❌ Don't do this: missing required options field
          "type": "fill_blank",
          "question": "______ is the powerhouse of the cell.",
          "correct_answer": "Mitochondria",
          "explanation": "Mitochondria generate energy for the cell.",
          "source": "Biology basics"
        },
        {
          "type": "matching",
          "question": "Match the scientist with their discovery.",
          "options": [],  // Not used for matching
          "left": ["Einstein", "Newton", "Curie", "Darwin"],
          "right": ["Relativity", "Gravity", "Radioactivity", "Evolution"],
          "correct_answer": [0, 1, 2, 3],
          "explanation": "These are standard associations.",
          "source": "Science summary chart"
        }
      ]
    }   
    """

    prompt = f"""
    You are an AI assistant that generates quiz questions in strict JSON format only.

    Generate exactly {num_questions} questions of the following types: {type_str}.

    Your response MUST match the following JSON structure exactly:
    {schema_sample}

    Text:
    \"\"\"
    {text}
    \"\"\"

    Rules:
    - Output only a single JSON object with a "quizzes" list.
    - Do not include ANY extra text, markdown, or comments.
    - Every object in the list must include all required keys and follow the order shown.
    - Do NOT omit required fields like "options", even if they are empty lists.
    - Questions with missing fields (like options for fill_blank) are invalid and will be discarded.

    Formatting guidelines:
    - "multiple_choice":
        - 4 plausible answer strings in "options"
        - No prefixes like A. / 1) / etc.
    - "true_false":
        - "correct_answer" must be either `true` or `false` (Boolean)
    - "fill_blank":
        - "question" should include a blank: "______"
        - "options" must be a list of 4 strings
        - "correct_answer" must exactly match one of the options
    - "matching":
        - Use "left" and "right" lists (4 items each)
        - "correct_answer" is a list of 4 integers that represent correct indices

    Make questions moderately challenging, factual, and based on the source material.
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
    DO NOT include triple backticks or markdown. Respond with raw JSON only.
    """ 
    return prompt.strip()
    
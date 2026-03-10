"""
Prompts for quiz generation.

This module contains all prompts used for quiz generation:
- build_quiz_prompt_mixed: For standard mode mixed-type quiz generation
- RAG_PROMPT_*: For enhanced/RAG mode question generation with Bloom's taxonomy

Usage:
    Standard mode (mixed types):
        prompt = build_quiz_prompt_mixed(text, num_questions, types)

    Enhanced/RAG mode (single question type per call):
        Use RAG_PROMPT_MCQ, RAG_PROMPT_TRUE_FALSE, RAG_PROMPT_FILL_BLANK,
        or RAG_PROMPT_MATCHING directly with format() to inject context.
"""
from typing import List
from services.logger import ai_logger as logger


# =============================================================================
# STANDARD MODE PROMPT (for mixed-type generation with gpt-4o-mini)
# =============================================================================

def build_quiz_prompt_mixed(text: str, num_questions: int, types: List[str]) -> str:
    """Build a prompt for generating mixed question types in standard mode."""
    logger.debug("Building mixed quiz prompt with %s questions for types %s", num_questions, types)
    
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

Each object in "quizzes" must include these REQUIRED fields:
- "type": The question type (e.g., "multiple_choice", "true_false", etc.)
- "question": The question text
- "explanation": A clear explanation of why the correct answer is right (1-2 sentences)
- "source": A brief excerpt (1-2 sentences) from the input text that supports this question
- Type-specific fields (see formatting rules below)

Formatting rules:
- "multiple_choice":
    - 4 plausible answers in `options` (MUST be a JSON array of 4 strings)
    - No prefixes like A. or 1)
    - `correct_answer` must match one of the options exactly
- "true_false":
    - `correct_answer` must be a boolean: true or false
- "fill_blank":
    - `question` must contain a blank: "_____"
    - `options` MUST be a JSON array of exactly 4 strings (REQUIRED, not optional, NEVER null)
    - `correct_answer` must match one of the options
- "matching":
    - `question` must be a clear instruction like "Match each term with its definition" (REQUIRED)
    - `left` MUST be a JSON array of exactly 4 strings (NEVER null)
    - `right` MUST be a JSON array of exactly 4 strings (NEVER null)
    - `correct_answer` MUST be a JSON array of 4 integer indices like [0, 1, 2, 3] (NEVER null)

CRITICAL: Every question MUST have `explanation` and `source` string fields. Never omit or return null for `explanation` or `source`. Never return null for options, left, right, or correct_answer fields. Always provide valid arrays.

Rules:
- Be factual, clear, and based on the provided text.
- Do not copy any examples.
- Do not return sample or placeholder questions.

Text to use:
\"\"\"
{text}
\"\"\"
""".strip()

    return prompt


# =============================================================================
# RAG/ENHANCED MODE PROMPTS (for question generation with Bloom's taxonomy)
# =============================================================================

# Bloom level descriptions for prompting
BLOOM_DESCRIPTIONS = {
    "remember": "recall of facts and basic concepts (define, list, name)",
    "understand": "explaining ideas or concepts (describe, summarize, explain)",
    "apply": "using information in new situations (demonstrate, solve, use)",
    "analyze": "drawing connections among ideas (compare, contrast, differentiate)",
    "evaluate": "justifying a decision (argue, defend, critique)",
    "create": "producing original work (design, construct, propose)"
}

# Question-type specific prompts for RAG mode
# Each prompt shows EXACTLY what JSON format is expected to avoid confusion

RAG_PROMPT_MCQ = """You are an expert educational content creator.
Create a {difficulty} difficulty multiple choice question at the {bloom_level} Bloom's Taxonomy level.

Target Concept: {concept_name}
Concept Type: {concept_type}
Bloom Level: {bloom_description}

Context:
{context}

Requirements:
1. Question must be clear, unambiguous, and directly test the concept.
2. Provide exactly 4 options with 1 correct answer and 3 plausible distractors.
3. Do NOT use labels like "A)", "B)", "1." in options - just the text.
4. correct_answer must exactly match one of the options.

Return this exact JSON format:
{{
  "question": "Your question text here?",
  "options": ["Option 1", "Option 2", "Option 3", "Option 4"],
  "correct_answer": "Option 1",
  "confidence_score": 0.95
}}
"""

RAG_PROMPT_TRUE_FALSE = """You are an expert educational content creator.
Create a {difficulty} difficulty true/false question at the {bloom_level} Bloom's Taxonomy level.

Target Concept: {concept_name}
Concept Type: {concept_type}
Bloom Level: {bloom_description}

Context:
{context}

Requirements:
1. Create a statement that is clearly true or false based on the context.
2. The statement should test understanding, not trick the reader.
3. correct_answer must be a boolean: true or false.

Return this exact JSON format:
{{
  "question": "Statement that is either true or false.",
  "correct_answer": true,
  "confidence_score": 0.95
}}
"""

RAG_PROMPT_FILL_BLANK = """You are an expert educational content creator.
Create a {difficulty} difficulty fill-in-the-blank question at the {bloom_level} Bloom's Taxonomy level.

Target Concept: {concept_name}
Concept Type: {concept_type}
Bloom Level: {bloom_description}

Context:
{context}

Requirements:
1. Create a sentence with ONE key term removed, marked with _____ (five underscores).
2. You MUST provide exactly 4 options including the correct answer.
3. Options should be plausible alternatives to make the question challenging.
4. correct_answer must exactly match one of the options.

Return this exact JSON format:
{{
  "question": "The _____ is responsible for generating ATP in cells.",
  "options": ["mitochondria", "nucleus", "ribosome", "cytoplasm"],
  "correct_answer": "mitochondria",
  "confidence_score": 0.95
}}
"""

# Bug fix: Added missing {bloom_level} placeholder to matching prompt (was causing template errors)
RAG_PROMPT_MATCHING = """You are an expert educational content creator.
Create a {difficulty} difficulty matching question at the {bloom_level} Bloom's Taxonomy level.

Topic: {concept_name}

Context (use this to find 4 matchable pairs):
{context}

Your task: Find 4 related terms/concepts from the context and create matching pairs.
Look for: names & roles, terms & definitions, causes & effects, concepts & examples.

OUTPUT REQUIREMENTS (STRICTLY FOLLOW):
1. "question" - A clear instruction like "Match each term with its definition"
2. "left" - MUST be a JSON array with exactly 4 string items
3. "right" - MUST be a JSON array with exactly 4 string items  
4. "correct_answer" - MUST be a JSON array of 4 integers [0-3]
   - The indices show which "right" item matches each "left" item
   - [0,1,2,3] means left[0]→right[0], left[1]→right[1], etc.
   - [2,0,3,1] means left[0]→right[2], left[1]→right[0], etc.
5. "confidence_score" - A float between 0 and 1
6. "explanation" - An educational explanation of each pair (2-4 sentences total)
   - Explain WHY each pair belongs together
   - Use your knowledge to provide educational context
   - DO NOT just list "X matches Y" - explain the relationship
7. "source" - A brief excerpt from the context that supports this question

NEVER return null for any field. All arrays must have exactly 4 items.

JSON FORMAT (copy this structure exactly):
{{
  "question": "Match each scientist with their discovery.",
  "left": ["Einstein", "Newton", "Curie", "Darwin"],
  "right": ["Relativity", "Gravity", "Radioactivity", "Evolution"],
  "correct_answer": [0, 1, 2, 3],
  "confidence_score": 0.95,
  "explanation": "Einstein developed the theory of relativity, revolutionizing our understanding of space and time. Newton formulated the law of universal gravitation. Marie Curie pioneered research on radioactivity, discovering polonium and radium. Darwin proposed the theory of evolution by natural selection.",
  "source": "This matches information found in the section on famous scientists."
}}

"""

# Map question types to their specific RAG prompts
RAG_QUESTION_TYPE_PROMPTS = {
    "multiple_choice": RAG_PROMPT_MCQ,
    "true_false": RAG_PROMPT_TRUE_FALSE,
    "fill_blank": RAG_PROMPT_FILL_BLANK,
    "matching": RAG_PROMPT_MATCHING,
}


# =============================================================================
# FLASHCARD GENERATION PROMPTS
# =============================================================================

def build_flashcard_prompt(
    text: str, 
    num_cards: int,
    card_style: str = "mixed",
    include_hints: bool = False,
) -> str:
    """
    Build a prompt for generating flashcards from text.
    
    Based on best practices from research:
    - Atomic: One fact per card
    - Self-contained: No references to "the text" or "the article"
    - Concise: Front/Back under 15 words each ideally
    - Variety: Mix definitions, "why" questions, and cloze deletions
    
    Args:
        text: Source text to generate flashcards from
        num_cards: Number of flashcards to generate
        card_style: Style of cards ("question_answer", "term_definition", "cloze", "mixed")
        include_hints: Whether to include hints in the output
        
    Returns:
        Formatted prompt string
    """
    logger.debug("Building flashcard prompt for %d cards, style: %s", num_cards, card_style)
    
    style_instructions = _get_card_style_instructions(card_style)
    hint_instruction = _get_hint_instruction(include_hints)
    
    prompt = f"""You are an expert educational content creator specializing in flashcard generation for effective learning.

Create exactly {num_cards} high-quality flashcards from the provided text.

## OUTPUT FORMAT (STRICT JSON)
Return ONLY valid JSON with this exact structure:
{{
  "cards": [
    {{
      "front": "Question or prompt text",
      "back": "Answer or response text"{', "hint": "Hint to help recall the answer"' if include_hints else ''}
    }}
  ]
}}

## FLASHCARD BEST PRACTICES (FOLLOW STRICTLY)

1. **ATOMIC**: Each card tests ONE discrete fact or concept only.
   - BAD: "What are the three main causes of WWI?" (multiple facts)
   - GOOD: "What event triggered the start of WWI?" (single fact)

2. **SELF-CONTAINED**: Cards must be understandable without the original text.
   - BAD: "According to the text, what happened next?"
   - BAD: "What does the author say about this?"
   - GOOD: "What is the primary function of mitochondria?"

3. **CONCISE**: Keep both sides brief (5-15 words ideal).
   - Front: Clear, specific question or prompt
   - Back: Direct answer without restating the question

4. **NO REPETITION**: The answer should NOT restate the question.
   - BAD: Front: "What is the capital of France?" Back: "The capital of France is Paris."
   - GOOD: Front: "What is the capital of France?" Back: "Paris"

{style_instructions}

{hint_instruction}

## IMPORTANT RULES
- Generate EXACTLY {num_cards} cards, no more, no less.
- Use ONLY information from the provided text.
- Ensure factual accuracy - do not invent or assume facts.
- Make questions clear and unambiguous.
- Vary question types when using "mixed" style.
- Do NOT include card numbers or prefixes in the text.

## SOURCE TEXT
\"\"\"
{text}
\"\"\"

Generate the flashcards now as valid JSON:"""

    return prompt.strip()


def _get_card_style_instructions(card_style: str) -> str:
    """Get style-specific instructions for flashcard generation."""
    
    style_map = {
        "question_answer": """## CARD STYLE: Question & Answer
Create cards where the front is a direct question and the back is the answer.
Examples:
- Front: "What year did World War II end?" → Back: "1945"
- Front: "Who developed the theory of relativity?" → Back: "Albert Einstein"
""",
        "term_definition": """## CARD STYLE: Term & Definition
Create cards where the front is a term/concept and the back is its definition.
Examples:
- Front: "Photosynthesis" → Back: "The process by which plants convert sunlight into energy"
- Front: "Mitochondria" → Back: "Cell organelles that generate most of the cell's ATP energy"
""",
        "cloze": """## CARD STYLE: Cloze Deletion (Fill-in-the-blank)
Create cards where the front is a sentence with a key term blanked out (use _____).
Examples:
- Front: "The _____ is the powerhouse of the cell." → Back: "mitochondria"
- Front: "Einstein published his theory of relativity in _____." → Back: "1905"
""",
        "mixed": """## CARD STYLE: Mixed (Variety)
Create a variety of card types for comprehensive learning:
- Some question/answer cards (Who? What? When? Why? How?)
- Some term/definition cards
- Some cloze deletion cards (fill-in-blank with _____)
- Include both factual recall and conceptual understanding questions
Mix these types throughout the deck for engaging study sessions.
""",
    }
    
    return style_map.get(card_style, style_map["mixed"])


def _get_hint_instruction(include_hints: bool) -> str:
    """Get hint instruction based on configuration."""
    if include_hints:
        return """## HINTS (Required)
Include a "hint" field for every card.
Each hint should:
- Give a clue without revealing the answer
- Reference the topic area, first letter, or related concept
- Be shorter than the answer itself
Example: For "What is the capital of France?" → hint: "Starts with 'P', city of lights"

Every card must have a hint field. Do not skip hints on any card.
"""
    return ""


# Prompt for generating flashcards with difficulty levels
def build_flashcard_prompt_with_difficulty(
    text: str,
    num_cards: int,
    difficulty: str = "mixed",
    card_style: str = "mixed",
    include_hints: bool = False,
) -> str:
    """
    Build a flashcard prompt with difficulty level targeting.
    
    Args:
        text: Source text
        num_cards: Number of cards to generate
        difficulty: "easy", "medium", "hard", or "mixed"
        card_style: Style of cards
        include_hints: Whether to include hints
        
    Returns:
        Formatted prompt string
    """
    base_prompt = build_flashcard_prompt(text, num_cards, card_style, include_hints)
    
    difficulty_instructions = {
        "easy": """
## DIFFICULTY: EASY
Focus on:
- Basic definitions and terminology
- Simple factual recall (names, dates, places)
- Recognition-level questions
""",
        "medium": """
## DIFFICULTY: MEDIUM  
Focus on:
- Understanding concepts and relationships
- Cause and effect connections
- Comparison questions
""",
        "hard": """
## DIFFICULTY: HARD
Focus on:
- Application of concepts to new situations
- Analysis and synthesis questions
- "Why" and "How" questions requiring deeper understanding
""",
        "mixed": """
## DIFFICULTY: MIXED
Create a balanced mix of difficulty levels:
- ~30% Easy (basic recall)
- ~50% Medium (understanding)
- ~20% Hard (application/analysis)
"""
    }
    
    difficulty_text = difficulty_instructions.get(difficulty, difficulty_instructions["mixed"])
    
    # Insert difficulty instructions before "## IMPORTANT RULES"
    return base_prompt.replace(
        "## IMPORTANT RULES",
        f"{difficulty_text}\n## IMPORTANT RULES"
    )


# =============================================================================
# Enhanced Flashcard Prompts (RAG-based)
# =============================================================================

ENHANCED_FLASHCARD_PROMPT = """
You are an expert educational content creator specializing in flashcard generation using pedagogical best practices.

## CONTEXT INFORMATION
Concept to cover: {concept_name}
Source Context:
\"\"\"
{context}
\"\"\"

## TASK
Generate {num_cards} high-quality flashcards that test understanding of "{concept_name}" using Bloom's taxonomy levels.

## BLOOM'S TAXONOMY LEVELS FOR FLASHCARDS
- Remember: Basic recall of facts, terms, definitions
- Understand: Explain concepts, compare, interpret meaning
- Apply: Use knowledge in new situations, solve problems
- Analyze: Break down information, identify relationships

## CARD STYLES
{card_style_instruction}

## DIFFICULTY TARGETING
{difficulty_instruction}

## OUTPUT FORMAT
Return a JSON object with the following structure:
{{
  "cards": [
    {{
      "front": "Question or prompt text",
      "back": "Answer or response text",
      "hint": "Optional hint (null if not needed)",
      "bloom_level": "remember|understand|apply|analyze",
      "difficulty_score": 0.1 to 1.0
    }}
  ]
}}

## QUALITY REQUIREMENTS
1. Front (question) should be clear and specific
2. Back (answer) should be concise but complete
3. Each card should test ONE key concept
4. Cards should be self-contained (no "see previous card")
5. Use simple, direct language
6. Avoid yes/no questions unless using true/false style
7. Include source references when relevant
8. Hints should guide without giving away the answer

Generate exactly {num_cards} cards. Return ONLY valid JSON, no additional text.
"""

ENHANCED_FLASHCARD_CARD_STYLES = {
    "question_answer": """
Style: QUESTION-ANSWER
- Front: Direct question (What, How, Why, etc.)
- Back: Clear, complete answer
- Example Front: "What is the primary function of mitochondria?"
- Example Back: "To produce ATP (energy) through cellular respiration"
""",
    "term_definition": """
Style: TERM-DEFINITION
- Front: Technical term or concept name
- Back: Clear definition with examples if helpful
- Example Front: "Photosynthesis"
- Example Back: "The process by which plants convert light energy into chemical energy (glucose), using carbon dioxide and water"
""",
    "cloze": """
Style: CLOZE (Fill-in-the-blank)
- Front: Statement with key term blanked out using _____
- Back: The missing term(s)
- Example Front: "The _____ is the powerhouse of the cell"
- Example Back: "mitochondria"
""",
    "mixed": """
Style: MIXED (Variety of formats)
Create a mix of:
- ~40% Question-Answer format
- ~30% Term-Definition format
- ~30% Cloze (fill-in-blank) format
"""
}

ENHANCED_FLASHCARD_DIFFICULTY = {
    "easy": """
Difficulty: EASY (score 0.1-0.3)
- Basic definitions and terminology
- Simple factual recall
- Recognition-level content
""",
    "medium": """
Difficulty: MEDIUM (score 0.4-0.6)
- Understanding relationships between concepts
- Cause and effect connections
- Comparison and contrast
""",
    "hard": """
Difficulty: HARD (score 0.7-1.0)
- Application to new scenarios
- Analysis of complex relationships
- Synthesis of multiple concepts
""",
    "mixed": """
Difficulty: MIXED
Target a balanced distribution:
- ~30% Easy (0.1-0.3)
- ~50% Medium (0.4-0.6)  
- ~20% Hard (0.7-1.0)
"""
}


def build_enhanced_flashcard_prompt(
    concept_name: str,
    context: str,
    num_cards: int,
    card_style: str = "mixed",
    difficulty: str = "mixed",
) -> str:
    """
    Build a prompt for enhanced (RAG-based) flashcard generation.
    
    This prompt uses retrieved context from the RAG pipeline and
    applies Bloom's taxonomy for educational quality.
    
    Args:
        concept_name: Name of the concept being tested
        context: Retrieved context text for the concept
        num_cards: Number of cards to generate for this concept
        card_style: "question_answer", "term_definition", "cloze", or "mixed"
        difficulty: "easy", "medium", "hard", or "mixed"
        
    Returns:
        Formatted prompt string
    """
    card_style_instruction = ENHANCED_FLASHCARD_CARD_STYLES.get(
        card_style, ENHANCED_FLASHCARD_CARD_STYLES["mixed"]
    )
    difficulty_instruction = ENHANCED_FLASHCARD_DIFFICULTY.get(
        difficulty, ENHANCED_FLASHCARD_DIFFICULTY["mixed"]
    )
    
    return ENHANCED_FLASHCARD_PROMPT.format(
        concept_name=concept_name,
        context=context,
        num_cards=num_cards,
        card_style_instruction=card_style_instruction,
        difficulty_instruction=difficulty_instruction,
    )

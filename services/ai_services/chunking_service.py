import math
import asyncio
from typing import List
import tiktoken
from services.ai_services.openai_service import (
    generate_quiz_for_type,
    QUESTION_TYPE_PROMPTS,
    generate_quiz_async
)
from schemas.quiz import Question
from services.logger import ai_logger as logger

logger.info("Chunking service initialized")

async def smart_chunk_text(
    text: str,
    num_questions: int,
    model_token_limit: int = 8000,
    small_text_threshold: int = 3000
) -> List[str]:
    """
    Splits text into a certain number of chunks based on both
    text size and # questions, with safeguards against context limit.
    """
    logger.info("Smart chunking text")
    enc = tiktoken.get_encoding("cl100k_base")
    tokens = enc.encode(text)
    total_tokens = len(tokens)

    if total_tokens <= small_text_threshold:
        return [enc.decode(tokens)]

    # baseline chunk_count = # questions
    chunk_count = max(1, num_questions)
    chunk_size = math.ceil(total_tokens / chunk_count)

    # adjust chunk_count if chunk_size > model_token_limit
    while chunk_size > model_token_limit and chunk_count < total_tokens:
        chunk_count += 1
        chunk_size = math.ceil(total_tokens / chunk_count)

    chunks = []
    start = 0
    for _ in range(chunk_count):
        end = min(start + chunk_size, total_tokens)
        chunk_tokens = tokens[start:end]
        chunks.append(enc.decode(chunk_tokens))
        start = end
        if start >= total_tokens:
            break

    return chunks

async def generate_quizzes_async(
    text: str,
    total_questions: int,
    question_types: List[str],
    model_token_limit: int = 8000
) -> List[Question]:
    logger.info("Generating questions asynchronously")

    

    # 1. Chunk once up front
    chunks = await smart_chunk_text(text, total_questions, model_token_limit=model_token_limit)
    logger.info(f"Smart chunked into {len(chunks)} segments")

    # 2. Handle "mixed"
    if "mixed" in question_types:
        question_types = list(QUESTION_TYPE_PROMPTS.keys())

    # 3. Distribute total questions across types
    base = total_questions // len(question_types)
    remainder = total_questions % len(question_types)
    q_counts = {qt: base for qt in question_types}
    for qt in question_types[:remainder]:
        q_counts[qt] += 1

    logger.info(f"Distribution across types: {q_counts}")

    # 4. Launch one LLM call per type, using full/partial text
    tasks = []
    for qtype in question_types:
        merged_text = "\n\n".join(chunks)
        tasks.append(generate_quiz_for_type(qtype, merged_text, q_counts[qtype]))

    results = await asyncio.gather(*tasks)

    # 5. Flatten results
    questions = [q for group in results for q in group]

    return questions[:total_questions]

async def generate_quizzes_single_async(
    text: str,
    total_questions: int,
    question_types: List[str],
    model_token_limit: int = 8000
) -> List[Question]:
    """
    Asynchronously chunkifies text + calls LLM to generate questions concurrently.
    """
    logger.info("Generating questions asynchronously")
    # 1. Chunk text
    chunks = await smart_chunk_text(text, total_questions, model_token_limit=model_token_limit)
    chunk_count = len(chunks)

    # 2. Distribute total_questions among chunks
    base_q = total_questions // chunk_count
    remainder = total_questions % chunk_count

    tasks = []
    for i, chunk in enumerate(chunks):
        q_for_this_chunk = base_q + (1 if i < remainder else 0)
        if q_for_this_chunk <= 0:
            break
        
        # Create async task for each chunk
        tasks.append(asyncio.create_task(
            generate_quiz_async(chunk, q_for_this_chunk, question_types)
        ))

    # 3. Run all chunk calls in parallel
    raw_results = await asyncio.gather(*tasks)

    all_questions = []
    for raw in raw_results:
        for question in raw:
            all_questions.append(question)
    
    # Filter questions based on question_types
    if "mixed" in question_types:
        filtered = all_questions
    else:
        allowed_types = set(question_types)
        filtered = [
            q for q in all_questions
            if getattr(q, "type", None) in allowed_types
        ]

    return filtered[:total_questions]
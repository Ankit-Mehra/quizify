import math
import asyncio
from typing import List, Optional
import tiktoken
from services.ai_services.llm_client_service import (
    generate_quiz_for_type,
    QUESTION_TYPE_PROMPTS,
    generate_quiz_async
)
from schemas.quiz import Question
from services.logger import ai_logger as logger

logger.debug("Chunking service initialized")

async def smart_chunk_text(
    text: str,
    num_questions: int,
    model_token_limit: int = 8000,
    small_text_threshold: int = 500
) -> List[str]:
    """
    Splits text into chunks for parallel LLM processing.
    
    Chunks are sized based on both text length and number of questions requested,
    with safeguards to stay within model context limits.
    
    Args:
        text: The input text to chunk
        num_questions: Number of questions to generate (influences chunk count)
        model_token_limit: Maximum tokens per chunk (default: 8000)
        small_text_threshold: Minimum tokens to trigger chunking (default: 500).
            Text below this threshold returns as a single chunk (no parallelism).
            Set to 500 tokens (~2KB) to enable parallel LLM calls for most content.
            
    Returns:
        List of text chunks for parallel processing
    """
    logger.debug("Smart chunking text")
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
    model_token_limit: int = 8000,
    user_id: Optional[str] = None,
    trace_id: Optional[str] = None,
    generation_mode: str = "standard",
    content_source_type: Optional[str] = None,
) -> List[Question]:
    """
    Generate quiz questions asynchronously with parallel LLM calls per question type.
    
    Args:
        text: Source text to generate questions from
        total_questions: Total number of questions to generate
        question_types: List of question types to include
        model_token_limit: Maximum tokens per chunk
        user_id: Optional user ID for PostHog analytics
        trace_id: Optional trace ID for correlating related LLM calls
        generation_mode: "standard" or "enhanced" for analytics tracking
        content_source_type: "text", "file", or "url" for analytics tracking
        
    Returns:
        List of generated Question objects
    """
    logger.debug("Generating questions asynchronously")

    # 1. Chunk once up front
    chunks = await smart_chunk_text(text, total_questions, model_token_limit=model_token_limit)
    logger.debug("Smart chunked into %s segments", len(chunks))

    # 2. Handle "mixed"
    if "mixed" in question_types:
        question_types = list(QUESTION_TYPE_PROMPTS.keys())

    # 3. Distribute total questions across types
    base = total_questions // len(question_types)
    remainder = total_questions % len(question_types)
    q_counts = {qt: base for qt in question_types}
    for qt in question_types[:remainder]:
        q_counts[qt] += 1

    logger.debug("Distribution across types: %s", q_counts)

    # 4. Launch one LLM call per type, using full/partial text
    tasks = []
    for qtype in question_types:
        merged_text = "\n\n".join(chunks)
        tasks.append(generate_quiz_for_type(
            qtype, merged_text, q_counts[qtype],
            user_id=user_id, trace_id=trace_id,
            generation_mode=generation_mode,
            content_source_type=content_source_type
        ))

    results = await asyncio.gather(*tasks)

    # 5. Flatten results
    questions = [q for group in results for q in group]

    return questions[:total_questions]

async def generate_quizzes_single_async(
    text: str,
    total_questions: int,
    question_types: List[str],
    model_token_limit: int = 8000,
    user_id: Optional[str] = None,
    trace_id: Optional[str] = None,
    generation_mode: str = "standard",
    content_source_type: Optional[str] = None,
) -> List[Question]:
    """
    Asynchronously chunkifies text + calls LLM to generate questions concurrently.
    
    This is the primary quiz generation entry point used by handlers.
    
    Args:
        text: Source text to generate questions from
        total_questions: Total number of questions to generate
        question_types: List of question types to include
        model_token_limit: Maximum tokens per chunk
        user_id: Optional user ID for PostHog analytics
        trace_id: Optional trace ID for correlating related LLM calls
        generation_mode: "standard" or "enhanced" for analytics tracking
        content_source_type: "text", "file", or "url" for analytics tracking
        
    Returns:
        List of generated Question objects
    """
    logger.debug("Generating questions asynchronously")
    # 1. Chunk text
    chunks = await smart_chunk_text(text, total_questions, model_token_limit=model_token_limit)
    chunk_count = len(chunks)
    parallel_note = f" ({chunk_count} parallel LLM calls)" if chunk_count > 1 else " (single LLM call)"
    logger.info("Smart chunked text into %d segment(s) for %d questions%s", chunk_count, total_questions, parallel_note)

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
            generate_quiz_async(
                chunk, q_for_this_chunk, question_types,
                user_id=user_id, trace_id=trace_id,
                generation_mode=generation_mode,
                content_source_type=content_source_type
            )
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
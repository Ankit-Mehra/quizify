"""
Unit tests for smart_chunk_text function in chunking_service.

Tests cover:
- Small text threshold boundary behavior (500 tokens default)
- Chunking based on question count
- Edge cases around threshold boundaries
- Token limit safeguards
"""

import pytest
import tiktoken
from services.ai_services.chunking_service import smart_chunk_text


# Helper to generate text with approximate token count
def generate_text_with_tokens(target_tokens: int) -> str:
    """Generate text with at least the target number of tokens."""
    enc = tiktoken.get_encoding("cl100k_base")
    # Use simple words that are ~1 token each
    words = ["hello", "world", "test", "data", "chunk", "text", "sample", "words"]
    text = ""
    idx = 0
    while len(enc.encode(text)) < target_tokens:
        text += words[idx % len(words)] + " "
        idx += 1
    return text.strip()


def count_tokens(text: str) -> int:
    """Count tokens in text using tiktoken."""
    enc = tiktoken.get_encoding("cl100k_base")
    return len(enc.encode(text))


class TestSmartChunkTextThreshold:
    """Tests for small_text_threshold behavior."""

    @pytest.mark.asyncio
    async def test_text_below_threshold_returns_single_chunk(self):
        """Text with 499 tokens should return exactly 1 chunk (no chunking)."""
        text = generate_text_with_tokens(499)
        
        chunks = await smart_chunk_text(text, num_questions=10)
        
        assert len(chunks) == 1
        assert chunks[0] == text  # Original text preserved

    @pytest.mark.asyncio
    async def test_text_above_threshold_gets_chunked(self):
        """Text well above threshold should be chunked based on question count."""
        # Use 1000 tokens to be well above the 500 threshold
        text = generate_text_with_tokens(1000)
        actual_tokens = count_tokens(text)
        
        # Verify we generated enough tokens (allow small variance from strip)
        assert actual_tokens >= 990, f"Expected >= 990 tokens, got {actual_tokens}"
        
        # With 5 questions, expect 5 chunks
        chunks = await smart_chunk_text(text, num_questions=5)
        
        assert len(chunks) == 5, f"Expected 5 chunks for 5 questions, got {len(chunks)}"
        # Verify all content is preserved (roughly)
        reconstructed = "".join(chunks)
        assert count_tokens(reconstructed) >= actual_tokens - 10  # Allow small variance

    @pytest.mark.asyncio
    async def test_exactly_500_tokens_returns_single_chunk(self):
        """Text with exactly 500 tokens should return 1 chunk (at threshold)."""
        text = generate_text_with_tokens(500)
        
        chunks = await smart_chunk_text(text, num_questions=10)
        
        assert len(chunks) == 1

    @pytest.mark.asyncio
    async def test_custom_threshold_respected(self):
        """Custom small_text_threshold should be respected."""
        text = generate_text_with_tokens(200)
        
        # With default threshold (500), should return 1 chunk
        chunks_default = await smart_chunk_text(text, num_questions=5)
        assert len(chunks_default) == 1
        
        # With lower threshold (100), should chunk
        chunks_custom = await smart_chunk_text(
            text, num_questions=5, small_text_threshold=100
        )
        assert len(chunks_custom) > 1


class TestSmartChunkTextQuestionDistribution:
    """Tests for chunking based on question count."""

    @pytest.mark.asyncio
    async def test_chunk_count_based_on_questions(self):
        """Number of chunks should be influenced by num_questions."""
        text = generate_text_with_tokens(1000)
        
        # More questions = potentially more chunks
        chunks_5q = await smart_chunk_text(text, num_questions=5)
        chunks_10q = await smart_chunk_text(text, num_questions=10)
        
        # With more questions, should have same or more chunks
        assert len(chunks_10q) >= len(chunks_5q)

    @pytest.mark.asyncio
    async def test_single_question_produces_single_chunk(self):
        """With 1 question, should produce 1 chunk regardless of text size."""
        text = generate_text_with_tokens(1000)
        
        chunks = await smart_chunk_text(text, num_questions=1)
        
        assert len(chunks) == 1


class TestSmartChunkTextModelLimit:
    """Tests for model token limit safeguards."""

    @pytest.mark.asyncio
    async def test_chunks_respect_model_limit(self):
        """Each chunk should be under model_token_limit."""
        text = generate_text_with_tokens(5000)
        model_limit = 1000
        
        chunks = await smart_chunk_text(
            text, num_questions=10, model_token_limit=model_limit
        )
        
        for chunk in chunks:
            assert count_tokens(chunk) <= model_limit + 10  # Small tolerance for encoding

    @pytest.mark.asyncio
    async def test_large_text_auto_increases_chunks(self):
        """Very large text should automatically create more chunks to stay under limit."""
        text = generate_text_with_tokens(10000)
        model_limit = 2000
        
        chunks = await smart_chunk_text(
            text, num_questions=3, model_token_limit=model_limit
        )
        
        # Should create more than 3 chunks due to model limit
        assert len(chunks) >= 5
        # Each chunk should respect limit
        for chunk in chunks:
            assert count_tokens(chunk) <= model_limit + 10


class TestSmartChunkTextEdgeCases:
    """Edge case tests."""

    @pytest.mark.asyncio
    async def test_empty_text_returns_empty_chunk(self):
        """Empty text should return single empty chunk."""
        chunks = await smart_chunk_text("", num_questions=5)
        
        assert len(chunks) == 1
        assert chunks[0] == ""

    @pytest.mark.asyncio
    async def test_very_small_text(self):
        """Very small text (few words) should return 1 chunk."""
        text = "Hello world"
        
        chunks = await smart_chunk_text(text, num_questions=10)
        
        assert len(chunks) == 1
        assert chunks[0] == text

    @pytest.mark.asyncio
    async def test_zero_questions_handled(self):
        """Zero questions should be handled gracefully (min 1 chunk)."""
        text = generate_text_with_tokens(1000)
        
        chunks = await smart_chunk_text(text, num_questions=0)
        
        assert len(chunks) >= 1

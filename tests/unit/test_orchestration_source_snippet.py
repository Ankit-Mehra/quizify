"""Unit tests for source snippet formatting in QuizOrchestrationService."""

import pytest

from services.ai_services.orchestration_service import QuizOrchestrationService


class TestOrchestrationSourceSnippet:
    @pytest.fixture
    def service(self):
        return QuizOrchestrationService()

    def test_empty_context_returns_empty(self, service):
        assert service._format_source_snippet("") == ""
        assert service._format_source_snippet("   \n\t  ") == ""

    def test_short_context_returns_normalized_whitespace(self, service):
        context = "Hello   world\n\nthis\tis   Quizify"
        assert service._format_source_snippet(context, max_words=100) == "Hello world this is Quizify"

    def test_exact_max_words_returns_normalized_without_separator(self, service):
        context = " ".join([f"w{i}" for i in range(100)])
        assert service._format_source_snippet(context, max_words=100) == context

    def test_long_context_returns_head_and_tail_with_separator(self, service):
        words = [f"w{i}" for i in range(150)]
        context = " ".join(words)
        snippet = service._format_source_snippet(context, max_words=100)
        assert "..." in snippet
        assert snippet.startswith(" ".join(words[:50]))
        assert snippet.endswith(" ".join(words[-50:]))

    def test_head_tail_budget_is_rebalanced_when_exceeding_max_words(self, service):
        words = [f"w{i}" for i in range(50)]
        context = " ".join(words)
        snippet = service._format_source_snippet(context, max_words=10, head_words=9, tail_words=9)
        assert snippet.startswith(" ".join(words[:5]))
        assert snippet.endswith(" ".join(words[-5:]))

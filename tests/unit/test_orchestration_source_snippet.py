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

    def test_head_only_truncation_includes_separator(self, service):
        words = [f"w{i}" for i in range(20)]
        context = " ".join(words)
        # max_words=10, head_words=5, tail_words=0
        snippet = service._format_source_snippet(context, max_words=10, head_words=5, tail_words=0)
        # Implementation uses ' [......] ' separator (with spaces) and joins parts with spaces
        # Result: "w0 w1 w2 w3 w4" + " " + " [......] " = "w0 w1 w2 w3 w4  [......] "
        assert snippet == "w0 w1 w2 w3 w4  [......] "

    def test_tail_only_truncation_includes_separator(self, service):
        words = [f"w{i}" for i in range(20)]
        context = " ".join(words)
        # max_words=10, head_words=0, tail_words=5
        snippet = service._format_source_snippet(context, max_words=10, head_words=0, tail_words=5)
        # Implementation uses ' [......] ' separator (with spaces) and joins parts with spaces
        # Result: " [......] " + " " + "w15 w16 w17 w18 w19" = " [......]  w15 w16 w17 w18 w19"
        assert snippet == " [......]  w15 w16 w17 w18 w19"

    def test_zero_or_negative_max_words_returns_separator_only(self, service):
        context = "some context words"
        # max_words=0 -> head=0, tail=0 -> returns separator only
        # Since separator is " [......] ", and no head/tail, result is just the separator
        assert service._format_source_snippet(context, max_words=0) == " [......] "
        # max_words=-5 -> treated as 0 -> returns separator
        assert service._format_source_snippet(context, max_words=-5) == " [......] "

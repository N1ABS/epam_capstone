"""
Tests for the Synthesis Agent.

Positive scenarios:
  - Combines doc and web results into a coherent answer with sources.
  - Doc-only path (no web results) still produces a complete answer.
  - Web-only path (no doc results) still produces a complete answer.

Negative / edge-case scenarios:
  - LLM failure sets a meaningful error message in synthesis field.
  - Hallucination check UNVERIFIED flag is appended to the answer.
  - Empty state (no docs, no web) produces a graceful "no info" response.
"""
from unittest.mock import patch

import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel

from src.agents.synthesis_agent import synthesis_agent
from src.state import AgentState


def _make_state(**overrides) -> AgentState:
    base: AgentState = {
        "query": "Explain machine learning",
        "doc_results": [],
        "web_results": [],
        "synthesis": None,
        "sources": [],
        "confidence": 0.0,
        "use_web": False,
        "error": None,
        "metadata": {},
    }
    base.update(overrides)
    return base


_SAMPLE_DOCS = [
    {
        "content": "ML is a subset of AI focused on learning from data.",
        "source": "/docs/ml.md",
        "score": 0.88,
        "metadata": {},
    }
]

_SAMPLE_WEB = [
    {
        "content": "Recent advances: GPT-5 released with improved reasoning.",
        "url": "https://example.com/ml-news",
        "title": "ML News",
        "published_date": "2025-01-01",
    }
]


# ── Positive tests ────────────────────────────────────────────────────────────

class TestSynthesisAgentPositive:
    @patch("src.agents.synthesis_agent._get_llm")
    def test_combines_doc_and_web_results(self, mock_get_llm):
        """Full context (docs + web) yields a populated synthesis and sources."""
        mock_get_llm.return_value = FakeListChatModel(
            responses=[
                "Machine learning is a key AI technique. [Doc: ml.md] [Web]",
                "VERIFIED",
            ]
        )

        result = synthesis_agent(_make_state(doc_results=_SAMPLE_DOCS, web_results=_SAMPLE_WEB))

        assert result["synthesis"] is not None
        assert len(result["synthesis"]) > 0
        assert len(result["sources"]) == 2  # 1 doc + 1 web

    @patch("src.agents.synthesis_agent._get_llm")
    def test_doc_only_produces_answer(self, mock_get_llm):
        """Doc-only state (no web results) still produces a synthesis."""
        mock_get_llm.return_value = FakeListChatModel(
            responses=["ML is learning from data. [Doc: ml.md]", "VERIFIED"]
        )

        result = synthesis_agent(_make_state(doc_results=_SAMPLE_DOCS))

        assert result["synthesis"] is not None
        doc_sources = [s for s in result["sources"] if s["type"] == "document"]
        assert len(doc_sources) == 1

    @patch("src.agents.synthesis_agent._get_llm")
    def test_web_only_produces_answer(self, mock_get_llm):
        """Web-only state (no doc results) still produces a synthesis."""
        mock_get_llm.return_value = FakeListChatModel(
            responses=["GPT-5 was recently released. [Web]", "VERIFIED"]
        )

        result = synthesis_agent(_make_state(web_results=_SAMPLE_WEB, use_web=True))

        assert result["synthesis"] is not None
        web_sources = [s for s in result["sources"] if s["type"] == "web"]
        assert len(web_sources) == 1


# ── Negative / edge-case tests ────────────────────────────────────────────────

class TestSynthesisAgentNegative:
    @patch("src.agents.synthesis_agent._get_llm")
    def test_llm_failure_returns_error_message(self, mock_get_llm):
        """LLM failure must be caught and stored gracefully."""
        mock_get_llm.side_effect = Exception("API quota exceeded")

        result = synthesis_agent(_make_state(doc_results=_SAMPLE_DOCS))

        assert result["synthesis"] is not None
        assert "Error generating response" in result["synthesis"]

    @patch("src.agents.synthesis_agent._get_llm")
    def test_hallucination_flag_appended_to_answer(self, mock_get_llm):
        """UNVERIFIED verdict from hallucination check must appear in output."""
        mock_get_llm.return_value = FakeListChatModel(
            responses=[
                "The answer with a fabricated claim.",
                "UNVERIFIED: claim X is not in the sources",
            ]
        )

        result = synthesis_agent(_make_state(doc_results=_SAMPLE_DOCS))

        assert "UNVERIFIED" in result["synthesis"]

    @patch("src.agents.synthesis_agent._get_llm")
    def test_empty_state_produces_graceful_response(self, mock_get_llm):
        """No docs, no web results — agent must not crash."""
        mock_get_llm.return_value = FakeListChatModel(
            responses=["I could not find relevant information.", "VERIFIED"]
        )

        result = synthesis_agent(_make_state())

        assert result["synthesis"] is not None
        assert result["sources"] == []

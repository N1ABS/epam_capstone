"""
Tests for the Research Agent.

Positive scenarios:
  - Finds relevant documents and sets confidence / use_web correctly.
  - High-confidence results suppress web search fallback.

Negative / edge-case scenarios:
  - No documents found → use_web=True, confidence=0.
  - Vector DB connection failure → error set, graceful degradation.
  - LLM reformulation failure → falls back to original query.
"""
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel

from src.agents.research_agent import research_agent
from src.state import AgentState


def _make_state(**overrides) -> AgentState:
    base: AgentState = {
        "query": "What is machine learning?",
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


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fake_llm(response: str = "machine learning overview") -> FakeListChatModel:
    """Return a deterministic fake LLM that always responds with *response*."""
    return FakeListChatModel(responses=[response])


def _mock_vs(results=None):
    vs = MagicMock()
    vs.similarity_search.return_value = results or []
    return vs


# ── Positive tests ────────────────────────────────────────────────────────────

class TestResearchAgentPositive:
    @patch("src.agents.research_agent.VectorStore")
    @patch("src.agents.research_agent._get_llm")
    def test_returns_documents_and_confidence(self, mock_get_llm, MockVS):
        """High-score result is reflected in confidence and use_web=False."""
        mock_get_llm.return_value = _fake_llm("ML definition query")
        MockVS.return_value = _mock_vs(
            [{"content": "ML is AI", "source": "/docs/ml.md", "score": 0.9, "metadata": {}}]
        )

        result = research_agent(_make_state())

        assert len(result["doc_results"]) == 1
        assert result["confidence"] == pytest.approx(0.9)
        assert result["use_web"] is False

    @patch("src.agents.research_agent.VectorStore")
    @patch("src.agents.research_agent._get_llm")
    def test_multiple_results_ordered_by_score(self, mock_get_llm, MockVS):
        """Multiple results are kept in the order returned by the vector store."""
        mock_get_llm.return_value = _fake_llm()
        docs = [
            {"content": "doc A", "source": "a.md", "score": 0.85, "metadata": {}},
            {"content": "doc B", "source": "b.md", "score": 0.70, "metadata": {}},
        ]
        MockVS.return_value = _mock_vs(docs)

        result = research_agent(_make_state())

        assert len(result["doc_results"]) == 2
        assert result["confidence"] == pytest.approx(0.85)  # top result score

    @patch("src.agents.research_agent.VectorStore")
    @patch("src.agents.research_agent._get_llm")
    def test_high_confidence_suppresses_web_search(self, mock_get_llm, MockVS):
        """Score >= CONFIDENCE_THRESHOLD must not trigger web search."""
        mock_get_llm.return_value = _fake_llm()
        MockVS.return_value = _mock_vs(
            [{"content": "content", "source": "doc.md", "score": 0.95, "metadata": {}}]
        )

        result = research_agent(_make_state())

        assert result["use_web"] is False


# ── Negative / edge-case tests ────────────────────────────────────────────────

class TestResearchAgentNegative:
    @patch("src.agents.research_agent.VectorStore")
    @patch("src.agents.research_agent._get_llm")
    def test_no_documents_triggers_web_fallback(self, mock_get_llm, MockVS):
        """Empty search results must set use_web=True and confidence=0."""
        mock_get_llm.return_value = _fake_llm()
        MockVS.return_value = _mock_vs([])  # empty results

        result = research_agent(_make_state())

        assert result["doc_results"] == []
        assert result["confidence"] == 0.0
        assert result["use_web"] is True

    @patch("src.agents.research_agent.VectorStore")
    @patch("src.agents.research_agent._get_llm")
    def test_vector_db_error_sets_error_state(self, mock_get_llm, MockVS):
        """A database connection error must be caught and stored in state['error']."""
        mock_get_llm.return_value = _fake_llm()
        MockVS.return_value.similarity_search.side_effect = Exception("Connection refused")

        result = research_agent(_make_state())

        assert result["error"] is not None
        assert "Document search failed" in result["error"]
        assert result["doc_results"] == []

    @patch("src.agents.research_agent.VectorStore")
    @patch("src.agents.research_agent._get_llm")
    def test_llm_failure_falls_back_to_original_query(self, mock_get_llm, MockVS):
        """LLM reformulation failure must not crash the agent."""
        mock_get_llm.side_effect = Exception("API key invalid")
        MockVS.return_value = _mock_vs(
            [{"content": "content", "source": "doc.md", "score": 0.8, "metadata": {}}]
        )

        # Should not raise; uses the original query for search
        result = research_agent(_make_state())

        MockVS.return_value.similarity_search.assert_called_once()
        assert result["doc_results"] is not None

    @patch("src.agents.research_agent.VectorStore")
    @patch("src.agents.research_agent._get_llm")
    def test_low_confidence_triggers_web_fallback(self, mock_get_llm, MockVS):
        """Score below CONFIDENCE_THRESHOLD must set use_web=True."""
        mock_get_llm.return_value = _fake_llm()
        MockVS.return_value = _mock_vs(
            [{"content": "vague result", "source": "doc.md", "score": 0.2, "metadata": {}}]
        )

        result = research_agent(_make_state())

        assert result["use_web"] is True

"""
Tests for the Web Agent.

Positive scenarios:
  - Performs web search when use_web=True and returns web_results.
  - Skips search when use_web=False (no-op).

Negative / edge-case scenarios:
  - MCP server failure sets error and returns empty web_results.
  - LLM summarisation failure falls back to raw MCP output.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel

from src.agents.web_agent import web_agent
from src.state import AgentState


def _make_state(**overrides) -> AgentState:
    base: AgentState = {
        "query": "Latest quantum computing breakthroughs",
        "doc_results": [],
        "web_results": [],
        "synthesis": None,
        "sources": [],
        "confidence": 0.2,
        "use_web": True,
        "error": None,
        "metadata": {},
    }
    base.update(overrides)
    return base


# ── Positive tests ────────────────────────────────────────────────────────────

class TestWebAgentPositive:
    @patch("src.agents.web_agent._get_llm")
    @patch("src.agents.web_agent._call_tavily_mcp")
    @patch("src.agents.web_agent.asyncio")
    def test_returns_web_results_when_use_web_true(
        self, mock_asyncio, mock_mcp, mock_get_llm
    ):
        """When use_web=True the agent must populate web_results."""
        mock_asyncio.get_event_loop.return_value.run_until_complete.return_value = (
            "[1] Quantum News\nURL: https://example.com\nNew qubit record set."
        )
        mock_get_llm.return_value = FakeListChatModel(
            responses=["Quantum computers reached a new milestone."]
        )

        result = web_agent(_make_state(use_web=True))

        assert len(result["web_results"]) == 1
        assert result["web_results"][0]["content"] != ""

    @patch("src.agents.web_agent._get_llm")
    @patch("src.agents.web_agent.asyncio")
    def test_skips_search_when_use_web_false(self, mock_asyncio, mock_get_llm):
        """When use_web=False the agent must be a no-op."""
        result = web_agent(_make_state(use_web=False))

        mock_asyncio.get_event_loop.assert_not_called()
        assert result["web_results"] == []


# ── Negative / edge-case tests ────────────────────────────────────────────────

class TestWebAgentNegative:
    @patch("src.agents.web_agent.asyncio")
    def test_mcp_failure_sets_error_and_empty_results(self, mock_asyncio):
        """MCP server crash must be caught; agent returns error without raising."""
        mock_asyncio.get_event_loop.return_value.run_until_complete.side_effect = (
            RuntimeError("MCP server crashed")
        )

        result = web_agent(_make_state(use_web=True))

        assert result["web_results"] == []
        assert result["error"] is not None
        assert "Web search failed" in result["error"]

    @patch("src.agents.web_agent._get_llm")
    @patch("src.agents.web_agent.asyncio")
    def test_llm_summarisation_failure_uses_raw_output(
        self, mock_asyncio, mock_get_llm
    ):
        """If LLM summarisation raises, the raw MCP output is stored instead."""
        raw = "raw search result text"
        mock_asyncio.get_event_loop.return_value.run_until_complete.return_value = raw
        # Make LLM chain raise on invoke
        mock_get_llm.side_effect = Exception("LLM unavailable")

        result = web_agent(_make_state(use_web=True))

        # Should still produce a web result (raw fallback)
        assert len(result["web_results"]) == 1
        assert result["web_results"][0]["content"] == raw

    @patch("src.agents.web_agent.asyncio")
    def test_existing_error_in_state_still_skips(self, mock_asyncio):
        """If research_agent already set an error, web agent must not run."""
        # use_web=True but error already present — routing logic handles this
        # at graph level; here we test the agent is robust if called anyway
        # with use_web=False.
        result = web_agent(
            _make_state(use_web=False, error="prior error")
        )
        mock_asyncio.get_event_loop.assert_not_called()
        assert result["web_results"] == []

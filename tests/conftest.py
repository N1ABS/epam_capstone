"""
Shared pytest fixtures for all test modules.
"""
import pytest

from src.state import AgentState


# ── Base state factories ──────────────────────────────────────────────────────

@pytest.fixture
def base_state() -> AgentState:
    """Minimal valid AgentState with no results."""
    return {
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


@pytest.fixture
def state_with_docs(base_state) -> AgentState:
    """State pre-populated with high-confidence document results."""
    return {
        **base_state,
        "doc_results": [
            {
                "content": "Machine learning is a subset of artificial intelligence.",
                "source": "/docs/ml_overview.md",
                "score": 0.87,
                "metadata": {"type": "markdown"},
            },
            {
                "content": "Deep learning uses multi-layered neural networks.",
                "source": "/docs/ml_overview.md",
                "score": 0.75,
                "metadata": {"type": "markdown"},
            },
        ],
        "confidence": 0.87,
        "use_web": False,
    }


@pytest.fixture
def state_with_web(base_state) -> AgentState:
    """State pre-populated with web results (use_web already satisfied)."""
    return {
        **base_state,
        "use_web": True,
        "web_results": [
            {
                "content": "Recent advances in ML include large language models.",
                "url": "https://example.com/ml-news",
                "title": "ML News 2025",
                "published_date": "2025-01-01",
            }
        ],
    }


@pytest.fixture
def state_no_docs(base_state) -> AgentState:
    """State where research found nothing — web fallback required."""
    return {
        **base_state,
        "query": "Latest news about quantum computing breakthroughs today",
        "doc_results": [],
        "confidence": 0.0,
        "use_web": True,
    }

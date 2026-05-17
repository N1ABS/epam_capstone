"""Shared state TypedDicts flowing through the LangGraph agent pipeline."""
from typing import Any, Dict, List, Optional

from typing_extensions import TypedDict


class DocumentResult(TypedDict):
    """A single retrieved document chunk from the vector store."""
    content: str
    source: str
    score: float
    metadata: Dict[str, Any]


class WebResult(TypedDict):
    """A single result from the Tavily MCP web search."""
    content: str
    url: str
    title: str
    published_date: Optional[str]


class AgentState(TypedDict):
    """
    Shared state flowing through every LangGraph node.

    Populated incrementally:
      research_agent  → doc_results, confidence, use_web
      web_agent       → web_results  (only when use_web=True)
      synthesis_agent → synthesis, sources
    """
    query: str
    doc_results: List[DocumentResult]
    web_results: List[WebResult]
    synthesis: Optional[str]
    sources: List[Dict[str, Any]]
    confidence: float
    use_web: bool
    error: Optional[str]
    metadata: Dict[str, Any]

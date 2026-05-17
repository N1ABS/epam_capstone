"""
Orchestrator
============
Builds and compiles the LangGraph StateGraph that connects the three agents.

Graph topology:
  research_agent
       │
       ├─ confidence >= threshold ──► synthesis_agent
       │
       └─ confidence <  threshold ──► web_agent ──► synthesis_agent

Security:
  - validate_input()       sanitises and rejects prompt-injection attempts.
  - check_rate_limit()     enforces a per-user sliding-window request quota.
  - detect_and_anonymise() detects PII so it is never written to plain logs.
"""
import logging
import re
from typing import Literal

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from opentelemetry.trace import Status, StatusCode

from src.agents.research_agent import research_agent
from src.agents.synthesis_agent import synthesis_agent
from src.agents.web_agent import web_agent
from src.observability.telemetry import get_tracer
from src.security.pii_detector import detect_and_anonymise
from src.security.rate_limiter import check_rate_limit
from src.state import AgentState

logger = logging.getLogger(__name__)

# ── Input validation ──────────────────────────────────────────────────────────

_INJECTION_PATTERNS = [
    r"ignore\s+(previous|prior|all)\s+instructions",
    r"forget\s+everything",
    r"you\s+are\s+now\s+a\s+different",
    r"(reveal|show|print)\s+(your\s+)?(system\s+prompt|instructions|prompt)",
    r"override\s+your",
    r"pretend\s+you\s+(are|were)",
    r"act\s+as\s+if",
    r"disregard\s+your",
    r"do\s+anything\s+now",
    r"jailbreak",
]
_INJECTION_RE = re.compile(
    "|".join(_INJECTION_PATTERNS), re.IGNORECASE
)


def validate_input(query: str) -> str:
    """
    Sanitise and validate a user query.

    Raises ValueError for:
      - empty / whitespace-only queries
      - queries exceeding 2 000 characters
      - prompt-injection patterns
    """
    query = query.strip()
    if not query:
        raise ValueError("Query cannot be empty.")
    if len(query) > 2_000:
        raise ValueError("Query exceeds the maximum length of 2 000 characters.")
    if _INJECTION_RE.search(query):
        logger.warning("Prompt injection attempt blocked: %.100s", query)
        raise ValueError(
            "Query contains disallowed patterns. Please rephrase your question."
        )
    return query


# ── Routing ───────────────────────────────────────────────────────────────────

def _route_after_research(
    state: AgentState,
) -> Literal["web_agent", "synthesis_agent"]:
    """Decide whether to call the web agent after research."""
    if state.get("use_web", False) and not state.get("error"):
        return "web_agent"
    return "synthesis_agent"


# ── Graph construction ────────────────────────────────────────────────────────

def build_graph() -> StateGraph:
    """Assemble and compile the full agent workflow."""
    graph = StateGraph(AgentState)

    graph.add_node("research_agent", research_agent)
    graph.add_node("web_agent", web_agent)
    graph.add_node("synthesis_agent", synthesis_agent)

    graph.set_entry_point("research_agent")

    graph.add_conditional_edges(
        "research_agent",
        _route_after_research,
        {
            "web_agent": "web_agent",
            "synthesis_agent": "synthesis_agent",
        },
    )
    graph.add_edge("web_agent", "synthesis_agent")
    graph.add_edge("synthesis_agent", END)

    # MemorySaver provides in-process checkpointing so multi-turn threads
    # accumulate context across calls within a single session.
    checkpointer = MemorySaver()
    return graph.compile(checkpointer=checkpointer)


# Module-level singleton — built once per process.
_graph = None


def get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph


# ── Public entry point ────────────────────────────────────────────────────────

def process_query(query: str, thread_id: str = "default") -> AgentState:
    """
    Validate *query*, enforce rate limiting, detect PII, run the full agent
    pipeline, and return the final state.

    Args:
        query:     Raw user input (will be validated and sanitised).
        thread_id: Conversation thread identifier — also used as the rate-limit
                   key so each UI session has its own independent quota.

    Returns:
        The final AgentState after all agents have run.

    Raises:
        ValueError:              If the query fails input validation.
        RateLimitExceededError:  If this thread has exhausted its request quota.
    """
    validated = validate_input(query)

    # ── Rate limiting ─────────────────────────────────────────────────────────
    # Raises RateLimitExceededError when the per-thread quota is exhausted.
    check_rate_limit(thread_id)

    # ── PII detection ─────────────────────────────────────────────────────────
    # Detect PII before any logging.  The original query is still used for
    # processing (anonymising it would destroy query semantics).  Only the
    # sanitised version is written to logs inside detect_and_anonymise().
    pii_result = detect_and_anonymise(validated)
    pii_metadata: dict = {
        "pii_detected": pii_result.has_pii,
        "pii_types": list(set(pii_result.detections)),
    }

    initial_state: AgentState = {
        "query": validated,
        "doc_results": [],
        "web_results": [],
        "synthesis": None,
        "sources": [],
        "confidence": 0.0,
        "use_web": False,
        "error": None,
        "metadata": pii_metadata,
    }

    config = {"configurable": {"thread_id": thread_id}}

    # ── OpenTelemetry tracing ─────────────────────────────────────────────────
    tracer = get_tracer()
    with tracer.start_as_current_span("process_query") as span:
        span.set_attribute("query.length", len(validated))
        span.set_attribute("thread.id", thread_id)
        span.set_attribute("pii.detected", pii_result.has_pii)

        result = get_graph().invoke(initial_state, config=config)

        span.set_attribute("confidence", result.get("confidence", 0.0))
        span.set_attribute("use_web", result.get("use_web", False))
        span.set_attribute("doc.count", len(result.get("doc_results", [])))
        span.set_attribute("web.count", len(result.get("web_results", [])))
        if result.get("error"):
            span.set_status(Status(StatusCode.ERROR, result["error"]))
        else:
            span.set_status(Status(StatusCode.OK))

    return result

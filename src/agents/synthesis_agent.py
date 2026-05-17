"""
Synthesis Agent
===============
LangGraph node that combines document and web search results into a
single, coherent, source-attributed answer.

Pipeline:
  1. Format doc_results and web_results into readable context blocks.
  2. Generate a grounded answer with inline citations.
  3. Run a lightweight hallucination check and flag uncertain claims.
  4. Collect structured source metadata for UI display.
"""
import logging
from pathlib import Path
from typing import Any, Dict, List

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_groq import ChatGroq
from opentelemetry.trace import Status, StatusCode

from src.config import GROQ_API_KEY, GROQ_MODEL
from src.observability.telemetry import get_tracer
from src.state import AgentState

logger = logging.getLogger(__name__)

_SYNTHESIS_PROMPT = ChatPromptTemplate.from_template(
    "You are a knowledgeable personal assistant synthesising information "
    "from multiple sources to answer a user question.\n\n"
    "User Question: {query}\n\n"
    "=== Personal Knowledge Base ===\n{doc_context}\n\n"
    "=== Web Search Results ===\n{web_context}\n\n"
    "Guidelines:\n"
    "1. Answer the question comprehensively. Prioritise personal documents "
    "   when they are relevant.\n"
    "2. Cite sources inline: use [Doc: <filename>] for documents and "
    "   [Web] for web results.\n"
    "3. If information may be outdated or uncertain, flag it explicitly.\n"
    "4. Structure the response clearly (use bullet points or headers where "
    "   appropriate).\n"
    "5. If no relevant information was found in either source, say so "
    "   honestly rather than speculating.\n\n"
    "Answer:"
)

_HALLUCINATION_PROMPT = ChatPromptTemplate.from_template(
    "You are a fact-checking assistant.\n\n"
    "Available source material:\n{sources}\n\n"
    "Answer to verify:\n{answer}\n\n"
    "Check whether every claim in the answer is supported by the source "
    "material above.\n"
    "Respond with exactly one of:\n"
    "  VERIFIED — all claims are grounded in the sources.\n"
    "  UNVERIFIED: <specific unsupported claim(s)>"
)


def _get_llm() -> ChatGroq:
    """Instantiate the Groq LLM (extracted for easy test mocking)."""
    return ChatGroq(api_key=GROQ_API_KEY, model=GROQ_MODEL, temperature=0.3)


def _format_doc_context(doc_results: List[Dict[str, Any]]) -> str:
    if not doc_results:
        return "No relevant documents found in the personal knowledge base."
    parts = []
    for i, r in enumerate(doc_results, start=1):
        filename = Path(r.get("source", "unknown")).name
        score = r.get("score", 0.0)
        parts.append(f"[Doc {i} | {filename} | relevance: {score:.2f}]\n{r['content']}")
    return "\n\n".join(parts)


def _format_web_context(web_results: List[Dict[str, Any]]) -> str:
    if not web_results:
        return "No web search was performed."
    return "\n\n".join(r.get("content", "") for r in web_results)


def _collect_sources(
    doc_results: List[Dict[str, Any]],
    web_results: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    sources: List[Dict[str, Any]] = []
    for r in doc_results:
        sources.append(
            {
                "type": "document",
                "source": r.get("source", "unknown"),
                "score": r.get("score", 0.0),
            }
        )
    for r in web_results:
        sources.append(
            {
                "type": "web",
                "source": r.get("url", "unknown"),
                "title": r.get("title", ""),
            }
        )
    return sources


def synthesis_agent(state: AgentState) -> AgentState:
    """
    Synthesis node: merges doc and web results into a cited, grounded answer.

    Writes to state:
      synthesis — the final answer string
      sources   — structured list of document and web sources used
    """
    query: str = state["query"]
    doc_results = state.get("doc_results", [])
    web_results = state.get("web_results", [])

    logger.info(
        "[Synthesis Agent] Synthesising from %d docs + %d web results",
        len(doc_results),
        len(web_results),
    )

    doc_context = _format_doc_context(doc_results)
    web_context = _format_web_context(web_results)
    sources = _collect_sources(doc_results, web_results)

    llm = _get_llm()

    tracer = get_tracer()
    with tracer.start_as_current_span("synthesis_agent") as span:
        span.set_attribute("agent.name", "synthesis_agent")
        span.set_attribute("query.length", len(query))
        span.set_attribute("doc.count", len(doc_results))
        span.set_attribute("web.count", len(web_results))

        # ── Step 1: Generate answer ───────────────────────────────────────────
        try:
            synthesis_chain = _SYNTHESIS_PROMPT | llm | StrOutputParser()
            answer: str = synthesis_chain.invoke(
                {
                    "query": query,
                    "doc_context": doc_context,
                    "web_context": web_context,
                }
            )
        except Exception as exc:
            logger.error("[Synthesis Agent] Synthesis failed: %s", exc)
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            return {
                **state,
                "synthesis": f"Error generating response: {exc}",
                "sources": sources,
            }

        # ── Step 2: Hallucination check ───────────────────────────────────────
        try:
            combined_sources = f"{doc_context}\n\n{web_context}"
            check_chain = _HALLUCINATION_PROMPT | llm | StrOutputParser()
            verdict: str = check_chain.invoke(
                {"sources": combined_sources, "answer": answer}
            )
            if verdict.startswith("UNVERIFIED"):
                logger.warning("[Synthesis Agent] Hallucination flag: %s", verdict)
                answer = f"{answer}\n\n> ⚠️ Verification note: {verdict}"
        except Exception as exc:
            # Non-critical: continue without the check
            logger.warning("[Synthesis Agent] Hallucination check skipped: %s", exc)

        span.set_attribute("answer.length", len(answer))
        span.set_status(Status(StatusCode.OK))

        logger.info("[Synthesis Agent] Complete")
        return {**state, "synthesis": answer, "sources": sources}

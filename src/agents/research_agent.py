"""
Research Agent
==============
LangGraph node responsible for retrieving relevant context from the
personal knowledge base stored in Qdrant.

Pipeline:
  1. Reformulate the user query for better vector-search recall.
  2. Perform cosine-similarity search in Qdrant.
  3. Compute a confidence score from the top result.
  4. Flag whether the web agent should run as a fallback.
"""
import logging

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from opentelemetry.trace import Status, StatusCode

from src.config import CONFIDENCE_THRESHOLD, OPENAI_API_KEY, OPENAI_MODEL
from src.observability.telemetry import get_tracer
from src.rag.vector_store import VectorStore
from src.state import AgentState

logger = logging.getLogger(__name__)

_REFORMULATE_PROMPT = ChatPromptTemplate.from_template(
    "You are a search-query optimisation expert.\n"
    "Rewrite the user question as a concise, keyword-rich search query "
    "for a vector database of personal knowledge documents.\n\n"
    "User question: {query}\n\n"
    "Respond with ONLY the improved search query — no explanation, no quotes."
)


def _get_llm() -> ChatOpenAI:
    """Instantiate the OpenAI LLM (extracted for easy test mocking)."""
    return ChatOpenAI(api_key=OPENAI_API_KEY, model=OPENAI_MODEL, temperature=0)


def research_agent(state: AgentState) -> AgentState:
    """
    RAG node: retrieves relevant document chunks from the personal knowledge base.

    Writes to state:
      doc_results  — list of DocumentResult dicts
      confidence   — top similarity score (0.0 if no results)
      use_web      — True when confidence < threshold or no results found
    """
    query: str = state["query"]
    logger.info("[Research Agent] Query: %.80s", query)

    tracer = get_tracer()
    with tracer.start_as_current_span("research_agent") as span:
        span.set_attribute("agent.name", "research_agent")
        span.set_attribute("query.length", len(query))

        # ── Step 1: Reformulate query ─────────────────────────────────────────
        try:
            llm = _get_llm()
            chain = _REFORMULATE_PROMPT | llm | StrOutputParser()
            search_query: str = chain.invoke({"query": query})
            logger.info("[Research Agent] Reformulated query: %.80s", search_query)
        except Exception as exc:
            logger.warning("[Research Agent] Reformulation failed, using original: %s", exc)
            search_query = query

        # ── Step 2: Vector similarity search ─────────────────────────────────
        try:
            vs = VectorStore()
            doc_results = vs.similarity_search(search_query)
        except Exception as exc:
            logger.error("[Research Agent] Vector search failed: %s", exc)
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            return {
                **state,
                "doc_results": [],
                "confidence": 0.0,
                "use_web": True,
                "error": f"Document search failed: {exc}",
            }

        # ── Step 3: Confidence scoring ────────────────────────────────────────
        confidence: float = doc_results[0]["score"] if doc_results else 0.0
        use_web: bool = confidence < CONFIDENCE_THRESHOLD or not doc_results

        logger.info(
            "[Research Agent] Found %d results | top score=%.2f | use_web=%s",
            len(doc_results),
            confidence,
            use_web,
        )

        span.set_attribute("doc.count", len(doc_results))
        span.set_attribute("rag.confidence", confidence)
        span.set_attribute("use_web", use_web)
        span.set_status(Status(StatusCode.OK))

        return {
            **state,
            "doc_results": doc_results,
            "confidence": confidence,
            "use_web": use_web,
        }

"""
Web Agent
=========
LangGraph node that performs live web searches via the Tavily MCP server.

The agent is only invoked when the Research Agent signals low confidence
(use_web=True). It spawns the Tavily MCP server as a subprocess over stdio,
uses langchain-mcp-adapters to call the search tool, then summarises the
raw results with an LLM.

MCP transport: stdio (subprocess)
MCP server:    src/mcp/tavily_mcp.py
"""
import asyncio
import logging
import os
import sys
from pathlib import Path

import nest_asyncio
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langchain_mcp_adapters.client import MultiServerMCPClient
from opentelemetry.trace import Status, StatusCode

from src.config import OPENAI_API_KEY, OPENAI_MODEL, MAX_WEB_RESULTS
from src.observability.telemetry import get_tracer
from src.state import AgentState

logger = logging.getLogger(__name__)

# Absolute path to the MCP server script
_MCP_SERVER_PATH = str(Path(__file__).parent.parent / "mcp" / "tavily_mcp.py")

_SUMMARISE_PROMPT = ChatPromptTemplate.from_template(
    "You are a research assistant processing web search results.\n\n"
    "Original question: {query}\n\n"
    "Raw search results:\n{raw_results}\n\n"
    "Summarise the most relevant facts in clear, concise bullet points. "
    "Include source URLs inline as [source](url). Be factual and brief."
)


def _get_llm() -> ChatOpenAI:
    """Instantiate the OpenAI LLM (extracted for easy test mocking)."""
    return ChatOpenAI(api_key=OPENAI_API_KEY, model=OPENAI_MODEL, temperature=0.2)


async def _call_tavily_mcp(query: str) -> str:
    """
    Spawn the Tavily MCP server and invoke the tavily_search tool.
    Returns the raw tool output as a string.
    """
    async with MultiServerMCPClient(
        {
            "tavily": {
                "command": sys.executable,
                "args": [_MCP_SERVER_PATH],
                "transport": "stdio",
                # Forward all env vars so the child process sees TAVILY_API_KEY
                "env": {**os.environ},
            }
        }
    ) as client:
        tools = client.get_tools()
        tavily_tool = next(
            (t for t in tools if t.name == "tavily_search"), None
        )
        if tavily_tool is None:
            raise RuntimeError(
                "tavily_search tool not advertised by MCP server. "
                "Check src/mcp/tavily_mcp.py."
            )
        result = await tavily_tool.ainvoke(
            {"query": query, "max_results": MAX_WEB_RESULTS}
        )
        return str(result)


def web_agent(state: AgentState) -> AgentState:
    """
    Web search node: only runs when research_agent sets use_web=True.

    Writes to state:
      web_results — list of WebResult dicts with summarised content
    """
    if not state.get("use_web", False):
        logger.info("[Web Agent] Skipping — not needed (confidence sufficient)")
        return state

    query: str = state["query"]
    logger.info("[Web Agent] Searching web for: %.80s", query)

    tracer = get_tracer()
    with tracer.start_as_current_span("web_agent") as span:
        span.set_attribute("agent.name", "web_agent")
        span.set_attribute("query.length", len(query))

        # ── MCP call (async → sync bridge) ───────────────────────────────────
        try:
            # nest_asyncio allows asyncio.run() inside environments that already
            # have a running loop (e.g. Jupyter, some test runners).
            nest_asyncio.apply()
            loop = asyncio.get_event_loop()
            raw_results: str = loop.run_until_complete(_call_tavily_mcp(query))
        except Exception as exc:
            logger.error("[Web Agent] MCP search failed: %s", exc)
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            return {**state, "web_results": [], "error": f"Web search failed: {exc}"}

        # ── Summarise with LLM ────────────────────────────────────────────────
        try:
            llm = _get_llm()
            summary_chain = _SUMMARISE_PROMPT | llm | StrOutputParser()
            summary: str = summary_chain.invoke(
                {"query": query, "raw_results": raw_results}
            )
        except Exception as exc:
            logger.warning("[Web Agent] LLM summarisation failed, using raw output: %s", exc)
            summary = raw_results

        web_results = [
            {
                "content": summary,
                "url": "https://tavily.com",
                "title": "Web Search Results (Tavily)",
                "published_date": None,
            }
        ]

        span.set_attribute("web.result_count", len(web_results))
        span.set_status(Status(StatusCode.OK))

        logger.info("[Web Agent] Web search complete")
        return {**state, "web_results": web_results}

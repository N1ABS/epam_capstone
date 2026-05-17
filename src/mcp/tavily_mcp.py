"""
Tavily Search MCP Server
========================
An MCP (Model Context Protocol) server that exposes Tavily's AI-powered
web search as a tool consumable by any MCP-compatible client.

Transport: stdio (suitable for subprocess spawning from the web agent).

Run standalone for testing:
    python -m src.mcp.tavily_mcp
"""
import asyncio
import logging
import os

from mcp import types
from mcp.server import Server
from mcp.server.stdio import stdio_server
from tavily import TavilyClient

logger = logging.getLogger(__name__)

# ── Server instance ───────────────────────────────────────────────────────────
app = Server("tavily-search-mcp")

# Lazy-initialised Tavily client (avoids import-time env var requirement)
_tavily_client: TavilyClient | None = None


def _get_tavily() -> TavilyClient:
    global _tavily_client
    if _tavily_client is None:
        api_key = os.getenv("TAVILY_API_KEY", "")
        if not api_key:
            raise EnvironmentError(
                "TAVILY_API_KEY is not set. "
                "Obtain a free key at https://app.tavily.com/ and add it to .env"
            )
        _tavily_client = TavilyClient(api_key=api_key)
    return _tavily_client


# ── Tool definitions ──────────────────────────────────────────────────────────

@app.list_tools()
async def list_tools() -> list[types.Tool]:
    """Advertise available tools to the MCP client."""
    return [
        types.Tool(
            name="tavily_search",
            description=(
                "Search the web for current, factual information using the "
                "Tavily AI search engine. Returns structured results with "
                "titles, URLs, snippets, and an AI-generated answer summary."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query.",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Number of results to return (1–10). Default 5.",
                        "default": 5,
                        "minimum": 1,
                        "maximum": 10,
                    },
                    "search_depth": {
                        "type": "string",
                        "description": "'basic' (fast) or 'advanced' (thorough). Default 'basic'.",
                        "enum": ["basic", "advanced"],
                        "default": "basic",
                    },
                },
                "required": ["query"],
            },
        )
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    """Handle a tool call from the MCP client."""
    if name != "tavily_search":
        raise ValueError(f"Unknown tool: '{name}'")

    query: str = arguments.get("query", "").strip()
    if not query:
        raise ValueError("'query' argument must not be empty")

    max_results: int = min(int(arguments.get("max_results", 5)), 10)
    search_depth: str = arguments.get("search_depth", "basic")

    client = _get_tavily()
    response = client.search(
        query=query,
        max_results=max_results,
        search_depth=search_depth,
        include_answer=True,
        include_raw_content=False,
    )

    # ── Format as structured plain-text for the LLM ──────────────────────────
    lines: list[str] = []

    if response.get("answer"):
        lines.append(f"AI Summary: {response['answer']}\n")

    for i, result in enumerate(response.get("results", []), start=1):
        title = result.get("title", "No title")
        url = result.get("url", "")
        content = result.get("content", "")
        published = result.get("published_date", "")
        date_str = f" ({published})" if published else ""
        lines.append(f"[{i}] {title}{date_str}\nURL: {url}\n{content}\n")

    output = "\n".join(lines) if lines else "No results found."
    return [types.TextContent(type="text", text=output)]


# ── Entrypoint ────────────────────────────────────────────────────────────────

async def _serve() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options(),
        )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(_serve())

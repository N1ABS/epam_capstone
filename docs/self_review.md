# Self-Review — Personal Knowledge Assistant

**Author:** Nurbolat Absagat  
**Date:** May 18, 2026  
**Audience:** Exam committee, code reviewers

---

## Purpose of This Document

This self-review walks through the key architectural decisions, code choices, and trade-offs made during the implementation of the Personal Knowledge Assistant.  
The goal is not to re-describe the system (see `architecture_blueprint.md` for that), but to reflect on **why** things were built the way they were and what I would do differently given more time.

---

## 1. Why LangGraph Over Other Agent Frameworks

### Decision
I chose **LangGraph** as the orchestration layer rather than CrewAI, AutoGen, or a hand-rolled pipeline.

### Reasoning
LangGraph forces you to define a **typed `AgentState`** that flows through every node. This made a significant practical difference:

- Every agent receives a dict it can inspect and return a modified copy of — there is no hidden shared mutable state.
- The routing logic (`_route_after_research`) is a pure function that takes a state and returns a string. This made it trivially testable without mocking any infrastructure.
- LangSmith traces are produced automatically per-node, including inputs, outputs, token counts, and latency, with zero extra instrumentation code.

CrewAI was tempting because it requires less boilerplate, but its role-based abstraction obscures the data flow. I wanted the committee to be able to follow exactly which data enters and exits each agent — the typed state makes that explicit.

### Trade-off
LangGraph is more verbose than CrewAI. Defining `AgentState` and wiring `add_conditional_edges` takes more code than CrewAI's decorator-based role assignment. For a project of this scale that verbosity is worth it for clarity and testability; for a larger project with 10+ agents, the boilerplate would accumulate.

---

## 2. The Typed `AgentState` as Architecture Contract

### Decision
All inter-agent communication goes through `src/state.py` — a single `AgentState` TypedDict. No agent calls another agent directly. No agent writes to a database or global variable during its run.

### Reasoning
This pattern came from thinking about **testability first**. If agents communicate only through a dict, then a test for the Research Agent needs nothing more than a dict in and a dict out — no live Qdrant, no LLM, no other agents. That is why the test suite can mock `VectorStore` and `_get_llm` in isolation without spinning up the full graph.

```python
# From src/state.py — the contract every agent must honour
class AgentState(TypedDict):
    query: str
    doc_results: List[DocumentResult]
    web_results: List[WebResult]
    synthesis: Optional[str]
    sources: List[Dict[str, Any]]
    confidence: float
    use_web: bool
    error: Optional[str]
    metadata: Dict[str, Any]
```

The `error` field deserves special mention. Rather than letting an exception propagate and kill the pipeline, each agent catches failures and writes to `error`. The routing function (`_route_after_research`) checks this field: if research errored, the web agent is skipped to prevent a cascading double-failure, and the Synthesis Agent receives an empty context and produces a graceful "no information found" response.

### Trade-off
TypedDict is not enforced at runtime in Python — a badly-behaved agent could silently drop a key and the downstream agent would get a `KeyError`. In production I would add a Pydantic model with validators. For this project the typed hints plus the test suite provide sufficient safety.

---

## 3. MCP Integration: Real Protocol vs. Wrapper

### Decision
I implemented `src/mcp/tavily_mcp.py` as a genuine MCP server using the `mcp` SDK with `stdio_server`, rather than writing a thin wrapper that calls Tavily and pretends to be MCP.

### Reasoning
The MCP specification exists for a reason: a real MCP server can be called by any MCP-compatible client — not just this project's Web Agent. By implementing the full `list_tools` / `call_tool` handlers, the server is genuinely interoperable. The Web Agent uses `langchain-mcp-adapters`'s `MultiServerMCPClient` to discover and invoke the tool dynamically, which is architecturally correct — the agent does not hard-code the Tavily API call; it asks the MCP server what tools are available and then invokes them.

```python
# From src/agents/web_agent.py — the agent discovers the tool at runtime
tools = client.get_tools()
tavily_tool = next((t for t in tools if t.name == "tavily_search"), None)
result = await tavily_tool.ainvoke({"query": query, "max_results": MAX_WEB_RESULTS})
```

I chose the **stdio transport** over SSE because stdio requires no separate running service — the MCP server is spawned as a child process on demand and exits when the search completes. This keeps the entire application launchable with a single `streamlit run ui/app.py` command, which is essential for a demo environment.

### Trade-off
stdio transport is a point-to-point connection. Every Web Agent invocation spawns and tears down a Python subprocess, which adds ~200–400 ms of startup latency. For a production deployment where multiple users share one MCP server instance, SSE transport would be the right choice. I documented this explicitly in the architecture blueprint and in the code comments.

---

## 4. Security Architecture: Why Each Control Exists

### Decision
I implemented four distinct security controls in `src/security/`: input validation (in `orchestrator.py`), PII detection, rate limiting, and session authentication.

### Reasoning

**Input validation and injection blocking** (`orchestrator.py` → `validate_input`): The system routes user input into LLM prompts. Prompt injection — where a user's query tries to override the system instructions — is a real attack class for RAG systems. I compiled 10 regex patterns covering the most common injection phrases. The patterns use `re.IGNORECASE` to catch case variants. This runs before any agent is invoked, so an injected query never reaches the LLM.

**PII detection** (`src/security/pii_detector.py`): User queries may contain personal data (emails, phone numbers, SSNs). The system logs queries for debugging; raw PII in logs is a compliance risk. The PII detector produces a `PIIResult` with both the `original` query (used for processing, so semantics are preserved) and a `sanitised` copy (used for logging). This is a pragmatic design — anonymising the query before the LLM would destroy meaning.

**Rate limiting** (`src/security/rate_limiter.py`): The system uses OpenAI's API and Tavily's free tier (limited requests per month). An unthrottled UI would let a single user exhaust the API quota in minutes. The sliding-window implementation uses a `deque` per `thread_id` protected by a `threading.Lock`, which is correct for Streamlit's multi-threaded execution model.

**Authentication** (`src/security/auth.py`): The SHA-256 hash and `hmac.compare_digest` for constant-time comparison are standard practice to prevent timing-based enumeration of valid usernames. The `secrets.token_hex(32)` session token provides 256 bits of entropy. This is disabled by default (`AUTH_ENABLED=false`) to simplify local development.

### Trade-off
The authentication uses SHA-256 rather than bcrypt/argon2. SHA-256 is fast, which is a weakness for offline brute-force attacks against the stored hash. For a capstone demo with a single user this is acceptable; a production system would use `bcrypt` or `argon2-cffi`.

---

## 5. Hallucination Check: Two LLM Calls in Synthesis

### Decision
The Synthesis Agent makes **two LLM calls**: one to generate the answer and a second to verify every claim against the retrieved sources.

### Reasoning
A single-pass RAG answer can confidently assert things not present in the retrieved documents, especially when the LLM's parametric knowledge fills gaps. The second pass (`_HALLUCINATION_PROMPT`) asks the LLM to check whether every claim in the answer is supported by the source material and returns either `VERIFIED` or `UNVERIFIED: <specific claim>`. When unverified, the answer gets a `⚠️ Verification note` appended.

This is a lightweight self-consistency check — it doesn't guarantee factual accuracy, but it catches the most obvious cases where the LLM has gone off-script from the provided context.

### Trade-off
The second LLM call adds ~1–2 seconds to the synthesis step (empirically ~30–50% of total synthesis latency). In a higher-traffic production system I would move this to an asynchronous background check or replace it with an embedding-similarity check (compare each sentence's embedding to the source embeddings) which is cheaper and faster. I noted this trade-off explicitly in the executive summary under "Lessons Learned".

---

## 6. Embeddings: Local Model Over API

### Decision
I used `sentence-transformers/all-MiniLM-L6-v2` running locally on CPU, rather than OpenAI's `text-embedding-3-small` or a hosted service.

### Reasoning
The choice has three drivers:
1. **Cost**: Zero API cost for any number of embeddings.
2. **Privacy**: Document content never leaves the machine during embedding — important for personal or proprietary documents.
3. **Latency**: The model is loaded once into memory via `@lru_cache(maxsize=1)` and then runs at ~20–50 ms per batch on CPU, which is faster than a round-trip to an embedding API for short texts.

The quality trade-off is real: `all-MiniLM-L6-v2` (384 dimensions) is less capable than `text-embedding-3-large` (3072 dimensions) for subtle semantic similarity tasks. However, for the domain-specific document corpus in this project (technical notes, markdown files) the difference is negligible.

### Trade-off
The first request after startup incurs a ~2–5 second model load. I mitigated this with `lru_cache` but not with eager loading — the model loads on first use, not at application start. Eager loading (calling `embed_query("")` during startup) would make the first real query instantaneous; I chose lazy loading to keep startup time fast for demo purposes.

---

## 7. Test Strategy: Why Mocking Over Integration Tests

### Decision
All agent tests mock the LLM and vector store rather than running live API calls.

### Reasoning
Integration tests that call real APIs are fragile in a CI/CD context: they require secrets, they consume rate-limited quotas, they fail intermittently on network issues, and they are slow. The goal of the test suite is to validate **LLM behaviour and routing logic** — not to test that OpenAI's API is available.

LangChain's `FakeListChatModel` returns pre-defined responses, making tests deterministic. For the Research Agent, I mock `VectorStore.similarity_search` to return specific scores, which lets me test the confidence threshold routing precisely:

```python
# From tests/test_research_agent.py — testing the threshold without live Qdrant
MockVS.return_value = _mock_vs(
    [{"content": "ML is AI", "source": "/docs/ml.md", "score": 0.9, "metadata": {}}]
)
result = research_agent(_make_state())
assert result["use_web"] is False  # 0.9 >= 0.6 threshold
```

Edge cases that cannot be tested with live infrastructure — like the vector database going down mid-query — are straightforward to test by having the mock raise an exception.

### Trade-off
The test suite does not prove the system works end-to-end with real API keys. A small set of smoke tests that run against live APIs would complement the unit suite, but I excluded them to avoid requiring API keys in CI and to keep test execution instantaneous.

---

## 8. What I Would Do Differently

| Area | What I did | What I'd change with more time |
|---|---|---|
| Authentication | SHA-256 password hash | Replace with `argon2-cffi` for brute-force resistance |
| Embeddings loading | Lazy load on first query | Eager-load at startup to eliminate first-query latency |
| User feedback | Toast-only 👍/👎 | Persist ratings to a SQLite log for quality monitoring |
| Sample data | 3 small markdown files | Curate a 20–50 document corpus with diverse formats |
| Bias detection | Not implemented | Add embedding-based bias check comparing answer tone across demographic terms |
| MCP transport | stdio subprocess | SSE transport for multi-user production deployment |
| Hallucination check | Synchronous second LLM call | Make asynchronous or replace with embedding similarity |

---

## 9. Lessons Learned

1. **Typed state is a debugging superpower.** When something went wrong during development, I could print the state dict at any node and immediately see exactly what each agent had written. With a framework that hides state internally, debugging would have taken much longer.

2. **Security controls are cheapest to add early.** I built the security module before the agents were complete. Adding rate limiting and PII detection after the fact would have required touching the orchestrator, UI, and all tests. Doing it upfront meant the test fixtures were written with security in mind from the start.

3. **MCP is simpler than its reputation suggests.** The `mcp` SDK handles all the protocol framing; implementing `list_tools` and `call_tool` handlers takes fewer than 60 lines of code. The complexity is in the async subprocess bridging, not the protocol itself.

4. **Provider flexibility pays off.** Because all LLM configuration (API key, model,
   base URL) is in environment variables, switching providers requires zero code
   changes. The confidence threshold is a first-class citizen of the architecture:
   avoiding unnecessary web calls reduces both latency and API spend.

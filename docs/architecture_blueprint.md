# Architecture Blueprint — Personal Knowledge Assistant

**Version:** 1.0  
**Date:** May 2026

---

## 1. System Overview

The Personal Knowledge Assistant (PKA) is a multi-agent RAG system that answers
user questions by first searching a personal document corpus and falling back to
live web search when local knowledge is insufficient.

```
┌────────────────────────────────────────────────────────────────────┐
│                         Streamlit UI (ui/app.py)                   │
│  Auth Gate → validate_input → process_query → render answer + sources │
└───────────────────────────┬────────────────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────────────────┐
│              Orchestrator — LangGraph StateGraph                    │
│                                                                    │
│  ┌─────────────────┐   confidence ≥ 0.60   ┌───────────────────┐  │
│  │  Research Agent │ ────────────────────► │ Synthesis Agent   │  │
│  │  (RAG / Qdrant) │                        │ (grounded answer  │  │
│  └─────────────────┘   confidence < 0.60   │  + hallucination  │  │
│          │             ────────────────►    │    check)         │  │
│          │                    ▲             └───────────────────┘  │
│          ▼                    │                                    │
│  ┌─────────────────┐          │                                    │
│  │   Web Agent     │ ─────────┘                                    │
│  │  (Tavily MCP)   │                                               │
│  └─────────────────┘                                               │
└────────────────────────────────────────────────────────────────────┘
```

---

## 2. Agent Roles and Responsibilities

### 2.1 Research Agent (`src/agents/research_agent.py`)

| Attribute | Detail |
|---|---|
| **Input** | `AgentState.query` |
| **Output** | `doc_results`, `confidence`, `use_web` |
| **Tools** | Qdrant vector store, Groq LLM (query reformulation) |

**Pipeline:**
1. Rewrites the user query into a keyword-rich search query using the LLM.
2. Performs cosine-similarity search in Qdrant (top-K chunks).
3. Sets `confidence` to the top result's similarity score (0.0 if no results).
4. Sets `use_web = True` when confidence < `CONFIDENCE_THRESHOLD`.

### 2.2 Web Agent (`src/agents/web_agent.py`)

| Attribute | Detail |
|---|---|
| **Input** | `AgentState.query`, `AgentState.use_web` |
| **Output** | `web_results` |
| **Tools** | Tavily MCP server (stdio subprocess), Groq LLM (summarisation) |
| **Condition** | Runs only when `use_web = True` |

**Pipeline:**
1. Spawns the Tavily MCP server as a stdio subprocess.
2. Invokes the `tavily_search` MCP tool via `langchain-mcp-adapters`.
3. Summarises raw results into bullet-point format using the LLM.

### 2.3 Synthesis Agent (`src/agents/synthesis_agent.py`)

| Attribute | Detail |
|---|---|
| **Input** | `AgentState.doc_results`, `AgentState.web_results` |
| **Output** | `synthesis`, `sources` |
| **Tools** | Groq LLM (answer generation + hallucination check) |

**Pipeline:**
1. Formats document and web context into readable blocks.
2. Generates a grounded answer with inline `[Doc: filename]` / `[Web]` citations.
3. Runs a second LLM call to verify every claim is grounded in the sources.
4. Appends a `⚠️ Verification note` to the answer when claims are unverified.

---

## 3. Shared State

All agents communicate exclusively through a typed `AgentState` TypedDict
(`src/state.py`).  No agent calls another directly.

```
AgentState
├── query          str          — validated user question
├── doc_results    List[DocumentResult]
│   └── {content, source, score, metadata}
├── web_results    List[WebResult]
│   └── {content, url, title, published_date}
├── synthesis      Optional[str]   — final answer
├── sources        List[Dict]      — structured source list for UI
├── confidence     float           — top document similarity score
├── use_web        bool            — trigger for web agent
├── error          Optional[str]   — last agent error (non-fatal)
└── metadata       Dict            — pii_detected, pii_types, etc.
```

---

## 4. Data Flow

```
User input
    │
    ▼ validate_input() — length, injection patterns
    │
    ▼ check_rate_limit() — sliding-window per thread_id
    │
    ▼ detect_and_anonymise() — PII flagged; logs use sanitised copy
    │
    ▼ Research Agent
    │   ├─ Groq LLM: query reformulation
    │   └─ Qdrant: cosine-similarity search → doc_results, confidence
    │
    ├─ confidence ≥ 0.60 ────────────────────────────────────┐
    │                                                        │
    └─ confidence < 0.60                                     │
            │                                               │
            ▼                                               │
        Web Agent                                           │
            ├─ Tavily MCP server (stdio)                    │
            └─ Groq LLM: result summarisation → web_results │
                    │                                       │
                    └───────────────────────────────────────┤
                                                            │
                                                            ▼
                                                   Synthesis Agent
                                                       ├─ Groq LLM: answer generation
                                                       └─ Groq LLM: hallucination check
                                                                │
                                                                ▼
                                                         Final answer + sources
```

---

## 5. Technology Stack

| Concern | Technology | Version | Rationale |
|---|---|---|---|
| Agent orchestration | LangGraph | ≥0.2 | Typed state graph, MemorySaver checkpointing, LangSmith tracing |
| Primary LLM | Groq (`llama-3.3-70b-versatile`) | ≥0.11 | Free tier, 100+ tok/s, OpenAI-compatible |
| Local LLM fallback | Ollama (`llama3.2`) | — | Zero cost, offline, no data egress |
| Vector database | Qdrant | ≥1.9 | Local Docker, cosine similarity, no cloud dependency |
| Embeddings | `sentence-transformers/all-MiniLM-L6-v2` | ≥3.0 | CPU-efficient, free, 384-dim, offline |
| Document processing | PyMuPDF4LLM + LangChain loaders | ≥0.0.17 | GNN-based PDF extraction, multi-format support |
| Web search (MCP) | Tavily API | ≥0.3 | Structured results, free tier, agent-optimised |
| MCP protocol | `mcp` + `langchain-mcp-adapters` | ≥1.0 | stdio transport, no extra HTTP server needed |
| Observability | LangSmith + OpenTelemetry SDK | ≥0.1 / ≥1.25 | LangGraph-native traces + vendor-neutral OTLP spans |
| UI | Streamlit | ≥1.38 | Rapid development, file upload, streaming, free deploy |
| Testing | pytest | ≥8.0 | Unit + LLM behaviour validation, mocking |

---

## 6. MCP Integration

The Tavily web-search capability is exposed as an MCP server
(`src/mcp/tavily_mcp.py`) using the `stdio` transport.

```
Web Agent process
    │
    │  subprocess.Popen(["python", "src/mcp/tavily_mcp.py"])
    │
    ▼
Tavily MCP Server (src/mcp/tavily_mcp.py)
    │  tools: [tavily_search]
    │  inputSchema: {query, max_results, search_depth}
    │
    ▼
Tavily REST API (external)
    │
    ▼
Structured results (title, URL, snippet, AI summary)
```

**Why stdio over SSE:**  stdio requires no separate running service; the MCP
server is spawned as a child process on demand and exits when the search
completes.  SSE transport would be preferred for a multi-user production
deployment where the server is shared across concurrent sessions.

---

## 7. Security Architecture

| Control | Implementation |
|---|---|
| **Input validation** | `validate_input()` in `orchestrator.py` — strips whitespace, enforces 2 000-char limit, regex-blocks 10 prompt-injection patterns |
| **Rate limiting** | `src/security/rate_limiter.py` — sliding-window per `thread_id` (default: 10 req / 60 s), thread-safe with `threading.Lock` |
| **PII detection** | `src/security/pii_detector.py` — regex detection for EMAIL, PHONE, SSN, IP; anonymised copy used in logs; raw query used for processing |
| **Authentication** | `src/security/auth.py` — SHA-256 password hashing, `hmac.compare_digest` constant-time comparison, `secrets.token_hex(32)` session tokens |
| **Content filtering** | Synthesis Agent prompt instructs the LLM to flag uncertainty; hallucination check validates claims against sources |
| **Secret management** | All API keys in `.env` (gitignored); `.env.example` ships no secrets |
| **Dependency integrity** | `requirements.txt` pins major versions |

---

## 8. Observability Architecture

```
Agent invocation
    │
    ├─ LangSmith trace (if LANGCHAIN_TRACING_V2=true)
    │   └─ per-node inputs / outputs, token counts, latency
    │
    └─ OpenTelemetry span (src/observability/telemetry.py)
        ├─ process_query span: query.length, thread.id, pii.detected,
        │                       confidence, use_web, doc.count, web.count
        ├─ research_agent span: doc.count, rag.confidence, use_web
        ├─ web_agent span:      web.result_count
        └─ synthesis_agent span: doc.count, web.count, answer.length
```

**Exporter options (env-configured, no code change required):**

| Variable | Effect |
|---|---|
| `OTEL_CONSOLE_EXPORT=true` | Prints spans to stdout (local debugging) |
| `OTEL_EXPORTER_OTLP_ENDPOINT=http://host:4317` | Sends spans to Jaeger / Tempo / Honeycomb |
| Neither set | No-op exporter — application runs normally without telemetry infra |

---

## 9. RAG Pipeline Detail

```
Document ingest (one-time or on upload)
    │
    ├─ load_document() — PDF (PyMuPDF4LLM), TXT, MD, DOCX
    ├─ split_documents() — RecursiveCharacterTextSplitter
    │   chunk_size=512, overlap=50
    └─ VectorStore.upsert_documents()
        ├─ embed_texts() — sentence-transformers (CPU, cached)
        └─ Qdrant.upsert() — cosine distance, deterministic IDs

Query path
    │
    ├─ Research Agent: reformulate → embed_query() → Qdrant.search()
    └─ score → confidence → routing decision
```

---

## 10. Infrastructure

```yaml
# docker-compose.yml
qdrant:
  image: qdrant/qdrant:latest
  ports: ["6333:6333", "6334:6334"]
  volumes: [qdrant_storage:/qdrant/storage]
  healthcheck: curl http://localhost:6333/health
```

No other infrastructure is required.  Everything else runs in the Python
process started by `streamlit run ui/app.py`.

---

## 11. Deployment

### Local (development)
```bash
docker compose up -d          # Qdrant
streamlit run ui/app.py       # Application
```

### Production considerations
- Replace `MemorySaver` with `langgraph-checkpoint-postgres` for multi-user persistence.
- Use Qdrant Cloud or a dedicated Qdrant instance for shared vector storage.
- Set `AUTH_ENABLED=true` and a strong `AUTH_PASSWORD_HASH`.
- Deploy Streamlit to Community Cloud or behind a reverse proxy with TLS.
- Configure `OTEL_EXPORTER_OTLP_ENDPOINT` to send spans to a hosted collector.

---

## 12. Key Architecture Trade-offs

| Decision | Alternative considered | Trade-off |
|---|---|---|
| LangGraph vs CrewAI | CrewAI | LangGraph gives explicit typed state and testable routing; CrewAI is simpler but harder to introspect |
| Qdrant vs ChromaDB | ChromaDB | Qdrant supports hybrid search and scales to production; ChromaDB has simpler local setup but no hybrid search |
| Local embeddings vs OpenAI | OpenAI embeddings | Local is free, private, and fast enough for this corpus size; OpenAI would cost ~$0.0001/1K tokens |
| Groq vs OpenAI LLM | OpenAI GPT-4o | Groq free tier is sufficient for demos; OpenAI offers stronger reasoning but at cost |
| stdio MCP vs SSE | SSE transport | stdio requires no extra server process; SSE needed for shared/multi-user deployments |
| MemorySaver vs DB checkpointer | PostgreSQL checkpointer | MemorySaver needs no dependencies; PostgreSQL needed for multi-user production |

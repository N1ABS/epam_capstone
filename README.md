# Personal Knowledge Assistant

A multi-agent RAG system that answers questions by searching your personal documents
first and falling back to live web search when needed.

```
User Query
    │
    ▼
┌──────────────────┐   high confidence    ┌──────────────────────┐
│  Research Agent  │ ──────────────────►  │   Synthesis Agent    │
│  (RAG / Qdrant)  │                      │  (grounded answer +  │
└──────────────────┘   low confidence     │   citation check)    │
         │             ──────────────────►└──────────────────────┘
         │                                        ▲
         ▼                                        │
┌──────────────────┐                              │
│    Web Agent     │ ─────────────────────────────┘
│ (Tavily MCP)     │
└──────────────────┘
```

---

## Technology Stack

| Concern | Choice | Rationale |
|---|---|---|
| Agent orchestration | **LangGraph** | Typed state graph, native LangSmith tracing, deterministic routing |
| Primary LLM | **OpenAI** (`gpt-4o-mini` default) | Configurable via env vars (`OPENAI_API_KEY`, `OPENAI_MODEL`, `OPENAI_BASE_URL`) |
| Local LLM fallback | **Ollama** (`llama3.2`) | Zero cost, fully offline, no data egress |
| Vector database | **Qdrant** (Docker) | Hybrid search, local-first, production-grade |
| Embeddings | **sentence-transformers** `all-MiniLM-L6-v2` | Free, local, CPU-efficient, no API key required |
| Document processing | **PyMuPDF4LLM** + LangChain loaders | GNN-based PDF extraction + multi-format support |
| Web search (MCP) | **Tavily API** via MCP stdio server | Structured results, agent-optimised, free tier |
| Observability | **LangSmith** + OpenTelemetry | Native LangGraph traces + vendor-neutral OTLP spans |
| UI | **Streamlit** | Rapid dev, file upload, streaming, free Community Cloud deploy |
| Testing | **pytest** | Unit + LLM behaviour validation, adversarial prompts |

---

## Project Structure

```
epam_capstone/
├── src/
│   ├── agents/
│   │   ├── research_agent.py      # RAG node: query reform → vector search → confidence
│   │   ├── web_agent.py           # MCP node: Tavily search via stdio subprocess
│   │   └── synthesis_agent.py     # Combine results → cited answer + hallucination check
│   ├── rag/
│   │   ├── document_processor.py  # PyMuPDF4LLM + LangChain loaders + chunking
│   │   ├── embeddings.py          # sentence-transformers wrapper (lru_cache singleton)
│   │   └── vector_store.py        # Qdrant client wrapper
│   ├── mcp/
│   │   └── tavily_mcp.py          # Full MCP server (stdio) exposing tavily_search tool
│   ├── security/
│   │   ├── auth.py                # SHA-256 + hmac.compare_digest session auth
│   │   ├── pii_detector.py        # Regex PII detection + log anonymisation
│   │   └── rate_limiter.py        # Sliding-window per-thread rate limiter
│   ├── observability/
│   │   └── telemetry.py           # OpenTelemetry TracerProvider (console + OTLP)
│   ├── orchestrator.py            # LangGraph StateGraph + input validation + process_query
│   ├── state.py                   # Shared AgentState TypedDict
│   └── config.py                  # All configuration loaded from environment variables
├── ui/
│   └── app.py                     # Streamlit chat UI: auth gate, file upload, feedback
├── tests/
│   ├── conftest.py                # sys.path fixture
│   ├── test_research_agent.py     # RAG retrieval + confidence routing
│   ├── test_web_agent.py          # MCP search + LLM summarisation
│   ├── test_synthesis_agent.py    # Answer generation + hallucination check
│   ├── test_orchestrator.py       # Graph routing + end-to-end pipeline (mocked)
│   ├── test_security.py           # Rate limiter, PII detector, auth
│   └── test_edge_cases.py         # 10+ adversarial prompt-injection patterns
├── docs/
│   ├── architecture_blueprint.md  # Full system design, data flow, trade-offs
│   ├── executive_summary.md       # 1-page business overview for stakeholders
│   ├── self_review.md             # Code commentary: decisions, trade-offs, lessons
│   └── task.md                    # Original capstone task specification
├── data/
│   └── sample_docs/               # Knowledge base: ML, Python, RAG, prompting, architecture, DevOps, security (MD, TXT)
├── docker-compose.yml             # Qdrant vector database service
├── .env.example                   # Environment variable template (copy to .env)
├── requirements.txt               # Pinned dependencies
└── README.md
```

---

## Prerequisites

- Python 3.11+
- Docker Desktop (for Qdrant)
- API keys:
  - **OpenAI** — https://platform.openai.com/api-keys
  - **Tavily** — https://app.tavily.com/ (free tier: 100 req/month)
  - **LangSmith** — https://smith.langchain.com/ (optional, for LLM tracing)

---

## Setup

### 1. Clone and create a virtual environment

```bash
git clone <repo-url>
cd epam_capstone
python -m venv .venv

# Windows (PowerShell)
.  \.venv\Scripts\Activate.ps1
# If blocked by execution policy, run first:
# Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

# macOS / Linux
source .venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment variables

A `.env` file is already provided in the project root with all variables pre-populated with placeholder values. Open it and replace the placeholders with your actual keys:

```bash
# ── Required ──────────────────────────────────────────────────────────────────
# OpenAI (default provider)
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini

# Tavily web search (MCP)
TAVILY_API_KEY=tvly-...

# ── Optional: LangSmith tracing ───────────────────────────────────────────────
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=ls__...

# ── Optional: OpenTelemetry spans ─────────────────────────────────────────────
# OTEL_CONSOLE_EXPORT=true                          # print spans to stdout
# OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317 # send to Jaeger/Tempo

# ── Optional: authentication (disabled by default) ────────────────────────────
# AUTH_ENABLED=true
# AUTH_USERNAME=admin
# AUTH_PASSWORD_HASH=<sha256 hex>  # python -c "import hashlib; print(hashlib.sha256(b'yourpassword').hexdigest())"
```

> **Never commit `.env` to git.** It is already listed in `.gitignore`.

### 4. Start the vector database

```bash
docker compose up -d
# Verify: curl http://localhost:6333/health
```

### 5. Index the sample documents

```bash
python -c "
from src.rag.document_processor import process_directory
from src.rag.vector_store import VectorStore
from src.config import SAMPLE_DOCS_DIR
vs = VectorStore()
docs = process_directory(SAMPLE_DOCS_DIR)
count = vs.upsert_documents(docs)
print(f'Indexed {count} chunks')
"
```

---

## Running the Application

```bash
streamlit run ui/app.py
```

Open http://localhost:8501 in your browser.

### Example queries

- *"What is the difference between supervised and unsupervised learning?"*
  → answered from `machine_learning_overview.md`

- *"What Python linting tools should I use?"*
  → answered from `python_best_practices.md`

- *"What chunking strategy should I use for RAG over technical docs?"*
  → answered from `rag_and_vector_databases.md`

- *"How do I defend against prompt injection?"*
  → answered from `llm_prompt_engineering.md`

- *"What HTTP status code should I return for a rate limit error?"*
  → answered from `api_design_and_security.md`

- *"What is the difference between LangGraph and CrewAI?"*
  → answered from `software_architecture_patterns.md`

- *"How do I set up a Dockerfile health check for a Compose service?"*
  → answered from `docker_and_devops.md`

- *"What happened in AI research this week?"*
  → low document confidence → Tavily MCP web search fallback

---

## Running Tests

```bash
pytest tests/ -v
```

The test suite includes:
- **Positive tests**: normal queries, doc retrieval, synthesis
- **Negative tests**: empty queries, DB failures, LLM failures
- **Adversarial tests**: 10+ prompt-injection patterns

---

## Architecture Decisions & Trade-offs

### LangGraph over CrewAI
LangGraph provides explicit state control through a typed `AgentState` TypedDict,
making data flow between agents transparent and easy to test. CrewAI's role-based
abstraction is simpler to set up but harder to introspect or extend with custom routing.

### OpenAI (`gpt-4o-mini`) as primary LLM
`gpt-4o-mini` provides a strong balance of capability, speed, and cost. The provider
is fully configurable via environment variables (`OPENAI_API_KEY`, `OPENAI_MODEL`,
`OPENAI_BASE_URL`), so switching to any OpenAI-compatible provider requires no code
changes.

### Qdrant over ChromaDB
Qdrant supports hybrid (dense + sparse) search which improves recall on keyword-heavy
queries. It runs locally via Docker with no cloud dependency and scales to production
without code changes. ChromaDB was considered for its simpler setup but lacks native
hybrid search.

### Local embeddings over API embeddings
`sentence-transformers/all-MiniLM-L6-v2` runs on CPU in <100 ms per batch, costs
nothing, and keeps document content on-premises. The quality difference versus
OpenAI embeddings is small for domain-specific retrieval tasks.

### MCP stdio transport over SSE
The Tavily MCP server uses stdio transport (subprocess spawn), which is simpler to
run locally without a separate HTTP server. For a production deployment, SSE transport
would be preferred so the MCP server can be centralised and shared across users.

### MemorySaver over SQLite checkpointer
`MemorySaver` requires no additional dependencies and is sufficient for single-session
demos. For a multi-user production deployment, replace it with
`langgraph-checkpoint-postgres` backed by a PostgreSQL instance.

---

## Observability

The system has two independent observability layers that can be used together or separately:

**LangSmith** (LangGraph-native, recommended for LLM traces)

Set `LANGCHAIN_TRACING_V2=true` and `LANGCHAIN_API_KEY` in `.env`. Every agent node is automatically traced in [LangSmith](https://smith.langchain.com/) showing:
- Inputs / outputs per node
- Token usage and latency
- Full prompt templates

**OpenTelemetry** (vendor-neutral infrastructure spans)

Each agent emits a span via `src/observability/telemetry.py` with attributes such as `rag.confidence`, `doc.count`, `use_web`, and `answer.length`. Exporter options:

| Environment variable | Effect |
|---|---|
| `OTEL_CONSOLE_EXPORT=true` | Print spans to stdout (local debugging) |
| `OTEL_EXPORTER_OTLP_ENDPOINT=http://host:4317` | Send to Jaeger / Grafana Tempo / Honeycomb |
| Neither set | No-op — application runs normally without any telemetry infra |

---

## Deliverables

| Document | Location | Description |
|---|---|---|
| Architecture Blueprint | [docs/architecture_blueprint.md](docs/architecture_blueprint.md) | Full system design: agent roles, data flow, technology stack, MCP integration, security, RAG pipeline, infrastructure, trade-offs |
| Executive Summary | [docs/executive_summary.md](docs/executive_summary.md) | 1–2 page business overview: problem, solution, key metrics, lessons learned |
| Self-Review | [docs/self_review.md](docs/self_review.md) | Code commentary: architecture decisions, implementation choices, trade-offs, what I'd do differently |
| Test Suite | [tests/](tests/) | 50+ automated tests across 6 modules — positive, negative, adversarial |
| Video Demo | *(link to be added)* | 2–5 minute demo with voiceover: system walkthrough, test run, code review |

---

## Security

| Control | Implementation |
|---|---|
| **Input validation** | `validate_input()` in `orchestrator.py` — strips whitespace, enforces 2 000-char limit, blocks 10 prompt-injection regex patterns (case-insensitive) |
| **PII detection** | `src/security/pii_detector.py` — detects EMAIL, PHONE, SSN, IPv4 and replaces them with typed placeholders in log output; raw query is still used for processing |
| **Rate limiting** | `src/security/rate_limiter.py` — sliding-window per `thread_id` (default: 10 req / 60 s), thread-safe with `threading.Lock` |
| **Authentication** | `src/security/auth.py` — optional session login (`AUTH_ENABLED=true`), SHA-256 password hash, `hmac.compare_digest` constant-time comparison, `secrets.token_hex(32)` session tokens |
| **Hallucination check** | Synthesis Agent runs a second LLM pass to verify every answer claim against retrieved sources; appends `⚠️ Verification note` when unverified |
| **No secrets in code** | All API keys loaded from `.env`; `.env` is gitignored; `.env.example` ships no real values |
| **Dependency pinning** | `requirements.txt` pins major versions to reduce supply-chain risk |

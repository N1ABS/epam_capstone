# Personal Knowledge Assistant

A multi-agent RAG system that answers questions by searching your personal documents
first and falling back to live web search when needed.

```
User Query
    │
    ▼
┌──────────────────┐   high confidence   ┌──────────────────────┐
│  Research Agent  │ ──────────────────► │   Synthesis Agent    │
│  (RAG / Qdrant)  │                     │  (grounded answer +  │
└──────────────────┘   low confidence    │   citation check)    │
         │             ──────────────────► ──────────────────────┘
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
| Agent orchestration | **LangGraph** | Stateful graphs, native MCP support, LangSmith tracing |
| Primary LLM | **Groq** (`llama-3.3-70b-versatile`) | Free tier, 100+ tok/s, OpenAI-compatible |
| Local LLM fallback | **Ollama** (`llama3.2`) | Zero cost, fully offline |
| Vector database | **Qdrant** (Docker) | Hybrid search, local-first, production-grade |
| Embeddings | **sentence-transformers** `all-MiniLM-L6-v2` | Free, local, CPU-efficient |
| Document processing | **PyMuPDF4LLM** + LangChain loaders | GNN-based PDF accuracy + multi-format support |
| Web search (MCP) | **Tavily API** | Structured results, agent-optimised, free tier |
| Observability | **LangSmith** + OpenTelemetry | Native LangGraph traces + infra metrics |
| UI | **Streamlit** | Rapid dev, streaming, free Community Cloud deploy |
| Testing | **pytest** | Unit + LLM behaviour validation |

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
│   │   ├── embeddings.py          # sentence-transformers wrapper (cached)
│   │   └── vector_store.py        # Qdrant client wrapper
│   ├── mcp/
│   │   └── tavily_mcp.py          # MCP server exposing Tavily as a tool (stdio)
│   ├── orchestrator.py            # LangGraph StateGraph + input validation
│   ├── state.py                   # Shared AgentState TypedDict
│   └── config.py                  # Environment-based configuration
├── ui/
│   └── app.py                     # Streamlit chat interface
├── tests/
│   ├── conftest.py                # Shared fixtures
│   ├── test_research_agent.py
│   ├── test_web_agent.py
│   ├── test_synthesis_agent.py
│   ├── test_orchestrator.py
│   └── test_edge_cases.py        # Input validation + adversarial prompts
├── data/
│   └── sample_docs/               # Sample knowledge base (MD, TXT)
├── docker-compose.yml             # Qdrant vector database
├── .env.example                   # Environment variable template
├── requirements.txt
└── README.md
```

---

## Prerequisites

- Python 3.11+
- Docker Desktop (for Qdrant)
- Free API keys: [Groq](https://console.groq.com/) · [Tavily](https://app.tavily.com/) · [LangSmith](https://smith.langchain.com/) (optional)

---

## Setup

### 1. Clone and create a virtual environment

```bash
git clone <repo-url>
cd epam_capstone
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment variables

```bash
cp .env.example .env
# Edit .env and fill in your API keys
```

Required:
- `GROQ_API_KEY` — from https://console.groq.com/
- `TAVILY_API_KEY` — from https://app.tavily.com/

Optional (for observability):
- `LANGCHAIN_API_KEY` — from https://smith.langchain.com/

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

### Groq over OpenAI
Groq's free tier is sufficient for development and demo purposes and is
~10x cheaper in production. The OpenAI-compatible API means switching providers
requires changing only the client instantiation.

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

With `LANGCHAIN_TRACING_V2=true` and a valid `LANGCHAIN_API_KEY`, every agent
invocation is traced in [LangSmith](https://smith.langchain.com/). Each trace shows:

- Inputs / outputs per node
- Token usage and latency
- Full prompt templates

---

## Security

- **Input validation**: all user input is sanitised and checked against 10 prompt-injection
  patterns before reaching any agent.
- **No secret logging**: API keys are loaded from environment variables; `.env` is in `.gitignore`.
- **Dependency pinning**: `requirements.txt` pins major versions to avoid supply-chain surprises.

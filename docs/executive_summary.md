# Executive Summary — Personal Knowledge Assistant

**Project:** Personal Knowledge Assistant (PKA)  
**Date:** May 2026  
**Audience:** Review committee, management, investors

---

## Problem Statement

Knowledge workers accumulate vast personal document libraries — notes,
research papers, internal guides, PDFs — that quickly become unsearchable.
Standard search tools require exact keyword matches and return no synthesised
answers.  Meanwhile, querying a general-purpose AI model produces hallucinated
responses disconnected from personal or proprietary content.

The **Personal Knowledge Assistant** closes this gap: it answers questions
grounded in the user's own documents first, escalates to live web search when
the local knowledge base is insufficient, and always attributes every claim to
its source.

---

## Solution Overview

PKA is a **three-agent, LangGraph-orchestrated system** built entirely on
free-tier and locally-running components:

| Agent | Role |
|---|---|
| **Research Agent** | Rewrites the user's question for vector search, queries Qdrant, and scores retrieval confidence |
| **Web Agent** | When document confidence is low, fetches live search results via the Tavily MCP server |
| **Synthesis Agent** | Merges both result sets into a cited, hallucination-checked answer |

A **confidence threshold** (default 0.60) governs the routing decision: above
the threshold the web agent is skipped, keeping latency low and API costs zero.
Below the threshold the Web Agent runs as a transparent fallback.

---

## Key Technical Decisions

| Decision | Choice | Reason |
|---|---|---|
| Agent framework | LangGraph | Typed state graph, native LangSmith tracing, deterministic routing |
| Primary LLM | Groq `llama-3.3-70b-versatile` | Free tier, 100+ tok/s, OpenAI-compatible API |
| Local LLM fallback | Ollama `llama3.2` | Zero cost, fully offline, no data leaves the machine |
| Vector database | Qdrant (Docker) | Local-first, hybrid search, production-grade, no cloud dependency |
| Embeddings | `sentence-transformers/all-MiniLM-L6-v2` | Free, CPU-efficient, runs offline, no API key |
| Web search (MCP) | Tavily API via stdio MCP server | Structured results, free tier, agent-optimised protocol |
| Observability | LangSmith + OpenTelemetry | Per-span agent traces + infrastructure metrics without vendor lock-in |
| UI | Streamlit | Rapid development, streaming-friendly, Community Cloud deployable |

---

## Security and Non-Functional Highlights

- **Input validation** — regex-based prompt-injection detection blocks 10+
  adversarial patterns before any agent is invoked.
- **PII detection** — emails, phone numbers, SSNs, and IP addresses are
  detected and anonymised in log output; raw queries are never persisted.
- **Rate limiting** — a per-session sliding-window limiter (10 req / 60 s)
  prevents API quota abuse.
- **Authentication** — optional session-based login with constant-time
  credential comparison (HMAC) guards the Streamlit UI.
- **Hallucination check** — the Synthesis Agent runs a second LLM pass to
  flag any answer claim not grounded in the retrieved sources.
- **Graceful degradation** — every agent wraps failures in try/except and
  stores errors in shared state rather than raising, so downstream agents
  always receive a valid context to work with.

---

## Results and Business Value

| Metric | Outcome |
|---|---|
| End-to-end latency (doc-only path) | ~2–4 s (Groq free tier) |
| End-to-end latency (web fallback path) | ~5–9 s |
| Test coverage | 50+ automated tests across 6 modules (positive, negative, adversarial) |
| External API spend | $0 (Groq free tier + Tavily free tier + local embeddings) |
| Infrastructure cost | $0 (Qdrant on local Docker) |

**Business value:**  A knowledge worker who spends 30 minutes per day
searching documents could recover most of that time through instant,
cited answers from their personal corpus.  Because all document content
stays on-premises (Qdrant + local embeddings), the system is compliant
with data-residency requirements that would prevent cloud-hosted RAG
solutions from being used with proprietary documents.

---

## Lessons Learned

1. **LangGraph's typed state is an architecture asset** — making data flow
   explicit (rather than relying on agent return values) made both debugging
   and testing dramatically easier.
2. **MCP via stdio is simpler than it looks** — spawning the Tavily MCP
   server as a subprocess avoids the need for a separate running service and
   keeps the deployment a single `streamlit run` command.
3. **Free tiers are sufficient for demos** — Groq's inference speed means
   the system feels responsive even on the free plan; Tavily's 100 req/month
   free tier is more than enough for a demo workload.
4. **Hallucination checking adds latency** — the second LLM pass for
   verification adds ~1–2 s; in production this would be made asynchronous
   or replaced with a lighter embedding-similarity check.

---

## Potential Next Steps

- **Multi-user deployment** — replace `MemorySaver` with a PostgreSQL
  checkpointer and add per-user Qdrant namespaces.
- **Incremental ingestion** — watch a local folder for new files and index
  them automatically rather than requiring manual re-indexing.
- **Richer MCP tools** — add calendar, email, and note-taking MCP servers
  so the assistant can act, not just answer.
- **Streaming UI** — pipe the Synthesis Agent's LLM output token-by-token
  to Streamlit's `st.write_stream` for a more responsive feel.
- **Bias and fairness monitoring** — integrate an embedding-based bias
  scanner to flag skewed distributions in retrieved documents.

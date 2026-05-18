# Software Architecture Patterns — Personal Notes

## SOLID Principles

| Principle | One-liner | Common violation |
|---|---|---|
| **S** — Single Responsibility | A class should have one reason to change | God objects that mix DB, business logic, and UI |
| **O** — Open/Closed | Open for extension, closed for modification | Deeply nested if/elif chains for type dispatch |
| **L** — Liskov Substitution | Subtypes must be substitutable for their base types | Subclass that raises `NotImplementedError` on inherited methods |
| **I** — Interface Segregation | Clients should not depend on interfaces they don't use | Fat interfaces with methods irrelevant to most implementors |
| **D** — Dependency Inversion | Depend on abstractions, not concretions | Hardcoded `import MyConcreteDB` inside business logic |

---

## Design Patterns (most useful in practice)

### Creational

**Factory Method** — delegates object creation to subclasses or configuration:
```python
def get_llm(provider: str) -> BaseLLM:
    if provider == "openai":
        return ChatOpenAI(...)
    if provider == "ollama":
        return ChatOllama(...)
    raise ValueError(f"Unknown provider: {provider}")
```

**Singleton (via `lru_cache`)** — ensures a single shared instance:
```python
from functools import lru_cache

@lru_cache(maxsize=1)
def get_vector_store() -> VectorStore:
    return VectorStore()
```

### Structural

**Adapter** — wraps an incompatible interface. Used extensively in LangChain to
present any LLM provider as `BaseChatModel`.

**Facade** — provides a simplified interface to a complex subsystem. The
`process_query()` function in `orchestrator.py` is a facade over the full
LangGraph agent pipeline.

### Behavioural

**Strategy** — swap algorithms at runtime. Useful for swapping retrieval strategies
(dense-only vs hybrid) or LLM providers without changing the calling code.

**Observer** — decouple event producers from consumers. OpenTelemetry spans follow
this pattern: agents emit spans; exporters react independently.

**Chain of Responsibility** — pass a request through a chain of handlers until one
handles it. A layered input validation pipeline (length check → injection check →
PII detection) is a Chain of Responsibility.

---

## Clean Architecture

Layers (inside → outside):

```
┌────────────────────────────────────────────┐
│  Frameworks & Drivers (Streamlit, Qdrant)  │
├────────────────────────────────────────────┤
│  Interface Adapters (orchestrator, UI)     │
├────────────────────────────────────────────┤
│  Application Use Cases (agent logic)       │
├────────────────────────────────────────────┤
│  Domain Entities (AgentState, models)      │
└────────────────────────────────────────────┘
```

**Dependency rule:** source code dependencies must point inward only. Domain entities
know nothing about Qdrant or Streamlit; agents know nothing about HTTP transport.

---

## Multi-Agent Architecture Patterns

**Shared State (LangGraph approach):**
- Agents communicate exclusively through a typed state object.
- No direct agent-to-agent calls.
- Deterministic routing via conditional edges on state values.
- Pros: testable (pure function state-in → state-out), traceable, debuggable.
- Cons: verbose for simple workflows.

**Message Passing:**
- Agents send messages to a shared queue or event bus.
- Loosely coupled; easier to add/remove agents.
- Harder to trace the exact flow for a given request.

**Supervisor / Subagent:**
- A supervisor LLM decides which specialist agent to call next.
- Flexible for open-ended tasks.
- Non-deterministic routing makes testing harder.

---

## Stateless vs Stateful Services

**Stateless:** each request is self-contained; no server-side session.
- Easier to scale horizontally.
- Suitable for read-heavy APIs.

**Stateful (with checkpointing):**
- LangGraph `MemorySaver` maintains conversation history per `thread_id`.
- For production multi-user systems, replace with a database-backed checkpointer
  (PostgreSQL via `langgraph-checkpoint-postgres`).

---

## Error Handling Strategies

1. **Fail fast** — validate inputs at the system boundary before expensive computation.
2. **Graceful degradation** — catch failures inside agents; propagate errors through
   state rather than raising exceptions that kill the pipeline.
3. **Circuit breaker** — after N consecutive failures to an external service, stop
   calling it for a cooldown period to avoid cascading timeouts.
4. **Idempotency** — make write operations safe to retry (deterministic IDs for
   vector upserts prevent ghost entries on re-ingestion).

---

## API Design Principles

- **Single entry point**: expose one `process_query(query, thread_id)` function;
  callers don't need to know about the internal graph.
- **Typed contracts**: use TypedDict or Pydantic models at API boundaries so IDEs
  and type checkers catch mismatches.
- **Return errors in-band**: return an error state rather than raising, so callers
  can handle partial results gracefully.
- **Idempotent ingest**: upsert (not insert) documents so running ingest twice does
  not create duplicates.

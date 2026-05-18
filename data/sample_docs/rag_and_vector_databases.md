# RAG and Vector Databases — Reference Guide

## What is RAG?

Retrieval-Augmented Generation (RAG) is a pattern that grounds LLM responses in
external documents rather than relying solely on the model's parametric memory.

**Core pipeline:**

1. **Ingest** — load documents, split into chunks, embed each chunk, store vectors.
2. **Retrieve** — embed the user query, find the most similar chunks by cosine
   distance.
3. **Generate** — pass the retrieved chunks as context to the LLM prompt and generate
   a grounded answer.

**Why RAG instead of fine-tuning?**

| Concern | RAG | Fine-tuning |
|---|---|---|
| Knowledge update | Add/replace documents instantly | Re-train or re-fine-tune |
| Cost | Embedding + retrieval (~$0.001/query) | GPU training hours |
| Attribution | Can cite exact source chunks | No native attribution |
| Hallucination risk | Lower (grounded in retrieved text) | Higher without grounding |

---

## Chunking Strategies

The quality of RAG retrieval depends heavily on how documents are split.

**Fixed-size chunking** (`RecursiveCharacterTextSplitter`):
- `chunk_size=512`, `overlap=50` is a good starting point for technical prose.
- Overlap prevents information loss at chunk boundaries.
- Separator hierarchy: `["\n\n", "\n", " ", ""]` respects paragraph structure.

**Semantic chunking:**
- Split on sentence embeddings; merge semantically similar consecutive sentences.
- Better recall but slower and more complex to implement.

**Markdown-aware chunking:**
- Split on `##` headers to keep sections intact.
- Ideal when documents have consistent header structure.

**Rules of thumb:**
- Chunks should be self-contained — a reader with no other context should understand
  the chunk.
- Shorter chunks (256–512 tokens) improve precision; longer chunks (1 024+ tokens)
  improve recall.
- For Q&A over documentation, 512-token chunks with 10% overlap is a well-validated
  default.

---

## Embedding Models

**Local (free):**
- `all-MiniLM-L6-v2` — 384 dimensions, 22 MB, best speed-quality balance for English.
- `all-mpnet-base-v2` — 768 dimensions, higher quality, 2–3× slower.
- `paraphrase-multilingual-MiniLM-L12-v2` — 384 dimensions, supports 50+ languages.

**API-based:**
- OpenAI `text-embedding-3-small` — 1 536 dimensions, $0.02/million tokens.
- OpenAI `text-embedding-3-large` — 3 072 dimensions, $0.13/million tokens.
- Cohere `embed-v3` — strong multilingual and long-document support.

**Normalisation:** always L2-normalise embeddings before storing so that cosine
similarity equals dot product, enabling faster SIMD operations in vector DBs.

---

## Vector Database Comparison

| Feature | Qdrant | ChromaDB | Pinecone | FAISS |
|---|---|---|---|---|
| Self-hosted | ✅ Docker | ✅ In-process | ❌ Cloud only | ✅ Library |
| Hybrid search | ✅ Dense + sparse | ❌ | ✅ | ❌ |
| Metadata filtering | ✅ | ✅ | ✅ | ❌ |
| Production scale | ✅ | ⚠️ | ✅ | ✅ |
| Free tier | Self-hosted | Self-hosted | 1 index free | Self-hosted |

**Qdrant** is the best choice for a local-first system that may need to scale:
- Start with `docker run -p 6333:6333 qdrant/qdrant`.
- Supports both cosine and dot-product distance.
- `payload` field stores arbitrary metadata (source, page, date).
- Hybrid search combines dense embeddings with sparse BM25 vectors for better
  keyword recall.

---

## Retrieval Quality Evaluation

**Metrics to track:**

- **Hit rate** — fraction of queries where the correct document is in the top-K results.
- **MRR (Mean Reciprocal Rank)** — rewards finding the correct document higher in
  the ranked list.
- **NDCG (Normalised Discounted Cumulative Gain)** — accounts for partial relevance.
- **Answer faithfulness** (RAGAs framework) — does the generated answer contain only
  claims supported by the retrieved context?
- **Answer relevance** (RAGAs) — does the answer actually address the question?
- **Context precision** — what fraction of retrieved chunks were actually relevant?

**Practical evaluation approach:**
1. Create a golden QA set (20–50 Q/A pairs with known source documents).
2. Run retrieval and check if the correct source appears in top-K.
3. Use an LLM judge to score faithfulness and relevance automatically.

---

## Confidence Scoring

A simple but effective proxy for retrieval quality is the **top-result cosine
similarity score**:

- Score ≥ 0.60 → answer from documents (high confidence).
- Score 0.40–0.60 → documents exist but weak match; consider supplementing with web.
- Score < 0.40 → no relevant documents; fall back to web search.

These thresholds are heuristic; calibrate on your specific corpus and query
distribution for best results.

---

## Common RAG Failure Modes

1. **Chunking too coarse** — relevant facts span two chunks; neither chunk alone
   answers the question.
2. **Missing re-ranking** — the top-1 cosine result is not the most relevant; a
   cross-encoder re-ranker would improve precision.
3. **Query-document mismatch** — user queries use different vocabulary than documents;
   query expansion or HyDE (Hypothetical Document Embeddings) helps.
4. **Context window overflow** — stuffing too many chunks exceeds the LLM's context;
   implement a max-context-length guard.
5. **Stale documents** — the vector store is not updated when source documents change;
   use deterministic chunk IDs to enable upsert-on-change.

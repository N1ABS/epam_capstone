"""
Qdrant-backed vector store wrapper.

Responsibilities:
  - Create the collection on first use if it does not exist.
  - Upsert documents with their embeddings and source metadata.
  - Perform cosine-similarity search with an optional score threshold.
"""
import logging
from typing import Any, Dict, List, Optional

from langchain_core.documents import Document
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    PointStruct,
    VectorParams,
)

from src.config import (
    EMBEDDING_DIMENSION,
    QDRANT_COLLECTION,
    QDRANT_URL,
    TOP_K_DOCUMENTS,
)
from src.rag.embeddings import embed_query, embed_texts

logger = logging.getLogger(__name__)


class VectorStore:
    """Thin wrapper around Qdrant for document ingestion and retrieval."""

    def __init__(self, url: str = QDRANT_URL, collection: str = QDRANT_COLLECTION) -> None:
        self.client = QdrantClient(url=url, timeout=10)
        self.collection = collection
        self._ensure_collection()

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _ensure_collection(self) -> None:
        """Create the Qdrant collection if it does not already exist."""
        existing = {c.name for c in self.client.get_collections().collections}
        if self.collection not in existing:
            self.client.create_collection(
                collection_name=self.collection,
                vectors_config=VectorParams(
                    size=EMBEDDING_DIMENSION,
                    distance=Distance.COSINE,
                ),
            )
            logger.info("Created Qdrant collection '%s'", self.collection)

    # ── Public API ────────────────────────────────────────────────────────────

    def upsert_documents(self, documents: List[Document]) -> int:
        """
        Embed and upsert *documents* into the vector store.
        Returns the number of points written.
        """
        if not documents:
            return 0

        texts = [doc.page_content for doc in documents]
        embeddings = embed_texts(texts)

        # Use a stable deterministic ID derived from index so repeated ingests
        # overwrite duplicates instead of creating ghost entries.
        existing_count = self.collection_count()
        points = [
            PointStruct(
                id=existing_count + idx,
                vector=embedding,
                payload={
                    "content": doc.page_content,
                    "source": doc.metadata.get("source", "unknown"),
                    "type": doc.metadata.get("type", "text"),
                    **{
                        k: v
                        for k, v in doc.metadata.items()
                        if k not in ("source", "type")
                    },
                },
            )
            for idx, (doc, embedding) in enumerate(zip(documents, embeddings))
        ]

        self.client.upsert(collection_name=self.collection, points=points)
        logger.info("Upserted %d points into '%s'", len(points), self.collection)
        return len(points)

    def similarity_search(
        self,
        query: str,
        top_k: int = TOP_K_DOCUMENTS,
        score_threshold: float = 0.3,
    ) -> List[Dict[str, Any]]:
        """
        Return the *top_k* most similar documents for *query*.
        Only results with score >= *score_threshold* are included.
        """
        query_vector = embed_query(query)
        hits = self.client.search(
            collection_name=self.collection,
            query_vector=query_vector,
            limit=top_k,
            score_threshold=score_threshold,
            with_payload=True,
        )
        return [
            {
                "content": h.payload.get("content", ""),
                "source": h.payload.get("source", "unknown"),
                "score": h.score,
                "metadata": {
                    k: v
                    for k, v in h.payload.items()
                    if k not in ("content", "source")
                },
            }
            for h in hits
        ]

    def collection_count(self) -> int:
        """Return the total number of points in the collection."""
        info = self.client.get_collection(self.collection)
        return info.points_count or 0

    def delete_collection(self) -> None:
        """Drop the entire collection. Used in test teardown."""
        self.client.delete_collection(self.collection)
        logger.info("Deleted Qdrant collection '%s'", self.collection)

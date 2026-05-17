"""
Local embedding generation using sentence-transformers.

The model is downloaded once on first use and cached in memory for the
lifetime of the process — no API key or internet connection required.
"""
import logging
from functools import lru_cache
from typing import List

from sentence_transformers import SentenceTransformer

from src.config import EMBEDDING_MODEL

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _get_model() -> SentenceTransformer:
    """Load the embedding model and cache it (singleton per process)."""
    logger.info("Loading embedding model: %s", EMBEDDING_MODEL)
    return SentenceTransformer(EMBEDDING_MODEL)


def embed_texts(texts: List[str]) -> List[List[float]]:
    """Return a list of embedding vectors for the given texts."""
    model = _get_model()
    embeddings = model.encode(
        texts,
        convert_to_numpy=True,
        show_progress_bar=False,
        normalize_embeddings=True,  # cosine similarity = dot product after normalisation
    )
    return embeddings.tolist()


def embed_query(query: str) -> List[float]:
    """Return the embedding vector for a single query string."""
    return embed_texts([query])[0]

"""
Document loading, cleaning, and chunking for the RAG pipeline.

Supported formats: PDF (via PyMuPDF4LLM), TXT, Markdown, DOCX.
"""
import logging
from pathlib import Path
from typing import List

import pymupdf4llm
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import (
    TextLoader,
    UnstructuredMarkdownLoader,
    UnstructuredWordDocumentLoader,
)
from langchain_core.documents import Document

from src.config import CHUNK_OVERLAP, CHUNK_SIZE

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS: set = {".pdf", ".txt", ".md", ".docx"}


def load_pdf(file_path: Path) -> List[Document]:
    """
    Load a PDF using PyMuPDF4LLM's GNN-based extraction.
    Returns a single Document with Markdown-formatted content preserving
    headings, tables, and lists without any GPU requirement.
    """
    md_text = pymupdf4llm.to_markdown(str(file_path), write_images=False)
    return [
        Document(
            page_content=md_text,
            metadata={"source": str(file_path), "type": "pdf"},
        )
    ]


def load_document(file_path: Path) -> List[Document]:
    """Load a single file. Raises ValueError for unsupported extensions."""
    ext = file_path.suffix.lower()
    if ext == ".pdf":
        return load_pdf(file_path)
    if ext == ".txt":
        return TextLoader(str(file_path), encoding="utf-8").load()
    if ext == ".md":
        return UnstructuredMarkdownLoader(str(file_path)).load()
    if ext == ".docx":
        return UnstructuredWordDocumentLoader(str(file_path)).load()
    raise ValueError(f"Unsupported file type: '{ext}'")


def split_documents(documents: List[Document]) -> List[Document]:
    """
    Split documents into overlapping chunks.
    Separator hierarchy respects paragraph → line → word boundaries.
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        length_function=len,
        separators=["\n\n", "\n", " ", ""],
    )
    return splitter.split_documents(documents)


def process_directory(directory: Path) -> List[Document]:
    """
    Recursively load and chunk all supported documents in *directory*.
    Unsupported files and load failures are logged and skipped.
    """
    all_docs: List[Document] = []
    for file_path in sorted(directory.rglob("*")):
        if file_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        try:
            docs = load_document(file_path)
            logger.info("Loaded %d doc(s) from %s", len(docs), file_path.name)
            all_docs.extend(docs)
        except Exception as exc:
            logger.error("Failed to load %s: %s", file_path.name, exc)

    chunks = split_documents(all_docs)
    logger.info(
        "Processed %d documents → %d chunks (chunk_size=%d, overlap=%d)",
        len(all_docs),
        len(chunks),
        CHUNK_SIZE,
        CHUNK_OVERLAP,
    )
    return chunks

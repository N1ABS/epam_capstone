"""
Personal Knowledge Assistant — Streamlit UI
============================================
Multi-agent RAG + Web search interface.

Run:
    streamlit run ui/app.py
"""
import os
import sys
import time
import uuid
from pathlib import Path

# Make project root importable when launched from any working directory.
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st

from src.config import SAMPLE_DOCS_DIR
from src.orchestrator import process_query, validate_input
from src.rag.document_processor import load_document, process_directory, split_documents
from src.rag.vector_store import VectorStore
from src.security.auth import generate_session_token, is_auth_enabled, verify_credentials
from src.security.rate_limiter import RateLimitExceededError

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Personal Knowledge Assistant",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ── Authentication gate ───────────────────────────────────────────────────────
def _require_auth() -> bool:
    """
    Render a login form when AUTH_ENABLED=true and the session is not yet
    authenticated.  Returns True when the caller may proceed, False when the
    login form has been shown and the user must authenticate first.
    """
    if not is_auth_enabled():
        return True
    if st.session_state.get("authenticated"):
        return True

    st.title("🔐 Login Required")
    st.caption("Set AUTH_ENABLED=false in .env to disable authentication for local development.")
    with st.form("login_form", clear_on_submit=True):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Sign in", use_container_width=True)

        if submitted:
            if verify_credentials(username, password):
                st.session_state.authenticated = True
                st.session_state.session_token = generate_session_token()
                st.rerun()
            else:
                st.error("Invalid username or password.")
    return False


if not _require_auth():
    st.stop()


# ── Session state initialisation ─────────────────────────────────────────────
if "history" not in st.session_state:
    st.session_state.history = []
if "thread_id" not in st.session_state:
    st.session_state.thread_id = str(uuid.uuid4())

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("🧠 PKA")
    st.caption("Personal Knowledge Assistant")
    st.markdown("---")

    # ── Knowledge base management ─────────────────────────────────────────────
    st.header("📚 Knowledge Base")

    if st.button("Index Sample Documents", use_container_width=True, type="primary"):
        with st.spinner("Indexing…"):
            try:
                vs = VectorStore()
                docs = process_directory(SAMPLE_DOCS_DIR)
                count = vs.upsert_documents(docs)
                st.success(f"Indexed **{count}** chunks from `data/sample_docs/`")
            except Exception as exc:
                st.error(f"Indexing failed: {exc}")

    st.markdown("---")
    st.subheader("Upload Documents")
    uploaded = st.file_uploader(
        "Add files to the knowledge base",
        type=["pdf", "txt", "md", "docx"],
        accept_multiple_files=True,
        label_visibility="collapsed",
    )
    if uploaded and st.button("Process Uploads", use_container_width=True):
        with st.spinner("Processing…"):
            try:
                import tempfile

                vs = VectorStore()
                total = 0
                for f in uploaded:
                    suffix = Path(f.name).suffix
                    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                        tmp.write(f.getvalue())
                        tmp_path = Path(tmp.name)
                    raw = load_document(tmp_path)
                    chunks = split_documents(raw)
                    for c in chunks:
                        c.metadata["source"] = f.name  # show original filename
                    total += vs.upsert_documents(chunks)
                    os.unlink(tmp_path)
                st.success(f"Indexed **{total}** chunks from {len(uploaded)} file(s)")
            except Exception as exc:
                st.error(f"Upload failed: {exc}")

    st.markdown("---")

    # ── System info ───────────────────────────────────────────────────────────
    st.header("ℹ️ System")
    st.markdown(
        "**Agents**\n"
        "- 🔍 Research Agent — RAG over personal docs\n"
        "- 🌐 Web Agent — live search via Tavily MCP\n"
        "- 🧩 Synthesis Agent — grounded, cited answers\n\n"
        "**Stack**\n"
        "LangGraph · Qdrant · OpenAI · Streamlit"
    )

    if st.button("🗑️ Clear Chat", use_container_width=True):
        st.session_state.history = []
        st.session_state.thread_id = str(uuid.uuid4())
        st.rerun()

# ── Main area ─────────────────────────────────────────────────────────────────
st.title("Personal Knowledge Assistant")
st.caption(
    "Ask questions about your documents. The assistant will search your "
    "knowledge base first and fall back to live web search when needed."
)

# ── Render chat history ───────────────────────────────────────────────────────
for msg in st.session_state.history:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])
        if msg.get("sources"):
            with st.expander("📎 Sources"):
                for s in msg["sources"]:
                    if s["type"] == "document":
                        fname = Path(s["source"]).name
                        st.markdown(
                            f"📄 **{fname}** &mdash; relevance: {s.get('score', 0):.2f}"
                        )
                    else:
                        title = s.get("title") or s["source"]
                        st.markdown(f"🌐 [{title}]({s['source']})")

# ── Query input ───────────────────────────────────────────────────────────────
query = st.chat_input("Ask anything about your documents or the web…")

if query:
    # Client-side validation before invoking agents
    try:
        validate_input(query)
    except ValueError as exc:
        st.error(f"Invalid query: {exc}")
        st.stop()

    # Show user message
    st.session_state.history.append({"role": "user", "content": query})
    with st.chat_message("user"):
        st.write(query)

    # Run pipeline and display response
    with st.chat_message("assistant"):
        with st.spinner("Thinking… Research → Web → Synthesis"):
            t0 = time.time()
            try:
                result = process_query(query, thread_id=st.session_state.thread_id)
                elapsed = time.time() - t0

                answer = result.get("synthesis") or "No response generated."
                sources = result.get("sources", [])
                doc_count = len(result.get("doc_results", []))
                web_count = len(result.get("web_results", []))
                confidence = result.get("confidence", 0.0)

                st.write(answer)
                st.caption(
                    f"⏱ {elapsed:.1f}s &nbsp;·&nbsp; "
                    f"📄 {doc_count} doc chunk(s) &nbsp;·&nbsp; "
                    f"🌐 {web_count} web result(s) &nbsp;·&nbsp; "
                    f"confidence: {confidence:.2f}"
                )

                if sources:
                    with st.expander("📎 Sources"):
                        for s in sources:
                            if s["type"] == "document":
                                fname = Path(s["source"]).name
                                st.markdown(
                                    f"📄 **{fname}** &mdash; relevance: {s.get('score', 0):.2f}"
                                )
                            else:
                                title = s.get("title") or s["source"]
                                st.markdown(f"🌐 [{title}]({s['source']})")

                # Rating widget
                col1, col2, _ = st.columns([1, 1, 8])
                with col1:
                    if st.button("👍", key=f"up_{len(st.session_state.history)}"):
                        st.toast("Thanks for the positive feedback!")
                with col2:
                    if st.button("👎", key=f"dn_{len(st.session_state.history)}"):
                        st.toast("Thanks — noted for improvement.")

                st.session_state.history.append(
                    {"role": "assistant", "content": answer, "sources": sources}
                )

            except ValueError as exc:
                st.error(f"Validation error: {exc}")
            except RateLimitExceededError as exc:
                st.warning(f"⏱ {exc}")
            except Exception as exc:
                st.error(f"Pipeline error: {exc}")
                logger.error("Pipeline error for query '%s': %s", query, exc, exc_info=True)

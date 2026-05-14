"""ChromaDB browser — single-page Streamlit admin.

Talks to ChromaDB through the official Python client, which natively
handles the v1 tenant-scoped API. Lists every collection, lets you page
through documents + metadata, and runs ad-hoc retrieval against a
collection using either a free-text query (encoded with the same
language-routed embedder M2 uses in production) or an arbitrary vector.

Designed for the local dev stack and quick poking around — not a
production admin tool. Run via docker compose service ``chromadb_admin``
or stand-alone via ``streamlit run frontend/chromadb_admin.py``.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

# Allow standalone host runs to import the production embedder for
# semantic query encoding. In the Docker container this path isn't on
# sys.path (and that's fine — we fall back to raw-vector mode).
_BACKEND = Path(__file__).resolve().parents[1] / "backend"
if _BACKEND.exists() and str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

CHROMA_HOST = os.environ.get("CHROMA_HOST", "localhost")
CHROMA_PORT = int(os.environ.get("CHROMA_PORT", "8001"))

st.set_page_config(page_title="ChromaDB Browser", layout="wide")
st.title("ChromaDB Browser")
st.caption(f"Connected to `http://{CHROMA_HOST}:{CHROMA_PORT}`")


@st.cache_resource
def get_client():
    import chromadb
    return chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)


@st.cache_resource
def get_embedder():
    """Return ``embed_query`` if the production embedder is importable, else None."""
    try:
        from app.core.nlp.embedder import embed_query  # type: ignore
        return embed_query
    except Exception as exc:
        st.sidebar.warning(f"Embedder unavailable — semantic queries disabled.\n\n`{exc}`")
        return None


def main() -> None:
    try:
        client = get_client()
        heartbeat = client.heartbeat()
        st.sidebar.success(f"Chroma heartbeat: {heartbeat}")
    except Exception as exc:
        st.error(f"Cannot reach ChromaDB at `{CHROMA_HOST}:{CHROMA_PORT}` — {exc}")
        st.stop()

    collections = client.list_collections()
    if not collections:
        st.warning("No collections found. Run the pipeline (or `embedder_chromadb_test.py`) first.")
        st.stop()

    names = [c.name for c in collections]
    st.sidebar.header("Collection")
    selected = st.sidebar.selectbox("Select", names, key="collection")
    col = client.get_collection(name=selected)
    n_total = col.count()
    st.sidebar.metric("Total vectors", n_total)

    # ── Documents tab ──────────────────────────────────────────────
    st.subheader(f"Collection — `{selected}`  ({n_total} vectors)")
    st.caption(
        f"Metadata: {col.metadata}"
        if col.metadata
        else "Metadata: (none — default L2 distance unless created with hnsw:space=cosine)"
    )

    tab_docs, tab_query, tab_raw = st.tabs(["Documents", "Semantic query", "Raw / by ID"])

    with tab_docs:
        page_size = st.number_input("Page size", min_value=10, max_value=200, value=25, step=5)
        page = st.number_input("Page (0-indexed)", min_value=0, value=0, step=1)
        offset = int(page) * int(page_size)
        if offset >= n_total:
            st.warning(f"Offset {offset} ≥ collection size {n_total}.")
        else:
            # Optional metadata filter
            filter_text = st.text_input(
                "Metadata filter (Chroma `where=` JSON, e.g. `{\"company_id\":\"adib\"}`)",
                value="",
            )
            where = None
            if filter_text.strip():
                import json
                try:
                    where = json.loads(filter_text)
                except Exception as exc:
                    st.error(f"Filter JSON parse error: {exc}")
                    where = None

            kwargs = {
                "limit": int(page_size),
                "offset": int(offset),
                "include": ["documents", "metadatas"],
            }
            if where:
                kwargs["where"] = where
            try:
                got = col.get(**kwargs)
            except Exception as exc:
                st.error(f"get() failed: {exc}")
                got = {"ids": [], "documents": [], "metadatas": []}

            rows = []
            for cid, doc, md in zip(got["ids"], got["documents"], got["metadatas"] or []):
                row = {"chunk_id": cid, "text": (doc or "")[:400]}
                if md:
                    row.update(md)
                rows.append(row)
            if rows:
                df = pd.DataFrame(rows)
                st.dataframe(df, use_container_width=True, height=480)
            else:
                st.info("No documents matched.")

    with tab_query:
        embed_query = get_embedder()
        if embed_query is None:
            st.info(
                "Semantic search needs the production embedder. Either run this "
                "page on the host (where `backend/` is importable) or rebuild "
                "the container with the embedder code mounted."
            )
        else:
            q = st.text_area("Query text", value="What is the total Scope 1 GHG emissions?", height=80)
            top_k = st.slider("Top K", min_value=1, max_value=20, value=5)
            # Allow forcing language; collections are language-segregated
            # under our M2 convention, so try to infer from collection name.
            inferred = (
                "ar" if selected.endswith("_ar")
                else "en" if selected.endswith("_en")
                else None
            )
            lang_choice = st.selectbox(
                "Embed query as language",
                options=["auto", "en", "ar"],
                index={None: 0, "en": 1, "ar": 2}[inferred],
            )
            where_text = st.text_input("Optional metadata filter (where=)", value="", key="qwhere")
            if st.button("Run query"):
                lang = None if lang_choice == "auto" else lang_choice
                try:
                    qvec = embed_query(q, lang=lang)
                except Exception as exc:
                    st.error(f"Embedding failed: {exc}")
                    return
                where = None
                if where_text.strip():
                    import json
                    try:
                        where = json.loads(where_text)
                    except Exception as exc:
                        st.error(f"Filter JSON parse error: {exc}")
                kwargs = {
                    "query_embeddings": [qvec.tolist()],
                    "n_results": int(top_k),
                    "include": ["documents", "metadatas", "distances"],
                }
                if where:
                    kwargs["where"] = where
                res = col.query(**kwargs)
                if not res.get("ids") or not res["ids"][0]:
                    st.info("No results.")
                else:
                    rows = []
                    for cid, doc, md, dist in zip(
                        res["ids"][0],
                        res["documents"][0],
                        res["metadatas"][0] or [],
                        res["distances"][0],
                    ):
                        row = {"rank_distance": round(float(dist), 4), "chunk_id": cid,
                               "text": (doc or "")[:500]}
                        if md:
                            row.update(md)
                        rows.append(row)
                    st.dataframe(pd.DataFrame(rows), use_container_width=True, height=520)

    with tab_raw:
        ids_text = st.text_input("Get by chunk_id (comma-separated)", value="")
        if ids_text.strip():
            ids = [s.strip() for s in ids_text.split(",") if s.strip()]
            try:
                got = col.get(
                    ids=ids,
                    include=["documents", "metadatas", "embeddings"],
                )
            except Exception as exc:
                st.error(f"get(ids=...) failed: {exc}")
                got = None
            if got and got.get("ids"):
                for cid, doc, md, vec in zip(
                    got["ids"], got["documents"], got["metadatas"] or [], got["embeddings"] or []
                ):
                    st.markdown(f"**`{cid}`**")
                    st.write({"metadata": md, "embedding_dim": len(vec) if vec is not None else None})
                    st.text(doc or "")
                    st.divider()


if __name__ == "__main__":
    main()

from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document

from contract_agent.runtime.config import settings
from contract_agent.llm.client import get_embeddings


class VectorStoreLike(Protocol):
    def similarity_search(self, query: str, k: int = 3) -> list[Document]:
        ...


def _vector_backend() -> str:
    return (settings.vector_backend or "faiss").strip().lower()


def _is_milvus_backend() -> bool:
    return _vector_backend() == "milvus"


def _ensure_numpy_compat_for_pymilvus() -> None:
    try:
        import numpy as np

        if not hasattr(np, "bool8"):
            np.bool8 = np.bool_  # type: ignore[attr-defined]
    except Exception:
        return


def _sanitize_metadata_for_milvus(metadata: dict) -> dict[str, str]:
    sanitized: dict[str, str] = {}
    for key, value in metadata.items():
        if key in {"pk", "text", "vector"}:
            continue
        if value is None:
            sanitized[key] = ""
            continue
        if isinstance(value, (str, int, float, bool)):
            sanitized[key] = str(value)
            continue
        sanitized[key] = json.dumps(value, ensure_ascii=False)
    return sanitized


def _build_milvus_store(documents: list[Document]):
    _ensure_numpy_compat_for_pymilvus()
    try:
        from langchain_community.vectorstores import Milvus
    except Exception as exc:
        raise RuntimeError("Milvus backend requested but langchain/pymilvus is not available.") from exc

    embeddings = get_embeddings()
    texts: list[str] = []
    metadatas: list[dict[str, str]] = []
    ids: list[str] = []
    for doc in documents:
        raw_metadata = dict(doc.metadata or {})
        doc_id = str(raw_metadata.get("chunk_id") or raw_metadata.get("doc_id") or uuid4().hex)
        texts.append(doc.page_content)
        metadatas.append(_sanitize_metadata_for_milvus(raw_metadata))
        ids.append(doc_id)

    if not texts:
        return Milvus(
            embedding_function=embeddings,
            connection_args={"uri": settings.milvus_uri},
            collection_name=settings.milvus_collection_name,
            consistency_level=settings.milvus_consistency_level,
        )

    return Milvus.from_texts(
        texts=texts,
        embedding=embeddings,
        metadatas=metadatas,
        collection_name=settings.milvus_collection_name,
        connection_args={"uri": settings.milvus_uri},
        ids=ids,
        consistency_level=settings.milvus_consistency_level,
        drop_old=True,
    )


def build_vector_store(documents: list[Document]):
    if _is_milvus_backend():
        return _build_milvus_store(documents)

    embeddings = get_embeddings()
    return FAISS.from_documents(documents, embeddings)


def save_vector_store(vector_store, target_dir: str) -> None:
    if _is_milvus_backend():
        return

    Path(target_dir).mkdir(parents=True, exist_ok=True)
    vector_store.save_local(target_dir)


def load_vector_store(target_dir: str):
    if _is_milvus_backend():
        _ensure_numpy_compat_for_pymilvus()
        try:
            from langchain_community.vectorstores import Milvus
        except Exception as exc:
            raise RuntimeError("Milvus backend requested but langchain/pymilvus is not available.") from exc

        embeddings = get_embeddings()
        return Milvus(
            embedding_function=embeddings,
            connection_args={"uri": settings.milvus_uri},
            collection_name=settings.milvus_collection_name,
            consistency_level=settings.milvus_consistency_level,
        )

    embeddings = get_embeddings()
    return FAISS.load_local(
        target_dir,
        embeddings,
        allow_dangerous_deserialization=True,
    )


def is_knowledge_base_ready(target_dir: str) -> bool:
    if _is_milvus_backend():
        _ensure_numpy_compat_for_pymilvus()
        try:
            from pymilvus import connections, utility

            connections.connect(alias="default", uri=settings.milvus_uri)
            return bool(utility.has_collection(settings.milvus_collection_name))
        except Exception:
            return False

    return Path(target_dir).exists()

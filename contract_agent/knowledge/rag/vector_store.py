from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Protocol
from uuid import uuid4

from contract_agent.runtime.config import Settings, settings, settings_snapshot
from contract_agent.provider.client import get_embeddings

if TYPE_CHECKING:
    from langchain_core.documents import Document


class VectorStoreLike(Protocol):
    def similarity_search(self, query: str, k: int = 3) -> list[Document]:
        ...


def _vector_backend(runtime_settings: Settings | None = None) -> str:
    source = runtime_settings or settings_snapshot()
    return (source.vector_backend or "faiss").strip().lower()


def _is_milvus_backend(runtime_settings: Settings | None = None) -> bool:
    return _vector_backend(runtime_settings) == "milvus"


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


def _build_milvus_store(documents: list[Document], runtime_settings: Settings):
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
            connection_args={"uri": runtime_settings.milvus_uri},
            collection_name=runtime_settings.milvus_collection_name,
            consistency_level=runtime_settings.milvus_consistency_level,
        )

    return Milvus.from_texts(
        texts=texts,
        embedding=embeddings,
        metadatas=metadatas,
        collection_name=runtime_settings.milvus_collection_name,
        connection_args={"uri": runtime_settings.milvus_uri},
        ids=ids,
        consistency_level=runtime_settings.milvus_consistency_level,
        drop_old=True,
    )


def build_vector_store(documents: list[Document], runtime_settings: Settings | None = None):
    source = runtime_settings or settings_snapshot()
    if _is_milvus_backend(source):
        return _build_milvus_store(documents, source)

    from langchain_community.vectorstores import FAISS

    embeddings = get_embeddings()
    return FAISS.from_documents(documents, embeddings)


def save_vector_store(vector_store, target_dir: str, runtime_settings: Settings | None = None) -> None:
    if _is_milvus_backend(runtime_settings):
        return

    Path(target_dir).mkdir(parents=True, exist_ok=True)
    vector_store.save_local(target_dir)


def load_vector_store(target_dir: str, runtime_settings: Settings | None = None):
    source = runtime_settings or settings_snapshot()
    if _is_milvus_backend(source):
        _ensure_numpy_compat_for_pymilvus()
        try:
            from langchain_community.vectorstores import Milvus
        except Exception as exc:
            raise RuntimeError("Milvus backend requested but langchain/pymilvus is not available.") from exc

        embeddings = get_embeddings()
        return Milvus(
            embedding_function=embeddings,
            connection_args={"uri": source.milvus_uri},
            collection_name=source.milvus_collection_name,
            consistency_level=source.milvus_consistency_level,
        )

    from langchain_community.vectorstores import FAISS

    embeddings = get_embeddings()
    return FAISS.load_local(
        target_dir,
        embeddings,
        allow_dangerous_deserialization=True,
    )


def is_knowledge_base_ready(target_dir: str, runtime_settings: Settings | None = None) -> bool:
    source = runtime_settings or settings_snapshot()
    if _is_milvus_backend(source):
        _ensure_numpy_compat_for_pymilvus()
        try:
            from pymilvus import connections, utility

            connections.connect(alias="default", uri=source.milvus_uri)
            return bool(utility.has_collection(source.milvus_collection_name))
        except Exception:
            return False

    return Path(target_dir).exists()

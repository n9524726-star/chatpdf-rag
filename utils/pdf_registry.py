"""
utils/pdf_registry.py — Persistência dos metadados de cada PDF (JSON sidecar) e
"hidratação" do st.session_state a partir do disco.

O ChromaDB (vector_store.py) persiste os embeddings, mas não guarda o nome do
arquivo, o texto completo extraído nem o resumo (insights) do Dashboard -- isso
é o que este módulo cuida, salvando um <pdf_id>.json ao lado de cada PDF em
data/uploads/. Juntos, os dois módulos permitem que a lista de PDFs sobreviva a
um restart do processo Streamlit, sem precisar reenviar nada.
"""
from __future__ import annotations

import json
from pathlib import Path

import streamlit as st

from utils.vector_store import PDFVectorStore

METADATA_DIR = Path("data/uploads")


def _metadata_path(pdf_id: str) -> Path:
    return METADATA_DIR / f"{pdf_id}.json"


def save_metadata(pdf_id: str, filename: str, pdf_path: Path, full_text: str, insights: dict) -> None:
    METADATA_DIR.mkdir(parents=True, exist_ok=True)
    data = {
        "pdf_id": pdf_id,
        "filename": filename,
        "path": str(pdf_path),
        "full_text": full_text,
        "insights": insights,
    }
    _metadata_path(pdf_id).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def load_all_metadata() -> dict[str, dict]:
    """Lê todos os <pdf_id>.json existentes. Ignora arquivos corrompidos em vez
    de derrubar a página inteira -- um metadado ruim não deveria impedir o
    resto dos PDFs de carregar."""
    METADATA_DIR.mkdir(parents=True, exist_ok=True)
    result: dict[str, dict] = {}
    for meta_file in METADATA_DIR.glob("*.json"):
        try:
            data = json.loads(meta_file.read_text(encoding="utf-8"))
            result[data["pdf_id"]] = data
        except Exception:
            continue
    return result


def delete_metadata(pdf_id: str) -> None:
    _metadata_path(pdf_id).unlink(missing_ok=True)


def hydrate_session_pdf_store() -> None:
    """Popula st.session_state.pdf_store a partir do disco, uma vez por sessão.

    Reconecta a cada PDFVectorStore existente (sem recalcular embeddings -- eles
    já estão persistidos no ChromaDB) e reconstrói a entrada usada pelas páginas
    ChatPDF e Dashboard. O histórico de mensagens do chat NÃO é persistido de
    propósito: cada nova sessão começa com o chat limpo, mas o PDF e seu resumo
    continuam disponíveis.
    """
    if "pdf_store" not in st.session_state:
        st.session_state.pdf_store = {}

    if st.session_state.get("_pdf_store_hydrated"):
        return

    for pdf_id, meta in load_all_metadata().items():
        if pdf_id in st.session_state.pdf_store:
            continue
        try:
            index = PDFVectorStore(pdf_id, meta["filename"])  # só conecta, não reindexar
        except Exception:
            # A coleção pode ter sido removida manualmente do disco sem passar
            # pelo botão de exclusão -- ignora esse PDF em vez de quebrar a página.
            continue

        st.session_state.pdf_store[pdf_id] = {
            "filename": meta["filename"],
            "path": Path(meta["path"]),
            "index": index,
            "full_text": meta.get("full_text", ""),
            "insights": meta.get("insights"),
        }

    st.session_state._pdf_store_hydrated = True

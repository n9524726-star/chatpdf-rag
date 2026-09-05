"""
utils/vector_store.py — Índice semântico persistido em disco via ChromaDB.

Antes, os embeddings viviam só em memória (numpy, por sessão do Streamlit) --
reiniciar o processo apagava tudo, exigindo reenviar os PDFs. Agora usamos um
ChromaDB PersistentClient salvo em data/chroma_db/. Uma coleção por PDF (nome
"pdf_<id>"), o que torna a exclusão de um PDF trivial: apagar a coleção inteira.

Requer um modelo de embeddings baixado no Ollama, ex:
    ollama pull nomic-embed-text
"""
from __future__ import annotations

from pathlib import Path

import chromadb
import ollama

EMBED_MODEL = "nomic-embed-text"
CHROMA_DIR = Path("data/chroma_db")

_client = None  # cache do client -- reabrir o PersistentClient a cada rerun do
                 # Streamlit seria desnecessário e mais lento


def get_client() -> "chromadb.ClientAPI":
    global _client
    if _client is None:
        CHROMA_DIR.mkdir(parents=True, exist_ok=True)
        _client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    return _client


def _collection_name(pdf_id: str) -> str:
    return f"pdf_{pdf_id}"


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Gera embeddings para uma lista de textos via Ollama."""
    return [ollama.embeddings(model=EMBED_MODEL, prompt=t)["embedding"] for t in texts]


class PDFVectorStore:
    """Uma coleção ChromaDB por PDF, persistida em disco.

    Dois modos de uso:
    - Upload novo: passe `chunks` -- cria a coleção do zero e indexa tudo.
    - PDF já indexado numa sessão anterior: não passe `chunks` (ou None) --
      apenas conecta à coleção existente, sem recalcular embeddings.
    """

    def __init__(self, pdf_id: str, filename: str, chunks: list[str] | None = None):
        self.pdf_id = pdf_id
        self.filename = filename
        client = get_client()
        name = _collection_name(pdf_id)

        if chunks is not None:
            # (Re)cria a coleção do zero -- get_or_create + delete evita erro se
            # já existir uma coleção antiga com o mesmo id (reenvio do mesmo PDF).
            existing = {c.name for c in client.list_collections()}
            if name in existing:
                client.delete_collection(name)
            self.collection = client.create_collection(name)

            embeddings = embed_texts(chunks)
            ids = [f"{pdf_id}-{i}" for i in range(len(chunks))]
            self.collection.add(ids=ids, embeddings=embeddings, documents=chunks)
        else:
            self.collection = client.get_collection(name)

    def search(self, query: str, top_k: int = 4) -> list[str]:
        query_embedding = embed_texts([query])[0]
        results = self.collection.query(query_embeddings=[query_embedding], n_results=top_k)
        documents = results.get("documents") or []
        return documents[0] if documents else []

    def delete(self) -> None:
        """Remove a coleção inteira do disco (chamado quando o usuário exclui o PDF)."""
        client = get_client()
        name = _collection_name(self.pdf_id)
        try:
            client.delete_collection(name)
        except Exception:
            pass  # coleção já pode não existir mais -- não é motivo para travar a exclusão

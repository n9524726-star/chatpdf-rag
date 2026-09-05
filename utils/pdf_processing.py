"""
utils/pdf_processing.py — Extração de texto e chunking.

A função _rejoin_wrapped_lines é adaptada do projeto pdf-translator do usuário:
PDFs (especialmente artigos em duas colunas) quebram linhas na largura da
coluna, não no fim de frases. Sem correção, o chunk fica "picado" e prejudica
tanto a busca semântica quanto a resposta da IA.
"""
from __future__ import annotations

from pypdf import PdfReader


def _rejoin_wrapped_lines(page_text: str) -> str:
    """Junta linhas que são apenas quebra visual, corrigindo hifenização."""
    raw_lines = [ln.strip() for ln in page_text.splitlines()]
    paragraphs: list[str] = []
    current = ""

    for line in raw_lines:
        if not line:
            if current:
                paragraphs.append(current)
                current = ""
            continue
        if not current:
            current = line
        elif current.endswith("-") and not current.endswith("--"):
            current = current[:-1] + line
        else:
            current = current.rstrip() + " " + line

    if current:
        paragraphs.append(current)

    return "\n\n".join(paragraphs)


def extract_text(pdf_path: str) -> str:
    """Extrai e devolve o texto completo de um PDF, página a página."""
    reader = PdfReader(pdf_path)
    pages = []
    for i, page in enumerate(reader.pages, start=1):
        raw = (page.extract_text() or "").strip()
        if raw:
            pages.append(f"[Página {i}]\n{_rejoin_wrapped_lines(raw)}")
    if not pages:
        raise ValueError(
            "Nenhum texto extraído. O PDF pode ser escaneado (imagem) e precisar de OCR."
        )
    return "\n\n".join(pages)


def chunk_text(text: str, chunk_size: int = 1200, overlap: int = 150) -> list[str]:
    """Divide o texto em trechos com sobreposição, para preservar contexto
    entre chunks na hora da busca semântica."""
    chunks = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + chunk_size, n)
        chunks.append(text[start:end])
        if end == n:
            break
        start = end - overlap
    return chunks

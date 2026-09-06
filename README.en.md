# chatpdf-rag

🇺🇸 English | 🇧🇷 [Português](README.md)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)

Analytical dashboard and conversational assistant over PDF documents, running
100% locally with [Ollama](https://ollama.com) — no data leaves the machine,
no cloud API involved.

Upload one or more PDFs, chat with them with answers strictly grounded in the
uploaded content, and see a dashboard automatically generated from whatever
each document actually contains — no fixed schema, adapted to the content
type of each file.

## Screenshots

<p align="center">
  <img src="docs/screenshots/login.png" alt="Login screen" width="30%">
  <img src="docs/screenshots/chatpdf.png" alt="ChatPDF conversation" width="30%">
  <img src="docs/screenshots/dashboard.png" alt="Adaptive dashboard" width="30%">
</p>

## Why

Cloud "chat with your documents" tools require sending the content to
third-party servers — inconvenient for résumés, contracts, institutional
material, or any sensitive document. This project runs entirely on your
machine: extraction, embeddings, semantic search, and response generation,
all via local Ollama.

## How it works

1. **Upload** — the PDF is saved to `data/uploads/` and its text extracted
   with `pypdf`, with paragraph reconstruction across column breaks (common
   in academic and institutional two-column documents).
2. **Indexing** — the text is split into overlapping chunks, embeddings are
   generated via `nomic-embed-text`, and persisted in a dedicated collection
   in [ChromaDB](https://www.trychroma.com/) (`data/chroma_db/`).
3. **Structured summary** — in parallel, the full text is sent to the chat
   model with instructions to extract an adaptive JSON (metrics, categorical
   distribution, keywords, table) — without assuming a fixed document type.
   This summary feeds the Dashboard.
4. **Multi-document conversation** — the user selects which PDFs participate
   in the conversation. Each question retrieves the most relevant chunks from
   each selected document (RAG), labels the source of each chunk, and injects
   everything into a prompt that restricts the answer to that set of
   documents.
5. **Persistence** — both the embeddings (ChromaDB) and the metadata
   (filename, extracted text, summary) survive process restarts. Nothing
   needs to be re-uploaded.

## Requirements

- Python 3.10+
- [Ollama](https://ollama.com/download) installed and running
- A chat model (e.g. `llama3.2`) and the embedding model:
  ```bash
  ollama pull llama3.2
  ollama pull nomic-embed-text
  ```

## Installation

```bash
git clone https://github.com/PGC13/chatpdf-rag.git
cd chatpdf-rag

python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\Activate.ps1

pip install -r requirements.txt

cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# edit the file with real username/password
```

## Usage

```bash
streamlit run app.py
```

1. Log in (credentials defined in `.streamlit/secrets.toml`).
2. In **ChatPDF**, upload one or more PDFs. Check (☑️) which ones should
   participate in the current conversation — one or several at once.
3. Ask freely. Answers are restricted to the content of the checked PDFs;
   questions outside that scope are declined.
4. In **Dashboard**, pick (dropdown) which PDF to view. Metrics, a
   distribution chart, keywords, and a table are generated from that
   document's actual content — the **Regenerate** button reprocesses the
   summary on demand.
5. Delete a PDF (🗑️) at any time — removes the file, the vector index, and
   the metadata, leaving no trace on disk.

## Project structure

```
chatpdf-rag/
├── app.py                       # login (entry point)
├── pages/
│   ├── 1_Dashboard.py           # per-document adaptive dashboard
│   └── 2_ChatPDF.py             # upload, multi-select, deletion, and chat
├── utils/
│   ├── auth.py                  # credential checking
│   ├── pdf_processing.py        # text extraction + chunking
│   ├── vector_store.py          # embeddings + ChromaDB (persisted on disk)
│   ├── pdf_registry.py          # PDF metadata + session hydration
│   └── pdf_insights.py          # adaptive LLM-based summary extraction (JSON)
├── modelfiles/                  # optional Ollama Modelfiles (see below)
├── data/uploads/                 # uploaded PDFs + metadata (generated at runtime)
├── data/chroma_db/                # persisted vector index (generated at runtime)
├── .streamlit/secrets.toml.example
└── requirements.txt
```

See [`ARCHITECTURE.md`](ARCHITECTURE.en.md) for the technical breakdown of each
module and the design decisions behind them.

## Custom models (optional)

The `modelfiles/` directory defines two Ollama models derived from the base
model, with parameters tuned for each specific role in the system:

| Modelfile | Generated model | Role | Main tweak |
|---|---|---|---|
| `Modelfile.chat` | `chatpdf-assistant` | Conversation about the PDF | `temperature 0.3`, `num_ctx 8192` (expanded context for retrieved chunks) |
| `Modelfile.insights` | `chatpdf-insights` | Data extraction for the Dashboard | `temperature 0.05`, no fixed `seed` (preserves the usefulness of the Regenerate button) |

Build:

```bash
ollama create chatpdf-assistant -f modelfiles/Modelfile.chat
ollama create chatpdf-insights  -f modelfiles/Modelfile.insights
```

Without this step, the app works normally using the plain base model. Details
on each parameter choice in [`modelfiles/README.md`](modelfiles/README.en.md).

## Limitations

- **Single-user authentication** — fine for personal use, not for multiple
  accounts with their own passwords (see Roadmap).
- **Scanned (image) PDFs are not supported** — requires OCR, which is not
  included.
- **Insight extraction is not deterministic** — since it relies on an LLM,
  two runs over the same document may produce slightly different metrics.
  The Regenerate button exists to give it another try when that happens.
- **Conversation history is not persisted** — restarting the process clears
  the chat, but keeps the indexed documents and their summaries.
- **Context grows with the number of PDFs checked** at once in the
  conversation — responses tend to get slower with many documents selected
  simultaneously.

## Roadmap

- [x] Disk persistence for embeddings and metadata (ChromaDB)
- [x] Conversation across multiple simultaneous PDFs, with source attribution
- [x] Dashboard with adaptive schema (no assumed document type)
- [x] Custom Ollama models via Modelfile
- [ ] Multiple users with their own authentication (`streamlit-authenticator`)
- [ ] Document-type detection as a separate step, allowing fixed schemas for
      known cases (e.g. résumés) with an adaptive fallback
- [ ] OCR support for scanned PDFs
- [ ] Optional pre-processing via [`pdf-translator`](https://github.com/PGC13/pdf-translator)
      for documents in another language
- [ ] Conversation history persistence

## Contributing

Suggestions, fixes, and pull requests are welcome. Please open an issue
describing the problem or improvement before submitting larger changes.

## License

MIT — see [LICENSE](LICENSE).

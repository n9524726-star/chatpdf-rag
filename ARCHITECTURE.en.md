# Technical Architecture

🇺🇸 English | 🇧🇷 [Português](ARCHITECTURE.md)

Architecture breakdown, module responsibilities, and design decisions behind
`chatpdf-rag`. Complements [`README.md`](README.en.md), which covers
installation and usage.

---

## 1. Architecture overview

The system is split into three layers:

- **Interface** (Streamlit, multipage): login, Dashboard, ChatPDF.
- **Document processing**: text extraction, chunking, embedding generation,
  structured summary extraction.
- **Persistence**: ChromaDB for embeddings, JSON for metadata — both on local
  disk, no external database dependency.

All language inference (chat, embeddings, summary extraction) goes through
Ollama, running locally. There are no external API calls anywhere in the
system.

## 2. Tech stack

| Component | Use |
|---|---|
| Streamlit | Interface, native multipage routing |
| Ollama | Chat model + `nomic-embed-text` (embeddings), 100% local |
| pypdf | PDF text extraction |
| ChromaDB | Vector index persisted to disk |
| pandas / numpy | Data handling for the Dashboard |

## 3. File structure

```
chatpdf-rag/
├── app.py
├── pages/
│   ├── 1_Dashboard.py
│   └── 2_ChatPDF.py
├── utils/
│   ├── auth.py
│   ├── pdf_processing.py
│   ├── vector_store.py
│   ├── pdf_registry.py
│   └── pdf_insights.py
├── modelfiles/
│   ├── Modelfile.chat
│   ├── Modelfile.insights
│   └── README.md
├── data/uploads/        # PDFs + metadata (JSON), generated at runtime
├── data/chroma_db/       # persisted embeddings, generated at runtime
└── .streamlit/secrets.toml.example
```

## 4. Modules

### 4.1 `app.py` — Authentication and routing

Login screen with a username/password form. The sidebar is hidden via CSS
while unauthenticated, to prevent direct navigation to the internal pages
before login. `utils/auth.py` validates against `.streamlit/secrets.toml`;
in that file's absence, a fallback `admin`/`admin` avoids blocking local
development — **not recommended beyond that**.

Logout clears all session state related to documents and conversation
(`pdf_store`, `chat_messages`, `selected_pdf_ids`, hydration flag), without
deleting anything from disk.

### 4.2 `utils/pdf_processing.py` — Extraction and chunking

`extract_text()` reads the PDF page by page via `pypdf`. The
`_rejoin_wrapped_lines()` function fixes a common issue in two-column PDFs
(common in academic and institutional documents): extraction captures the
column's *visual* line breaks, not real sentence breaks — without
correction, the text ends up artificially fragmented, hurting both semantic
search and summary extraction. The function joins consecutive lines without
a real blank-line break, fixing end-of-line hyphenation.

`chunk_text()` splits the corrected text into ~1200-character blocks with a
150-character overlap, preserving context between adjacent chunks for vector
indexing.

### 4.3 `utils/vector_store.py` — Persisted vector index

`PDFVectorStore` keeps one ChromaDB collection per document (`pdf_<id>`),
persisted to `data/chroma_db/`. Two initialization modes:

- **With `chunks`** (new upload): creates the collection from scratch,
  generates embeddings via `ollama.embeddings(model="nomic-embed-text")`,
  and indexes them.
- **Without `chunks`** (already-indexed document): just connects to the
  existing collection, without recomputing embeddings.

`search()` uses Chroma's native similarity search; `delete()` removes the
entire collection — deleting a document is a single atomic operation, no
need to track individual chunk IDs.

### 4.4 `utils/pdf_registry.py` — Metadata and session hydration

ChromaDB persists embeddings, but not the filename, full text, or structured
summary — that lives in a JSON sidecar (`<pdf_id>.json`) next to each PDF in
`data/uploads/`.

`hydrate_session_pdf_store()` is called at the top of every page: on a
session's first run, it reads all metadata from disk and reconnects each
corresponding `PDFVectorStore` (without reprocessing embeddings), repopulating
`st.session_state.pdf_store`. A session flag prevents repeating this
hydration on every Streamlit rerun.

Conversation history is **not** persisted by this layer — every new session
starts with a clean chat, but the indexed documents and their summaries
remain available.

### 4.5 `utils/pdf_insights.py` — Adaptive summary extraction

Generates the structured JSON consumed by the Dashboard. Unlike a schema
fixed per document type, the prompt instructs the model to **decide**, based
on the text's actual content, which metrics, categories, and items are worth
highlighting — the same pipeline works for a résumé, an academic paper, a
contract, or a financial report.

Output schema:

```json
{
  "titulo_documento": "string",
  "tipo_documento": "string",
  "resumo_curto": "string",
  "metricas": [{"rotulo": "string", "valor": "string|number"}],
  "distribuicao": {"titulo": "string", "categorias": {"categoria": number}},
  "tags": ["string"],
  "tabela": {"titulo": "string", "colunas": ["string"], "linhas": [["string"]]}
}
```

All sections are optional and independent. `_validate_and_clean()` discards
any malformed section (e.g. table rows with an inconsistent number of
columns) instead of propagating the error to the UI — a document with no
categorical data simply doesn't generate a chart, for example.

### 4.6 `pages/2_ChatPDF.py` — Conversation across multiple documents

Upload flow: extraction → chunking → indexing (ChromaDB) → summary extraction
(parallel, used by the Dashboard) → metadata persistence.

**Multi-select**: the sidebar shows a checkbox per document
(`st.session_state.selected_pdf_ids`), letting the user check as many PDFs as
they want to include in the conversation at once. The conversation is a
single one per session (`chat_messages`), no longer one instance per document.

**Context retrieval (RAG)**: for every question, similarity search runs
separately on each checked document — there is no single combined search.
The number of chunks retrieved per document is reduced based on how many
documents are selected (`4` for a single document, `max(2, 6 // n)` for
multiple), to keep the context sent to the model under control. Each
retrieved chunk is labeled with its source (`### Documento: nome.pdf`).

**Scope restriction**: the system prompt (two variants — one document or
multiple) instructs the model to answer strictly based on the provided
chunks, explicitly state when a piece of information isn't present in the
context, decline out-of-scope questions, and — for multiple documents —
indicate which document each piece of information came from when the
question involves comparison.

**Deletion**: removes the physical file, the ChromaDB collection, and the
metadata JSON — all three storage layers, leaving no orphaned data.

### 4.7 `pages/1_Dashboard.py` — Per-document dashboard

Independent selector from the chat selection (`dashboard_pdf_id`) — the
Dashboard always shows the summary of one document at a time. It dynamically
renders each section of the insights JSON (metrics, distribution chart, tags,
table), omitting any section that's missing or empty for that specific
document.

With no document loaded, it shows an example panel with fictional data, just
to demonstrate the layout.

The **Regenerate** button re-runs the summary extraction over the originally
stored text (not over the conversation history), and persists the result to
disk. By design, the insights model **does not use a fixed `seed`** — a
fixed value would make regeneration deterministic, always repeating the same
reading (correct or not) of the document, which would defeat the button's
purpose.

## 5. Custom Ollama models

See [`modelfiles/README.md`](modelfiles/README.en.md) for the full parameter
breakdown. Summary of the decisions:

- **`chatpdf-assistant`**: `temperature 0.3` (naturalness without rambling),
  `num_ctx 8192` (expanded context to accommodate chunks retrieved via RAG
  plus conversation history), `repeat_penalty 1.15` (avoids repetition in
  long contexts).
- **`chatpdf-insights`**: `temperature 0.05` (maximum consistency), no fixed
  `seed` (see section 4.7), limited `num_predict` (the output is a compact
  JSON).

Both models are optional — the app works normally with the plain base model
if they aren't built via `ollama create`.

## 6. Known limitations

See the "Limitations" section of [`README.md`](README.en.md) for the
consolidated list. Additional technical details:

- Insight extraction depends entirely on the local chat model's ability to
  follow formatting instructions — smaller or less capable models may
  produce malformed JSON more often (mitigated by `_validate_and_clean()`,
  but not eliminated).
- Semantic search only uses the configured embedding model
  (`nomic-embed-text`); there is no re-ranking or hybrid (lexical + vector)
  search.
- Context for multiple documents grows linearly with the number of PDFs
  checked in the conversation — there is no intermediate summarization for
  very long documents beyond what chunking already provides.

## 7. Operational notes

Environment issues (not code issues) observed during development, recorded
here for reference:

- **Activating the virtual environment in PowerShell**: use
  `.\.venv\Scripts\Activate.ps1` (not `source`, which is POSIX-shell
  specific). If the execution policy blocks the script:
  `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process`.
- **Non-ASCII filenames on Windows**: Streamlit page filenames containing
  emoji can render as garbled text in some Windows terminals. This project's
  page files use ASCII-only names for that reason.
- **Mismatch between the configured model and installed models**: a
  `model not found (404)` error from Ollama means the `CHAT_MODEL` (or
  `INSIGHTS_MODEL`) constant in the code doesn't match a model listed in
  `ollama list`.
- **Losing the virtual environment on updates**: replacing the entire
  project folder when applying an update removes `.venv/`, since it was
  never part of the versioned code. Prefer updating only the code
  files/folders (`app.py`, `pages/`, `utils/`), preserving `.venv/`,
  `.streamlit/secrets.toml`, and `data/`.

## 8. Technical roadmap

See the "Roadmap" section of [`README.md`](README.en.md).

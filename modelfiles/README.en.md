# modelfiles/ — Custom models for chatpdf-rag

🇺🇸 English | 🇧🇷 [Português](README.md)

Two models, two different purposes. Instead of using plain `llama3.2` for both
cases and relying solely on the system prompt assembled at runtime, we "bake"
a base behavior into each one via a `Modelfile` — that way the rules (language,
honesty, output format) always hold, even if the app's dynamic prompt ever
changes or gets used in a different context.

## Build

```bash
cd chatpdf-rag
ollama create chatpdf-assistant -f modelfiles/Modelfile.chat
ollama create chatpdf-insights  -f modelfiles/Modelfile.insights
```

Confirm both showed up:

```bash
ollama list
```

## How to enable in the app

Once created, swap the constants in the code (two files, two constants):

| File | Constant | New value |
|---|---|---|
| `pages/2_ChatPDF.py` | `CHAT_MODEL` | `"chatpdf-assistant:latest"` |
| `pages/2_ChatPDF.py` | `INSIGHTS_MODEL` | `"chatpdf-insights:latest"` |
| `pages/1_Dashboard.py` | `INSIGHTS_MODEL` | `"chatpdf-insights:latest"` (must match the one above) |

If you don't run `ollama create`, the app keeps working normally with plain
`llama3.2:latest` (the default value) — the custom models are an optional
upgrade, not a required dependency.

## `chatpdf-assistant` (chat)

- **Goal**: chat about the PDF naturally, but always grounded in the
  context — never "filling in" with general knowledge.
- `temperature 0.3` — low enough not to ramble, high enough not to sound
  robotic in a conversation.
- `num_ctx 8192` — the app injects up to 4 chunks (~1200 characters each) +
  conversation history on every question; Ollama's default (2048) would be
  too tight.
- `repeat_penalty 1.15` — avoids repeating whole sentences when the injected
  context is long (common with several concatenated chunks).

## `chatpdf-insights` (Dashboard extraction)

- **Goal**: read the whole PDF and return only a JSON, with no assistant
  "voice" at all — as literal and reproducible as possible.
- `temperature 0.05` — practically deterministic; here, creativity is a bug,
  not a feature.
- **No fixed `seed`, on purpose**: a fixed seed would make the extraction
  always repeat the same reading (right or wrong) for the same PDF, which
  would defeat the Dashboard's "🔄 Regenerate" button — which exists
  precisely to give it another chance when the first extraction comes out
  inconsistent.
- `num_predict 800` — insight JSONs are compact; a low limit also prevents
  the model from "continuing" past the JSON with out-of-format comments.

## Why two models instead of one

Chat and data extraction have opposite goals: one wants some conversational
naturalness, the other wants zero variation and a rigid format. A single set
of parameters would always be a bad middle ground for both cases — hence the
split.

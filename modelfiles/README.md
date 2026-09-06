# modelfiles/ — Modelos customizados do chatpdf-rag

🇧🇷 Português | 🇺🇸 [English](README.en.md)

Dois modelos, dois propósitos diferentes. Em vez de usar o `llama3.2` cru nos dois
casos e confiar só no system prompt montado em tempo de execução, "assamos" um
comportamento base de cada um via `Modelfile` — assim as regras (idioma, honestidade,
formato de saída) valem sempre, mesmo se o prompt dinâmico do app um dia mudar ou for
usado de outro contexto.

## Build

```bash
cd chatpdf-rag
ollama create chatpdf-assistant -f modelfiles/Modelfile.chat
ollama create chatpdf-insights  -f modelfiles/Modelfile.insights
```

Confirme que os dois apareceram:

```bash
ollama list
```

## Como ativar no app

Depois de criados, troque as constantes no código (dois arquivos, duas constantes):

| Arquivo | Constante | Valor novo |
|---|---|---|
| `pages/2_ChatPDF.py` | `CHAT_MODEL` | `"chatpdf-assistant:latest"` |
| `pages/2_ChatPDF.py` | `INSIGHTS_MODEL` | `"chatpdf-insights:latest"` |
| `pages/1_Dashboard.py` | `INSIGHTS_MODEL` | `"chatpdf-insights:latest"` (precisa ser igual ao de cima) |

Se você não rodar o `ollama create`, o app continua funcionando normalmente com o
`llama3.2:latest` puro (valor padrão) — os modelos customizados são um upgrade
opcional, não uma dependência obrigatória.

## `chatpdf-assistant` (chat)

- **Objetivo**: conversar sobre o PDF de forma natural, mas sempre ancorada no
  contexto — nunca "completar com conhecimento geral".
- `temperature 0.3` — baixa o suficiente para não divagar, alta o suficiente para
  não soar robótico numa conversa.
- `num_ctx 8192` — o app injeta até 4 chunks (~1200 caracteres cada) + histórico da
  conversa a cada pergunta; o padrão do Ollama (2048) ficaria apertado.
- `repeat_penalty 1.15` — evita repetição de frases quando o contexto injetado é
  longo (comum com vários chunks concatenados).

## `chatpdf-insights` (extração para o Dashboard)

- **Objetivo**: ler o PDF inteiro e devolver só um JSON, sem nenhuma "voz" de
  assistente — o mais literal e reprodutível possível.
- `temperature 0.05` — praticamente determinístico; aqui criatividade é bug, não
  feature.
- **Sem `seed` fixo, de propósito**: um seed fixo faria a extração repetir sempre a
  mesma leitura (certa ou errada) para o mesmo PDF, o que anularia o botão
  "🔄 Regenerar" do Dashboard — que existe justamente para dar uma nova chance
  quando a primeira extração sai inconsistente.
- `num_predict 800` — JSONs de insight são compactos; um limite baixo também evita
  que o modelo "continue" além do JSON com comentários fora do formato.

## Por que dois modelos e não um só

Chat e extração de dados têm objetivos opostos: um quer alguma naturalidade
conversacional, o outro quer zero variação e formato rígido. Um único conjunto de
parâmetros seria sempre um meio-termo ruim para os dois casos — daí separar.

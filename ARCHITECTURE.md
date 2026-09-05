# Arquitetura Técnica

Detalhamento de arquitetura, responsabilidades de cada módulo e decisões de
design do `chatpdf-rag`. Complementa o [`README.md`](README.md), que cobre
instalação e uso.

---

## 1. Visão geral da arquitetura

O sistema é dividido em três camadas:

- **Interface** (Streamlit, multipage): login, Dashboard, ChatPDF.
- **Processamento de documentos**: extração de texto, chunking, geração de
  embeddings, extração de resumo estruturado.
- **Persistência**: ChromaDB para embeddings, JSON para metadados — ambos em
  disco local, sem dependência de banco de dados externo.

Toda inferência de linguagem (chat, embeddings, extração de resumo) passa pelo
Ollama, rodando localmente. Não há chamadas a APIs externas em nenhum ponto do
sistema.

## 2. Stack técnica

| Componente | Uso |
|---|---|
| Streamlit | Interface, roteamento multipage nativo |
| Ollama | Modelo de chat + `nomic-embed-text` (embeddings), 100% local |
| pypdf | Extração de texto de PDF |
| ChromaDB | Índice vetorial persistido em disco |
| pandas / numpy | Manipulação de dados exibidos no Dashboard |

## 3. Estrutura de arquivos

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
├── data/uploads/        # PDFs + metadados (JSON), gerado em runtime
├── data/chroma_db/       # embeddings persistidos, gerado em runtime
└── .streamlit/secrets.toml.example
```

## 4. Módulos

### 4.1 `app.py` — Autenticação e roteamento

Tela de login com formulário usuário/senha. A sidebar fica oculta via CSS
enquanto não autenticado, para impedir navegação direta às páginas internas
antes do login. `utils/auth.py` valida contra `.streamlit/secrets.toml`; na
ausência desse arquivo, um fallback `admin`/`admin` evita travar o ambiente de
desenvolvimento local — **não recomendado além disso**.

O logout zera todo o estado de sessão relacionado a documentos e conversa
(`pdf_store`, `chat_messages`, `selected_pdf_ids`, flag de hidratação), sem
apagar nada do disco.

### 4.2 `utils/pdf_processing.py` — Extração e chunking

`extract_text()` lê o PDF página a página via `pypdf`. A função
`_rejoin_wrapped_lines()` corrige um problema comum em PDFs de duas colunas
(comum em artigos e documentos institucionais): a extração captura quebras de
linha *visuais* da coluna, não quebras reais de frase — sem correção, o texto
fica fragmentado de forma artificial, prejudicando tanto a busca semântica
quanto a extração de resumo. A função junta linhas consecutivas sem quebra em
branco real, corrigindo hifenização de fim de linha.

`chunk_text()` divide o texto corrigido em blocos de ~1200 caracteres com 150
de sobreposição, preservando contexto entre chunks adjacentes para a indexação
vetorial.

### 4.3 `utils/vector_store.py` — Índice vetorial persistido

`PDFVectorStore` mantém uma coleção ChromaDB por documento (`pdf_<id>`),
persistida em `data/chroma_db/`. Dois modos de inicialização:

- **Com `chunks`** (upload novo): cria a coleção do zero, gera embeddings via
  `ollama.embeddings(model="nomic-embed-text")` e indexa.
- **Sem `chunks`** (documento já indexado): apenas conecta à coleção
  existente, sem recalcular embeddings.

`search()` usa a busca por similaridade nativa do Chroma; `delete()` remove a
coleção inteira — a exclusão de um documento é uma única operação atômica, sem
necessidade de rastrear IDs individuais de chunks.

### 4.4 `utils/pdf_registry.py` — Metadados e hidratação de sessão

O ChromaDB persiste embeddings, mas não nome de arquivo, texto completo ou
resumo estruturado — isso fica em um JSON sidecar (`<pdf_id>.json`) ao lado de
cada PDF em `data/uploads/`.

`hydrate_session_pdf_store()` é chamada no topo de cada página: na primeira
execução de uma sessão, lê todos os metadados do disco e reconecta cada
`PDFVectorStore` correspondente (sem reprocessar embeddings), repopulando
`st.session_state.pdf_store`. Uma flag de sessão evita repetir essa
hidratação a cada rerun do Streamlit.

O histórico de conversa **não** é persistido por essa camada — cada nova
sessão inicia com o chat limpo, mas os documentos indexados e seus resumos
permanecem disponíveis.

### 4.5 `utils/pdf_insights.py` — Extração adaptativa de resumo

Gera o JSON estruturado consumido pelo Dashboard. Diferente de um schema fixo
por tipo de documento, o prompt instrui o modelo a **decidir**, a partir do
conteúdo real do texto, quais métricas, categorias e itens fazem sentido
destacar — o mesmo pipeline funciona para um currículo, um artigo acadêmico,
um contrato ou um relatório financeiro.

Schema de saída:

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

Todas as seções são opcionais e independentes. `_validate_and_clean()`
descarta qualquer seção malformada (ex: linhas de tabela com número de colunas
inconsistente) em vez de propagar o erro para a interface — um documento sem
dado categórico simplesmente não gera gráfico, por exemplo.

### 4.6 `pages/2_ChatPDF.py` — Conversa com múltiplos documentos

Fluxo de upload: extração → chunking → indexação (ChromaDB) → extração de
resumo (paralela, usada pelo Dashboard) → persistência de metadados.

**Seleção múltipla**: a sidebar exibe um checkbox por documento
(`st.session_state.selected_pdf_ids`), permitindo marcar quantos PDFs devem
participar da conversa simultaneamente. A conversa é única por sessão
(`chat_messages`), não mais uma instância por documento.

**Recuperação de contexto (RAG)**: a cada pergunta, a busca por similaridade
roda separadamente em cada documento marcado — não há uma busca combinada
única. O número de chunks recuperados por documento é reduzido conforme a
quantidade de documentos selecionados (`4` para um único documento, `max(2, 6
// n)` para múltiplos), para conter o tamanho do contexto enviado ao modelo.
Cada trecho recuperado é rotulado com sua origem (`### Documento: nome.pdf`).

**Restrição de escopo**: o system prompt (duas variantes — um documento ou
múltiplos) instrui o modelo a responder exclusivamente com base nos trechos
fornecidos, declarar explicitamente quando uma informação não está presente no
contexto, recusar perguntas fora do escopo, e — no caso de múltiplos
documentos — indicar de qual documento veio cada informação quando a pergunta
envolver comparação.

**Exclusão**: remove o arquivo físico, a coleção no ChromaDB e o JSON de
metadados — as três camadas de armazenamento, sem deixar dado órfão.

### 4.7 `pages/1_Dashboard.py` — Dashboard por documento

Seletor independente da seleção de chat (`dashboard_pdf_id`) — o Dashboard
sempre exibe o resumo de um documento por vez. Renderiza dinamicamente cada
seção do JSON de insights (métricas, gráfico de distribuição, tags, tabela),
omitindo qualquer seção ausente ou vazia para aquele documento específico.

Sem nenhum documento carregado, exibe um painel de exemplo com dados
fictícios, apenas para demonstrar o layout.

O botão **Regenerar** reexecuta a extração de resumo sobre o texto original
armazenado (não sobre o histórico de conversa), e persiste o resultado em
disco. Por decisão de design, o modelo de insights **não usa `seed` fixo** —
um valor fixo tornaria a regeneração determinística, sempre repetindo a mesma
leitura (correta ou não) do documento, o que anularia o propósito do botão.

## 5. Modelos Ollama customizados

Ver [`modelfiles/README.md`](modelfiles/README.md) para o detalhamento
completo dos parâmetros. Resumo das decisões:

- **`chatpdf-assistant`**: `temperature 0.3` (naturalidade sem divagar),
  `num_ctx 8192` (contexto ampliado para acomodar os chunks recuperados via
  RAG mais o histórico da conversa), `repeat_penalty 1.15` (evita repetição em
  contextos longos).
- **`chatpdf-insights`**: `temperature 0.05` (máxima consistência), sem `seed`
  fixo (ver seção 4.7), `num_predict` limitado (a saída é um JSON compacto).

Ambos os modelos são opcionais — o app funciona normalmente com o modelo base
puro caso não sejam construídos via `ollama create`.

## 6. Limitações conhecidas

Ver seção "Limitações" do [`README.md`](README.md) para a lista consolidada.
Detalhes técnicos adicionais:

- A extração de insights depende inteiramente da capacidade do modelo de chat
  local de seguir instruções de formatação — modelos menores ou menos
  capazes podem produzir JSON malformado com mais frequência (mitigado por
  `_validate_and_clean()`, mas não eliminado).
- A busca semântica usa apenas o modelo de embeddings configurado
  (`nomic-embed-text`); não há re-ranking nem busca híbrida (lexical +
  vetorial).
- O contexto de múltiplos documentos cresce linearmente com o número de PDFs
  marcados na conversa — não há sumarização intermediária para documentos
  muito longos além do que o chunking já provê.

## 7. Notas operacionais

Problemas de ambiente (não de código) observados durante o desenvolvimento,
registrados aqui para referência:

- **Ativação de ambiente virtual no PowerShell**: usar
  `.\.venv\Scripts\Activate.ps1` (não `source`, específico de shells POSIX).
  Se a política de execução bloquear o script:
  `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process`.
- **Nomes de arquivo com caracteres não-ASCII no Windows**: nomes de página do
  Streamlit contendo emoji podem ser exibidos corrompidos em alguns terminais
  Windows. Os arquivos de página deste projeto usam apenas ASCII no nome por
  esse motivo.
- **Divergência entre o modelo configurado e os modelos instalados**: um erro
  `model not found (404)` do Ollama indica que a constante `CHAT_MODEL` (ou
  `INSIGHTS_MODEL`) no código não corresponde a um modelo listado em
  `ollama list`.
- **Perda do ambiente virtual em atualizações**: substituir a pasta do projeto
  inteira ao aplicar uma atualização remove `.venv/`, já que ele nunca fez
  parte do código versionado. Prefira atualizar apenas os arquivos/pastas de
  código (`app.py`, `pages/`, `utils/`), preservando `.venv/`,
  `.streamlit/secrets.toml` e `data/`.

## 8. Roadmap técnico

Ver seção "Roadmap" do [`README.md`](README.md).

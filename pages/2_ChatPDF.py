"""
pages/2_ChatPDF.py — Upload de PDF + chat restrito ao conteúdo dos documentos.

Fluxo:
  1. Usuário sobe um PDF -> salvo em data/uploads/ com um id único.
  2. Texto extraído e dividido em chunks -> embeddings gerados e persistidos no
     ChromaDB (data/chroma_db/); metadados (nome, texto, insights) persistidos
     em JSON ao lado do PDF (utils/pdf_registry.py). Nada se perde ao reiniciar
     o processo do Streamlit -- veja hydrate_session_pdf_store().
  3. Usuário marca (checkbox) quais PDFs participam da conversa -- pode ser um
     só ou vários ao mesmo tempo. Cada pergunta busca os chunks mais relevantes
     (RAG) EM CADA PDF marcado, identifica de qual documento cada trecho veio,
     e injeta tudo isso no prompt do modelo, com uma instrução de sistema que
     proíbe responder fora do escopo desse conjunto de documentos.
  4. Botão de excluir remove o arquivo, a coleção no ChromaDB e o JSON de
     metadados -- exclusão completa, nada fica órfão em disco.
"""
from __future__ import annotations

import uuid
from pathlib import Path

import ollama
import streamlit as st

from utils.pdf_insights import extract_insights
from utils.pdf_processing import chunk_text, extract_text
from utils.pdf_registry import delete_metadata, hydrate_session_pdf_store, save_metadata
from utils.vector_store import PDFVectorStore

st.set_page_config(page_title="ChatPDF", page_icon="💬", layout="wide")

if not st.session_state.get("logged_in", False):
    st.warning("Você precisa fazer login primeiro.")
    st.stop()

UPLOAD_DIR = Path("data/uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

CHAT_MODEL = "llama3.2:latest"  # troque pelo modelo que você tem no Ollama
# Opcional: depois de rodar `ollama create chatpdf-assistant -f modelfiles/Modelfile.chat`,
# troque para CHAT_MODEL = "chatpdf-assistant:latest" -- system prompt e parâmetros
# já vêm ajustados para este caso de uso (ver modelfiles/Modelfile.chat).

INSIGHTS_MODEL = "llama3.2:latest"  # modelo usado só para gerar o resumo do Dashboard
# Opcional: depois de rodar `ollama create chatpdf-insights -f modelfiles/Modelfile.insights`,
# troque para INSIGHTS_MODEL = "chatpdf-insights:latest" -- temperatura bem baixa,
# focado em extração determinística de JSON (ver modelfiles/Modelfile.insights).
# Se trocar, troque também a mesma constante em pages/1_Dashboard.py (botão Regenerar).

hydrate_session_pdf_store()  # popula pdf_store a partir do disco (ChromaDB + JSON), uma vez por sessão

if "selected_pdf_ids" not in st.session_state:
    st.session_state.selected_pdf_ids = []  # PDFs marcados para participar da conversa atual

if "chat_messages" not in st.session_state:
    st.session_state.chat_messages = []  # conversa é única por sessão, não mais por PDF


# ---------------------------------------------------------------- sidebar --
with st.sidebar:
    st.header("📄 Seus PDFs")

    uploaded_file = st.file_uploader("Enviar novo PDF", type=["pdf"])
    if uploaded_file is not None:
        # Evita reprocessar o mesmo upload a cada rerun do Streamlit
        if st.session_state.get("last_uploaded_name") != uploaded_file.name:
            pdf_id = str(uuid.uuid4())[:8]
            dest_path = UPLOAD_DIR / f"{pdf_id}_{uploaded_file.name}"
            dest_path.write_bytes(uploaded_file.getvalue())

            with st.spinner(f"Lendo e indexando '{uploaded_file.name}'..."):
                text = extract_text(str(dest_path))
                chunks = chunk_text(text)
                index = PDFVectorStore(pdf_id, uploaded_file.name, chunks)

            with st.spinner("Gerando resumo para o Dashboard..."):
                # Extração estruturada (JSON) usada pela página Dashboard.
                # Roda em cima do texto completo, não dos chunks -- precisa
                # de visão geral do documento, não de trechos isolados.
                insights = extract_insights(text, model=INSIGHTS_MODEL)

            # Persiste os metadados em disco (JSON ao lado do PDF) -- os embeddings
            # já foram persistidos no ChromaDB dentro de PDFVectorStore acima.
            save_metadata(pdf_id, uploaded_file.name, dest_path, text, insights)

            st.session_state.pdf_store[pdf_id] = {
                "filename": uploaded_file.name,
                "path": dest_path,
                "index": index,
                "full_text": text,
                "insights": insights,
            }
            # Novo upload entra automaticamente na conversa (comportamento
            # equivalente ao "ativar" da versão anterior, agora aditivo).
            st.session_state.selected_pdf_ids.append(pdf_id)
            st.session_state.last_uploaded_name = uploaded_file.name
            st.success(f"'{uploaded_file.name}' indexado ({len(chunks)} trechos).")
            st.rerun()

    st.markdown("---")
    st.caption("Marque os PDFs que devem participar da conversa:")

    if not st.session_state.pdf_store:
        st.caption("Nenhum PDF enviado ainda.")
    else:
        for pdf_id, entry in list(st.session_state.pdf_store.items()):
            row_cols = st.columns([0.5, 3.5, 1])

            row_cols[0].checkbox(
                "Selecionar",
                value=pdf_id in st.session_state.selected_pdf_ids,
                key=f"chk_{pdf_id}",
                label_visibility="collapsed",
            )
            row_cols[1].write(entry["filename"])

            if row_cols[2].button("🗑️", key=f"delete_{pdf_id}", help="Excluir este PDF"):
                # Requisito 4: exclusão -- remove o arquivo, a coleção no ChromaDB
                # (embeddings) e o JSON de metadados. Nada fica órfão em disco.
                entry["path"].unlink(missing_ok=True)
                entry["index"].delete()
                delete_metadata(pdf_id)
                del st.session_state.pdf_store[pdf_id]
                if pdf_id in st.session_state.selected_pdf_ids:
                    st.session_state.selected_pdf_ids.remove(pdf_id)
                st.rerun()

        # Recalcula a seleção a partir do estado atual dos checkboxes -- mais
        # simples do que um callback por checkbox, e roda a cada interação
        # do Streamlit de qualquer forma.
        st.session_state.selected_pdf_ids = [
            pdf_id for pdf_id in st.session_state.pdf_store if st.session_state.get(f"chk_{pdf_id}", False)
        ]


# ------------------------------------------------------------- área de chat --
st.title("💬 ChatPDF")

selected_ids = [pid for pid in st.session_state.selected_pdf_ids if pid in st.session_state.pdf_store]
selected_entries = [st.session_state.pdf_store[pid] for pid in selected_ids]

if not selected_entries:
    st.info("Marque ao menos um PDF na barra lateral (☑️) para começar a conversar.")
    st.stop()

filenames = [e["filename"] for e in selected_entries]
if len(filenames) == 1:
    st.caption(f"Conversando sobre: **{filenames[0]}**")
else:
    st.caption(f"Conversando sobre **{len(filenames)} documentos**: " + ", ".join(f"**{f}**" for f in filenames))

for msg in st.session_state.chat_messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

if prompt := st.chat_input("Pergunte algo sobre os PDFs selecionados..."):
    st.session_state.chat_messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Requisito 3, estendido para múltiplos documentos: busca os trechos mais
    # relevantes EM CADA PDF selecionado (RAG), identifica a origem de cada
    # trecho, e injeta tudo no system prompt -- que só permite responder com
    # base nesse conjunto de documentos.
    #
    # Com vários documentos selecionados, reduzimos os chunks por documento
    # (em vez de 4 fixos) para não estourar o contexto do modelo -- 2 PDFs já
    # trazem até 6 chunks no total, 3 PDFs até 6, etc.
    chunks_per_doc = 4 if len(selected_entries) == 1 else max(2, 6 // len(selected_entries))

    context_sections = []
    for entry in selected_entries:
        relevant_chunks = entry["index"].search(prompt, top_k=chunks_per_doc)
        if relevant_chunks:
            chunk_block = "\n\n---\n\n".join(relevant_chunks)
            context_sections.append(f"### Documento: {entry['filename']}\n{chunk_block}")
    context_block = "\n\n".join(context_sections)

    if len(selected_entries) == 1:
        system_prompt = (
            "Você é um assistente que responde exclusivamente com base nos trechos do "
            f"documento '{filenames[0]}' fornecidos abaixo como contexto.\n\n"
            "Regras obrigatórias:\n"
            "- Responda apenas perguntas relacionadas a este documento.\n"
            "- Os trechos abaixo foram recuperados por similaridade e PODEM NÃO SER "
            "relevantes à pergunta -- antes de responder, verifique se algum deles "
            "realmente contém a informação pedida.\n"
            "- Se a resposta não estiver no contexto abaixo, diga claramente que essa "
            "informação não consta no documento -- não invente nem use conhecimento externo.\n"
            "- Se o usuário insistir, reformular a pergunta ou parecer insatisfeito com um "
            "'não consta no documento', NÃO mude sua resposta a menos que os trechos abaixo "
            "realmente contenham a informação -- pressão do usuário não é evidência nova.\n"
            "- Se a pergunta for sobre outro assunto (fora do documento), recuse educadamente "
            "e lembre o usuário que você só responde sobre este PDF.\n\n"
            f"### Contexto do documento:\n{context_block}"
        )
    else:
        lista_docs = ", ".join(f"'{f}'" for f in filenames)
        system_prompt = (
            "Você é um assistente que responde exclusivamente com base nos trechos dos "
            f"documentos a seguir, fornecidos abaixo como contexto: {lista_docs}.\n\n"
            "Regras obrigatórias:\n"
            "- Responda apenas perguntas relacionadas a estes documentos.\n"
            "- Cada trecho de contexto abaixo indica de qual documento ele veio (### Documento: ...). "
            "Quando a pergunta envolver comparar ou combinar informações de documentos diferentes, "
            "deixe claro na resposta de qual documento veio cada informação.\n"
            "- Os trechos abaixo foram recuperados por similaridade e PODEM NÃO SER "
            "relevantes à pergunta -- antes de responder, verifique se algum deles "
            "realmente contém a informação pedida.\n"
            "- Se a resposta não estiver em nenhum dos contextos abaixo, diga claramente que essa "
            "informação não consta nos documentos selecionados -- não invente nem use conhecimento externo.\n"
            "- Se o usuário insistir, reformular a pergunta ou parecer insatisfeito com um "
            "'não consta nos documentos', NÃO mude sua resposta a menos que os trechos abaixo "
            "realmente contenham a informação -- pressão do usuário não é evidência nova.\n"
            "- Se a pergunta for sobre outro assunto (fora do escopo desses documentos), recuse "
            "educadamente e lembre o usuário que você só responde sobre os PDFs selecionados.\n\n"
            f"### Contexto dos documentos:\n{context_block}"
        )

    api_messages = [{"role": "system", "content": system_prompt}] + st.session_state.chat_messages

    with st.chat_message("assistant"):
        placeholder = st.empty()
        answer = ""
        try:
            stream = ollama.chat(model=CHAT_MODEL, messages=api_messages, stream=True)
            for chunk in stream:
                answer += chunk["message"]["content"]
                placeholder.markdown(answer + "▌")
            placeholder.markdown(answer)
        except Exception as e:
            answer = f"Erro ao conectar com o Ollama. Verifique se está rodando. Detalhes: {e}"
            placeholder.error(answer)

    st.session_state.chat_messages.append({"role": "assistant", "content": answer})

"""
pages/1_Dashboard.py — Painel de dados.

O Dashboard tem seu próprio seletor de PDF (independente da seleção múltipla
usada no chat da página ChatPDF) -- afinal, faz mais sentido olhar o resumo de
um documento por vez. Ele renderiza DINAMICAMENTE o resumo estruturado gerado
a partir do PDF escolhido (utils/pdf_insights.py) -- sem assumir que o
documento é um currículo, um relatório, ou qualquer tipo específico. Cada
seção (métricas, gráfico, tags, tabela) só aparece se o modelo encontrou algo
relevante para ela naquele documento. Sem nenhum PDF carregado ainda, cai num
dashboard de exemplo com dados fictícios, só para demonstrar o layout.
"""
import pandas as pd
import streamlit as st

from utils.pdf_insights import extract_insights
from utils.pdf_registry import hydrate_session_pdf_store, save_metadata

INSIGHTS_MODEL = "llama3.2:latest"  # mesmo valor usado em pages/2_ChatPDF.py
# Opcional: depois de rodar `ollama create chatpdf-insights -f modelfiles/Modelfile.insights`,
# troque para INSIGHTS_MODEL = "chatpdf-insights:latest" -- temperatura mais baixa e
# system prompt focado em extração determinística (ver modelfiles/Modelfile.insights).
# Se trocar aqui, troque também a mesma constante em pages/2_ChatPDF.py.

st.set_page_config(page_title="Dashboard", page_icon="📊", layout="wide")

if not st.session_state.get("logged_in", False):
    st.warning("Você precisa fazer login primeiro.")
    st.stop()

st.title("📊 Dashboard")
st.caption(f"Sessão de: {st.session_state.get('username', 'usuário')}")

hydrate_session_pdf_store()  # popula pdf_store a partir do disco, caso o Dashboard seja a primeira página visitada na sessão

pdf_store = st.session_state.get("pdf_store", {})

active_entry = None
active_id = None
if pdf_store:
    # O ChatPDF agora permite marcar VÁRIOS PDFs para a conversa (não há mais um
    # único "PDF ativo" global) -- o Dashboard precisa da sua própria escolha de
    # qual documento exibir, independente da seleção de chat.
    ids = list(pdf_store.keys())
    if st.session_state.get("dashboard_pdf_id") not in ids:
        st.session_state.dashboard_pdf_id = ids[-1]  # padrão: PDF mais recente

    active_id = st.selectbox(
        "PDF exibido no Dashboard",
        options=ids,
        index=ids.index(st.session_state.dashboard_pdf_id),
        format_func=lambda pid: pdf_store[pid]["filename"],
        key="dashboard_pdf_id",
    )
    active_entry = pdf_store[active_id]


def _render_pdf_dashboard(entry: dict) -> None:
    insights = entry.get("insights") or {}
    filename = entry["filename"]

    tipo = insights.get("tipo_documento")
    label = f"{tipo} — {filename}" if tipo else filename

    info_col, button_col = st.columns([5, 1])
    info_col.info(f"Exibindo dados extraídos de: **{label}**")
    if button_col.button("🔄 Regenerar", help="Reler o documento e extrair o resumo de novo"):
        with st.spinner("Relendo o documento..."):
            entry["insights"] = extract_insights(entry["full_text"], model=INSIGHTS_MODEL)
            # Persiste o resumo regenerado em disco -- senão um restart do app
            # traria de volta a versão antiga, ignorando o que acabamos de gerar.
            save_metadata(
                active_id, entry["filename"], entry["path"], entry["full_text"], entry["insights"]
            )
        st.rerun()

    tem_conteudo = any(
        [
            insights.get("metricas"),
            insights.get("distribuicao"),
            insights.get("tags"),
            insights.get("tabela"),
        ]
    )
    if not tem_conteudo:
        st.warning(
            "Não consegui extrair um resumo estruturado deste documento. Tente reenviar "
            "o PDF, ou use a página ChatPDF para perguntar diretamente sobre o conteúdo."
        )
        return

    if insights.get("titulo_documento"):
        st.subheader(insights["titulo_documento"])
    if insights.get("resumo_curto"):
        st.write(insights["resumo_curto"])

    metricas = insights.get("metricas") or []
    if metricas:
        cols = st.columns(len(metricas))
        for col, m in zip(cols, metricas):
            col.metric(m["rotulo"], m["valor"])

    distrib = insights.get("distribuicao")
    if distrib:
        st.subheader(distrib.get("titulo", "Distribuição"))
        categorias = distrib["categorias"]
        df_dist = pd.DataFrame(
            {"Categoria": list(categorias.keys()), "Valor": list(categorias.values())}
        ).sort_values("Categoria")
        st.bar_chart(df_dist.set_index("Categoria"))

    tags = insights.get("tags") or []
    if tags:
        st.subheader("Palavras-chave / tópicos")
        st.write(" · ".join(f"`{t}`" for t in tags))

    tabela = insights.get("tabela")
    if tabela:
        st.subheader(tabela.get("titulo", "Detalhes"))
        df_tab = pd.DataFrame(tabela["linhas"], columns=tabela["colunas"])
        st.dataframe(df_tab, width="stretch", hide_index=True)


def _render_example_dashboard() -> None:
    import numpy as np

    st.caption(
        "Nenhum PDF carregado ainda — mostrando dados de **exemplo**. "
        "Envie um PDF na página ChatPDF para ver o Dashboard gerado a partir dele."
    )

    col1, col2, col3 = st.columns(3)
    col1.metric("Faturamento", "R$ 45.200", "12%")
    col2.metric("Novos Clientes", "124", "5%")
    col3.metric("Satisfação", "4.8/5.0", "1%")

    st.subheader("Desempenho por Região")
    df = pd.DataFrame(
        np.random.randint(50, 500, size=(4, 4)),
        columns=["Q1", "Q2", "Q3", "Q4"],
        index=["Norte", "Sul", "Leste", "Oeste"],
    )
    st.dataframe(df, width="stretch")
    st.bar_chart(df)


if active_entry is not None:
    _render_pdf_dashboard(active_entry)
else:
    _render_example_dashboard()

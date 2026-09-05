"""
utils/pdf_insights.py — Extrai um resumo ESTRUTURADO e ADAPTATIVO (JSON) do PDF via LLM,
para alimentar o Dashboard com dados reais do documento carregado -- seja ele um
currículo, um artigo acadêmico, um contrato, um relatório financeiro, etc.

Diferente de um schema fixo (ex: "anos de experiência"), aqui o modelo decide QUAIS
métricas, categorias e itens fazem sentido para o documento em questão. O Dashboard
(pages/1_Dashboard.py) renderiza o que vier, de forma genérica.
"""
from __future__ import annotations

import json
import re

import ollama

INSIGHTS_SCHEMA_PROMPT = """Você recebe o texto de um documento PDF de tipo desconhecido
(pode ser um currículo, artigo acadêmico, contrato, relatório financeiro, manual técnico,
ata de reunião, etc). Sua tarefa é decidir, com base no CONTEÚDO REAL do documento, quais
métricas e informações fazem mais sentido destacar em um dashboard resumido.

Devolva **APENAS** um JSON válido (sem markdown, sem texto antes ou depois), neste formato:

{
  "titulo_documento": "título curto descrevendo do que se trata o documento",
  "tipo_documento": "classificação livre e curta, ex: 'Currículo', 'Artigo científico', 'Contrato', 'Relatório financeiro'",
  "resumo_curto": "1 a 2 frases resumindo o documento",
  "metricas": [
    {"rotulo": "nome curto da métrica", "valor": "número ou texto curto"}
  ],
  "distribuicao": {
    "titulo": "título do gráfico, ex: 'Certificações por ano' ou 'Gastos por categoria'",
    "categorias": {"categoria1": number, "categoria2": number}
  },
  "tags": ["palavras-chave ou tópicos relevantes, até 12"],
  "tabela": {
    "titulo": "título da tabela, ex: 'Experiência profissional' ou 'Itens do contrato'",
    "colunas": ["Coluna 1", "Coluna 2"],
    "linhas": [["valor1", "valor2"], ["valor1", "valor2"]]
  }
}

Regras:
- "metricas": escolha de 2 a 6 métricas REALMENTE presentes ou calculáveis a partir do
  texto (contagens, totais, datas, valores). Nunca invente números que não estejam no
  documento nem sejam uma contagem direta de itens nele.
- "distribuicao": só inclua se houver uma quebra categórica clara e útil (ex: itens por
  ano, valores por categoria). Se não houver nada assim, use null.
- "tabela": só inclua se houver uma lista de itens estruturáveis (experiências, cláusulas,
  seções, produtos). Todas as linhas devem ter o mesmo número de valores que "colunas".
  Se não houver nada assim, use null.
- "tags": até 12 palavras/termos curtos relevantes (habilidades, tópicos, partes
  envolvidas, etc conforme o tipo de documento). Use [] se não houver nada relevante.
- Nunca invente dados que não estejam no texto. Responda em português."""


def _extract_json_block(raw: str) -> dict:
    """O modelo às vezes envolve o JSON em ```json ... ``` mesmo quando instruído a não
    fazer isso -- essa função tenta extrair o primeiro bloco {...} válido."""
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?", "", raw).strip()
    raw = re.sub(r"```$", "", raw).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise


def _empty_insights() -> dict:
    return {
        "titulo_documento": "",
        "tipo_documento": "",
        "resumo_curto": "",
        "metricas": [],
        "distribuicao": None,
        "tags": [],
        "tabela": None,
    }


def _validate_and_clean(data: dict) -> dict:
    """Sanitiza o que o modelo devolveu: descarta seções malformadas em vez de
    deixar a página quebrar. Cada seção é opcional e independente das outras."""
    clean = _empty_insights()

    if isinstance(data.get("titulo_documento"), str):
        clean["titulo_documento"] = data["titulo_documento"]
    if isinstance(data.get("tipo_documento"), str):
        clean["tipo_documento"] = data["tipo_documento"]
    if isinstance(data.get("resumo_curto"), str):
        clean["resumo_curto"] = data["resumo_curto"]

    metricas = data.get("metricas")
    if isinstance(metricas, list):
        clean["metricas"] = [
            {"rotulo": str(m.get("rotulo", "")), "valor": m.get("valor", "")}
            for m in metricas
            if isinstance(m, dict) and m.get("rotulo")
        ][:6]

    distrib = data.get("distribuicao")
    if isinstance(distrib, dict) and isinstance(distrib.get("categorias"), dict):
        categorias = {
            str(k): v for k, v in distrib["categorias"].items() if isinstance(v, (int, float))
        }
        if categorias:
            clean["distribuicao"] = {
                "titulo": str(distrib.get("titulo", "Distribuição")),
                "categorias": categorias,
            }

    tags = data.get("tags")
    if isinstance(tags, list):
        clean["tags"] = [str(t) for t in tags if isinstance(t, (str, int, float))][:12]

    tabela = data.get("tabela")
    if isinstance(tabela, dict):
        colunas = tabela.get("colunas")
        linhas = tabela.get("linhas")
        if isinstance(colunas, list) and isinstance(linhas, list) and colunas:
            linhas_validas = [
                row for row in linhas if isinstance(row, list) and len(row) == len(colunas)
            ]
            if linhas_validas:
                clean["tabela"] = {
                    "titulo": str(tabela.get("titulo", "Detalhes")),
                    "colunas": [str(c) for c in colunas],
                    "linhas": linhas_validas,
                }

    return clean


def extract_insights(full_text: str, model: str) -> dict:
    """Chama o modelo de chat para extrair o JSON adaptativo. Em caso de falha
    de parsing ou resposta malformada, devolve uma estrutura vazia em vez de
    quebrar a página -- o Dashboard trata isso mostrando um aviso."""
    try:
        response = ollama.chat(
            model=model,
            messages=[
                {"role": "system", "content": INSIGHTS_SCHEMA_PROMPT},
                {"role": "user", "content": full_text[:12000]},  # limite de segurança
            ],
            options={"temperature": 0.1},
        )
        content = response.get("message", {}).get("content", "")
        data = _extract_json_block(content)
        return _validate_and_clean(data)
    except Exception:
        return _empty_insights()

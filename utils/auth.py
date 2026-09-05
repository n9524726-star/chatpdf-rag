"""
utils/auth.py — Checagem de credenciais.

Para um protótipo, credenciais ficam em .streamlit/secrets.toml (nunca versionado
— veja .gitignore). Para produção real, troque por streamlit-authenticator
(hash de senha + cookies) ou um provedor de identidade (OAuth/SSO).
"""
import streamlit as st


def check_credentials(username: str, password: str) -> bool:
    """Compara com as credenciais definidas em st.secrets.

    Formato esperado em .streamlit/secrets.toml:

        [auth]
        username = "admin"
        password = "troque-esta-senha"

    Se secrets.toml não existir (ex: ainda não configurado), cai em um
    fallback admin/admin só para não travar o desenvolvimento local —
    troque isso antes de expor a aplicação fora da sua máquina.
    """
    try:
        expected_user = st.secrets["auth"]["username"]
        expected_pass = st.secrets["auth"]["password"]
    except (KeyError, FileNotFoundError):
        expected_user, expected_pass = "admin", "admin"

    return username == expected_user and password == expected_pass

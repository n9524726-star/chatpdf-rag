"""
app.py — Ponto de entrada da aplicação.

Responsável apenas pelo controle de acesso (login). Depois de autenticado,
o Streamlit expõe automaticamente as páginas em pages/ na barra lateral
(Dashboard e ChatPDF).
"""
import streamlit as st

from utils.auth import check_credentials

st.set_page_config(page_title="ChatPDF App", page_icon="🔒", layout="wide")

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False


def _hide_sidebar_css() -> None:
    """Esconde a sidebar (e o botão de expandir) enquanto não autenticado,
    para impedir que o usuário navegue direto para pages/ pela URL/atalho."""
    st.markdown(
        """
        <style>
            [data-testid="collapsedControl"] { display: none; }
            [data-testid="stSidebar"] { display: none; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def login_screen() -> None:
    _hide_sidebar_css()
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.title("🔒 Acesso Restrito")
        st.caption("Entre com suas credenciais para acessar o Dashboard e o ChatPDF.")

        with st.form("login_form"):
            username = st.text_input("Usuário")
            password = st.text_input("Senha", type="password")
            submitted = st.form_submit_button("Entrar", use_container_width=True)

            if submitted:
                if check_credentials(username, password):
                    st.session_state.logged_in = True
                    st.session_state.username = username
                    st.rerun()
                else:
                    st.error("Usuário ou senha incorretos.")


def welcome_screen() -> None:
    st.title(f"🚀 Bem-vindo, {st.session_state.get('username', 'usuário')}!")
    st.write("Use a barra lateral para acessar o **Dashboard** ou o **ChatPDF**.")
    if st.button("Sair (Logout)"):
        # Zera tudo que for específico da sessão autenticada
        for key in (
            "logged_in",
            "username",
            "chat_messages",
            "pdf_store",
            "_pdf_store_hydrated",
            "selected_pdf_ids",
        ):
            st.session_state.pop(key, None)
        st.rerun()


if not st.session_state.logged_in:
    login_screen()
else:
    welcome_screen()

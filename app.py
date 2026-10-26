import streamlit as st
import pandas as pd
import pdfplumber
import re
import uuid
import httpx

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from supabase import create_client


st.set_page_config(
    page_title="Controle de Exames",
    layout="wide"
)

url = "https://dpouzkapdaipnfnlsrio.supabase.co"
key = "sb_publishable_hhN-A_o0Q9Y6o8lTGr2xCw_iBbSSXca"

if "supabase_client" not in st.session_state:
    st.session_state.supabase_client = create_client(url, key)

supabase = st.session_state.supabase_client


def eh_timeout_ou_erro_conexao(erro):
    texto = str(erro).lower()
    return (
        isinstance(
            erro,
            (
                httpx.ReadTimeout,
                httpx.ConnectTimeout,
                httpx.ConnectError
            )
        )
        or "readtimeout" in texto
        or "connecttimeout" in texto
        or "connecterror" in texto
        or "timed out" in texto
    )


def executar_com_tentativa(funcao, tentativas=2):
    ultimo_erro = None
    for tentativa in range(tentativas):
        try:
            return funcao()
        except Exception as erro:
            ultimo_erro = erro
            if not eh_timeout_ou_erro_conexao(erro):
                raise
    raise ultimo_erro


if "modal_mensagem" not in st.session_state:
    st.session_state.modal_mensagem = None

if "modal_titulo" not in st.session_state:
    st.session_state.modal_titulo = "Aviso"

if "modal_tipo" not in st.session_state:
    st.session_state.modal_tipo = "info"


def abrir_modal(mensagem, titulo="Aviso", tipo="info"):
    st.session_state.modal_mensagem = mensagem
    st.session_state.modal_titulo = titulo
    st.session_state.modal_tipo = tipo


@st.dialog("Aviso", dismissible=False)
def mostrar_modal_mensagem():
    titulo = st.session_state.modal_titulo
    mensagem = st.session_state.modal_mensagem
    tipo = st.session_state.modal_tipo

    st.subheader(titulo)

    if tipo == "success":
        st.success(mensagem)
    elif tipo == "warning":
        st.warning(mensagem)
    elif tipo == "error":
        st.error(mensagem)
    else:
        st.info(mensagem)

    st.divider()

    if st.button(
        "OK, entendi",
        key="botao_ok_modal_mensagem",
        use_container_width=True
    ):

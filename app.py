import streamlit as st
import pandas as pd
import pdfplumber
import re
from datetime import datetime, timedelta
from supabase import create_client

# 🔑 SUPABASE
url = "https://dpouzkapdaipnfnlsrio.supabase.co"
key = "sb_publishable_hhN-A_o0Q9Y6o8lTGr2xCw_iBbSSXca"
supabase = create_client(url, key)

st.set_page_config(page_title="Controle de Exames", layout="wide")

# ================= LOGIN =================

if "user" not in st.session_state:
    st.session_state.user = None

st.title("Sistema de Controle de Exames")

if not st.session_state.user:
    st.subheader("Login")

    email = st.text_input("Email")
    senha = st.text_input("Senha", type="password")

    col1, col2 = st.columns(2)

    with col1:
        if st.button("Entrar"):
            try:
                user = supabase.auth.sign_in_with_password({
                    "email": email,
                    "password": senha
                })
                st.session_state.user = user
                st.rerun()
            except Exception as e:
                st.error(f"Erro no login: {e}")

    with col2:
        if st.button("Cadastrar"):
            try:
                supabase.auth.sign_up({
                    "email": email,
                    "password": senha
                })
                st.success("Usuário criado! Agora clique em entrar.")
            except Exception as e:
                st.error(f"Erro ao cadastrar: {e}")

    st.stop()

user_id = st.session_state.user.user.id

# ================= FUNÇÕES DE PDF =================

def identificar_exame(texto):
    if texto.lower().count("resultado") > 5:
        return "LAUDO PRÉ TRANSPLANTE"

    linhas = texto.split("\n")
    palavras_chave = [
        "ELETROCARDIOGRAMA","ULTRASSONOGRAFIA","ENDOSCOPIA",
        "ECOCARDIOGRAMA","TESTE ERGOMÉTRICO","TESTE ERGOMETRICO",
        "DOPPLER","HEMODINÂMICO","HEMODINAMICO",
        "CORONARIOGRAFIA","CATETERISMO"
    ]

    for linha in linhas:
        linha_limpa = linha.strip()
        for palavra in palavras_chave:
            if palavra in linha_limpa.upper():
                return linha_limpa.upper()

    texto = texto.lower()
    if "endoscopia" in texto or "eda" in texto:
        return "ENDOSCOPIA"
    if "ecocardiograma" in texto or "ecocardiografia" in texto:
        return "ECOCARDIOGRAMA"
    if "ultrassom" in texto or "ultrassonografia" in texto:
        return "ULTRASSOM"
    if "pré tx" in texto or "pre tx" in texto:
        return "LAUDO PRÉ TRANSPLANTE"
    return "EXAME"

def limpar_nome(nome):
    nome = nome.split("\n")[0]
    nome = re.split(r'Origem|Sexo|Idade|Nascimento|Dt\.|Convênio', nome)[0]
    return nome.strip()

def ler_pdf(arquivo):
    texto = ""
    with pdfplumber.open(arquivo) as pdf:
        for page in pdf.pages:
            conteudo = page.extract_text()
            if conteudo:
                texto += conteudo + "\n"

    cpf = None
    cpf_match = re.search(r'CPF[:\s]*([0-9\.\-]{11,14})', texto)
    if cpf_match:
        cpf = cpf_match.group(1)

    nome = None
    padroes_nome = [
        r'Nome Civil:\s*(.*)',
        r'Nome\s*\.{0,}\s*:\s*(.*)',
        r'Paciente:\s*(.*)'
    ]
    for padrao in padroes_nome:
        match = re.search(padrao, texto)
        if match:
            nome = limpar_nome(match.group(1).strip())
            break

    data_exame = None
    padroes_data = [
        r'Data do exame[:\s]*([0-9]{2}/[0-9]{2}/[0-9]{4})',
        r'Data realização[:\s]*([0-9]{2}/[0-9]{2}/[0-9]{4})',
        r'Realização[:\s]*([0-9]{2}/[0-9]{2}/[0-9]{4})',
        r'Emissão do laudo[:\s]*([0-9]{2}/[0-9]{2}/[0-9]{4})'
    ]
    for padrao in padroes_data:
        match = re.search(padrao, texto, re.IGNORECASE)
        if match:
            data_exame = datetime.strptime(match.group(1), "%d/%m/%Y")
            break
    if not data_exame:
        for linha in texto.split("\n"):
            if "nasc" in linha.lower():
                continue
            match = re.search(r'\d{2}/\d{2}/\d{4}', linha)
            if match:
                data_exame = datetime.strptime(match.group(0), "%d/%m/%Y")
                break

    tipo_exame = identificar_exame(texto)

    # ===== PRONTUÁRIO / REGISTRO =====
    prontuario_registro = None
    match_prontuario = re.search(r'Prontu[aá]rio[:\s]*([0-9/]+)', texto, re.IGNORECASE)
    if match_prontuario:
        prontuario_registro = re.sub(r'\D', '', match_prontuario.group(1))
    if not prontuario_registro:
        match_registro = re.search(r'Registro.*?([0-9]{5,})', texto, re.IGNORECASE)
        if match_registro:
            prontuario_registro = match_registro.group(1)
        if not prontuario_registro:
            match_registro2 = re.search(r'Registro.*?\n\s*([0-9]{5,})', texto, re.IGNORECASE)
            if match_registro2:
                prontuario_registro = match_registro2.group(1)
        if not prontuario_registro:
            match_resultado = re.search(r'RESULTADOS\s*\n\s*([0-9]{5,})', texto, re.IGNORECASE)
            if match_resultado:
                prontuario_registro = match_resultado.group(1)

    return cpf, nome, data_exame, tipo_exame, prontuario_registro

def calcular_status(data_vencimento):
    hoje = datetime.today()
    if hoje > data_vencimento:
        return "🔴 VENCIDO"
    if (data_vencimento - hoje).days <= 30:
        return "🟡 EM ALERTA"
    return "🟢 VALIDO"

# ================= CARREGAR DADOS =================
res = supabase.table("exames").select("*").eq("hospital_id", user_id).execute()
df = pd.DataFrame(res.data)

if df.empty:
    df = pd.DataFrame(columns=[
        "cpf", "paciente", "prontuario_registro", "exame",
        "data_exame", "data_vencimento", "status"
    ])

# ================= DASHBOARD =================
vencidos = len(df[df["status"].str.contains("VENCIDO", na=False)])
alerta = len(df[df["status"].str.contains("ALERTA", na=False)])
validos = len(df[df["status"].str.contains("VALIDO", na=False)])

c1, c2, c3 = st.columns(3)
c1.metric("🔴 VENCIDOS", vencidos)
c2.metric("🟡 EM ALERTA", alerta)
c3.metric("🟢 VÁLIDOS", validos)

st.divider()

# ================= UPLOAD =================
arquivos = st.file_uploader("Selecionar PDFs", type=["pdf"], accept_multiple_files=True)

if st.button("Ler exames"):

    if not arquivos:
        st.warning("Nenhum PDF selecionado")
    else:
        novos = []
        for arquivo in arquivos:
            cpf, nome, data_exame, tipo_exame, prontuario_registro = ler_pdf(arquivo)
            if not data_exame:
                st.warning(f"Data não encontrada em {arquivo.name}")
                continue
            data_vencimento = data_exame + timedelta(days=180)
            status = calcular_status(data_vencimento)
            novos.append({
                "hospital_id": user_id,
                "cpf": cpf,
                "paciente": nome,
                "prontuario_registro": prontuario_registro,
                "exame": tipo_exame,
                "data_exame": data_exame.strftime("%d/%m/%Y"),
                "data_vencimento": data_vencimento.strftime("%d/%m/%Y"),
                "status": status
            })
        if novos:
            for item in novos:
                supabase.table("exames").insert(item).execute()
            st.success("Exames adicionados")
            st.rerun()

# ================= TABELA COM EXCLUSÃO =================
st.subheader("Tabela de exames")

if not df.empty:
    df["Excluir"] = False
    colunas = [
        "cpf", "paciente", "prontuario_registro", "exame",
        "data_exame", "data_vencimento", "status", "Excluir"
    ]
    tabela = st.data_editor(df[colunas], use_container_width=True)
    if st.button("Salvar alterações"):
        df_final = tabela[tabela["Excluir"] == False].drop(columns=["Excluir"])
        # Atualiza no Supabase
        supabase.table("exames").delete().eq("hospital_id", user_id).execute()  # limpa antigo
        for _, row in df_final.iterrows():
            supabase.table("exames").insert(row.to_dict()).execute()
        st.success("Alterações salvas")
        st.rerun()
else:
    st.info("Nenhum exame cadastrado")
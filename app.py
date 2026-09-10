import streamlit as st
import pandas as pd
import pdfplumber
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from supabase import create_client

# ============================================================
# SUPABASE
# ============================================================

url = "https://dpouzkapdaipnfnlsrio.supabase.co"
key = "sb_publishable_hhN-A_o0Q9Y6o8lTGr2xCw_iBbSSXca"

supabase = create_client(url, key)

st.set_page_config(
    page_title="Controle de Exames",
    layout="wide"
)

# ============================================================
# LOGIN
# ============================================================

if "user" not in st.session_state:
    st.session_state.user = None

st.title("Sistema de Controle de Exames")

if not st.session_state.user:

    st.subheader("Login")

    with st.form("login_form"):

        email = st.text_input("Email")
        senha = st.text_input("Senha", type="password")

        col1, col2 = st.columns(2)

        with col1:
            entrar = st.form_submit_button(
                "Entrar",
                use_container_width=True
            )

        with col2:
            cadastrar = st.form_submit_button(
                "Cadastrar",
                use_container_width=True
            )

    # --------------------------------------------------------
    # ENTRAR
    # --------------------------------------------------------

    if entrar:

        if not email or not senha:
            st.warning("Preencha o email e a senha.")

        else:

            try:

                user = supabase.auth.sign_in_with_password({
                    "email": email,
                    "password": senha
                })

                st.session_state.user = user

                st.rerun()

            except Exception as e:

                st.error(
                    "Não foi possível realizar o login. "
                    "Verifique o email e a senha."
                )

    # --------------------------------------------------------
    # CADASTRAR
    # --------------------------------------------------------

    if cadastrar:

        if not email or not senha:

            st.warning(
                "Preencha o email e a senha para realizar o cadastro."
            )

        else:

            try:

                resultado = supabase.auth.sign_up({
                    "email": email,
                    "password": senha
                })

                if resultado.user:

                    st.success(
                        "Usuário criado com sucesso! "
                        "Para efetuar o login, é necessário confirmar o email."
                    )

            except Exception as e:

                st.error(
                    f"Erro ao cadastrar: {e}"
                )

    st.stop()


# ============================================================
# SESSÃO SUPABASE
# ============================================================

if st.session_state.user:

    try:

        supabase.auth.set_session(
            st.session_state.user.session.access_token,
            st.session_state.user.session.refresh_token
        )

    except Exception as e:

        st.error(
            "A sessão expirou. Faça o login novamente."
        )

        st.session_state.user = None
        st.stop()


user_id = st.session_state.user.user.id


# ============================================================
# FUNÇÕES
# ============================================================

def identificar_exame(texto):

    if texto.lower().count("resultado") > 5:
        return "LAUDO PRÉ TRANSPLANTE"

    linhas = texto.split("\n")

    palavras_chave = [
        "ELETROCARDIOGRAMA",
        "ULTRASSONOGRAFIA",
        "ENDOSCOPIA",
        "ECOCARDIOGRAMA",
        "TESTE ERGOMÉTRICO",
        "TESTE ERGOMETRICO",
        "DOPPLER",
        "HEMODINÂMICO",
        "HEMODINAMICO",
        "CORONARIOGRAFIA",
        "CATETERISMO"
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

    nome = re.split(
        r'Origem|Sexo|Idade|Nascimento|Dt\.|Convênio',
        nome
    )[0]

    return nome.strip()


def ler_pdf(arquivo):

    texto = ""

    with pdfplumber.open(arquivo) as pdf:

        for page in pdf.pages:

            conteudo = page.extract_text()

            if conteudo:
                texto += conteudo + "\n"

    cpf = None

    cpf_match = re.search(
        r'CPF[:\s]*([0-9\.\-]{11,14})',
        texto
    )

    if cpf_match:
        cpf = cpf_match.group(1)

    nome = None

    padroes_nome = [
        r'Nome Civil:\s*(.*)',
        r'Nome\s*\.{0,}\s*:\s*(.*)',
        r'Paciente:\s*(.*)'
    ]

    for padrao in padroes_nome:

        match = re.search(
            padrao,
            texto
        )

        if match:

            nome = limpar_nome(
                match.group(1).strip()
            )

            break

    data_exame = None

    padroes_data = [

        r'Data do exame[:\s]*([0-9]{2}/[0-9]{2}/[0-9]{4})',

        r'Data realização[:\s]*([0-9]{2}/[0-9]{2}/[0-9]{4})',

        r'Realização[:\s]*([0-9]{2}/[0-9]{2}/[0-9]{4})',

        r'Emissão do laudo[:\s]*([0-9]{2}/[0-9]{2}/[0-9]{4})'
    ]

    for padrao in padroes_data:

        match = re.search(
            padrao,
            texto,
            re.IGNORECASE
        )

        if match:

            data_exame = datetime.strptime(
                match.group(1),
                "%d/%m/%Y"
            )

            break

    if not data_exame:

        for linha in texto.split("\n"):

            if "nasc" in linha.lower():
                continue

            match = re.search(
                r'\d{2}/\d{2}/\d{4}',
                linha
            )

            if match:

                data_exame = datetime.strptime(
                    match.group(0),
                    "%d/%m/%Y"
                )

                break

    tipo_exame = identificar_exame(texto)

    prontuario_registro = None

    match_prontuario = re.search(
        r'Prontu[aá]rio[:\s]*([0-9/]+)',
        texto,
        re.IGNORECASE
    )

    if match_prontuario:

        prontuario_registro = re.sub(
            r'\D',
            '',
            match_prontuario.group(1)
        )

    if not prontuario_registro:

        match_registro = re.search(
            r'Registro.*?([0-9]{5,})',
            texto,
            re.IGNORECASE
        )

        if match_registro:

            prontuario_registro = match_registro.group(1)

    return (
        cpf,
        nome,
        data_exame,
        tipo_exame,
        prontuario_registro
    )


def calcular_status(data_vencimento):

    hoje = datetime.now(
        ZoneInfo("America/Sao_Paulo")
    ).date()

    vencimento = data_vencimento.date()

    dias_restantes = (
        vencimento - hoje
    ).days

    if dias_restantes < 0:

        return "🔴 VENCIDO"

    if dias_restantes <= 30:

        return "🟡 EM ALERTA"

    return "🟢 VALIDO"


# ============================================================
# ATUALIZAÇÃO DOS STATUS
# ============================================================

def atualizar_status_banco():

    exames = supabase.table(
        "exames"
    ).select(
        "id, data_vencimento"
    ).eq(
        "hospital_id",
        user_id
    ).execute()

    for exame in exames.data:

        try:

            data_vencimento = datetime.strptime(
                exame["data_vencimento"],
                "%d/%m/%Y"
            )

            novo_status = calcular_status(
                data_vencimento
            )

            supabase.table(
                "exames"
            ).update({
                "status": novo_status
            }).eq(
                "id",
                exame["id"]
            ).execute()

        except Exception:
            continue


# ============================================================
# CONTROLE DA PRIMEIRA ATUALIZAÇÃO
# ============================================================

if "status_atualizado_entrada" not in st.session_state:

    st.session_state.status_atualizado_entrada = False


# ============================================================
# ATUALIZAÇÃO AUTOMÁTICA AO ENTRAR
# ============================================================

if not st.session_state.status_atualizado_entrada:

    atualizar_status_banco()

    st.session_state.status_atualizado_entrada = True


# ============================================================
# BUSCAR EXAMES
# ============================================================

res = supabase.table(
    "exames"
).select(
    "*"
).eq(
    "hospital_id",
    user_id
).execute()

df = pd.DataFrame(
    res.data
)


# ============================================================
# ATUALIZAÇÃO AUTOMÁTICA A CADA 1 HORA
# ============================================================

if "ultima_atualizacao" not in st.session_state:

    st.session_state.ultima_atualizacao = None


@st.fragment(run_every="1h")
def atualizacao_automatica():

    # Se houver alguma seleção de exclusão na tela,
    # não executa a atualização automática.

    if (
        "exclusoes_pendentes" in st.session_state
        and st.session_state.exclusoes_pendentes
    ):

        return

    atualizar_status_banco()


atualizacao_automatica()


# ============================================================
# DASHBOARD
# ============================================================

if not df.empty:

    vencidos = len(
        df[
            df["status"].str.contains(
                "VENCIDO",
                na=False
            )
        ]
    )

    alerta = len(
        df[
            df["status"].str.contains(
                "ALERTA",
                na=False
            )
        ]
    )

    validos = len(
        df[
            df["status"].str.contains(
                "VALIDO",
                na=False
            )
        ]
    )

else:

    vencidos = 0
    alerta = 0
    validos = 0


c1, c2, c3 = st.columns(3)

c1.metric(
    "🔴 VENCIDOS",
    vencidos
)

c2.metric(
    "🟡 EM ALERTA",
    alerta
)

c3.metric(
    "🟢 VÁLIDOS",
    validos
)


# ============================================================
# ATUALIZAR STATUS + SAIR
# ============================================================

col_atualizar, col_espaco, col_sair = st.columns(
    [2, 5, 1]
)

with col_atualizar:

    if st.button(
        "Atualizar status",
        use_container_width=True
    ):

        # Se houver algo selecionado para excluir,
        # não atualiza para evitar interferência.

        if (
            "exclusoes_pendentes" in st.session_state
            and st.session_state.exclusoes_pendentes
        ):

            st.warning(
                "Há exames selecionados para exclusão. "
                "Salve ou desmarque as alterações antes de atualizar os status."
            )

        else:

            try:

                atualizar_status_banco()

                st.session_state.ultima_atualizacao = datetime.now(
                    ZoneInfo("America/Sao_Paulo")
                )

                st.rerun()

            except Exception as e:

                st.error(
                    f"Erro ao atualizar os status: {e}"
                )


with col_sair:

    if st.button(
        "Sair",
        use_container_width=True
    ):

        supabase.auth.sign_out()

        st.session_state.user = None

        st.session_state.status_atualizado_entrada = False

        st.rerun()


if st.session_state.ultima_atualizacao:

    st.caption(
        "Atualizado em: "
        + st.session_state.ultima_atualizacao.strftime(
            "%d/%m/%Y às %H:%M:%S"
        )
    )


st.divider()


# ============================================================
# UPLOAD
# ============================================================

arquivos = st.file_uploader(
    "Selecionar PDFs",
    type=["pdf"],
    accept_multiple_files=True
)


if st.button("Ler exames"):

    if not arquivos:

        st.warning(
            "Selecione PDFs"
        )

    else:

        for arquivo in arquivos:

            (
                cpf,
                nome,
                data_exame,
                tipo_exame,
                prontuario
            ) = ler_pdf(arquivo)

            if not data_exame:

                st.warning(
                    f"Data não encontrada em {arquivo.name}"
                )

                continue

            data_vencimento = (
                data_exame
                + timedelta(days=180)
            )

            status = calcular_status(
                data_vencimento
            )

            supabase.table(
                "exames"
            ).insert({

                "hospital_id": user_id,

                "cpf": cpf,

                "paciente": nome,

                "prontuario_registro": prontuario,

                "exame": tipo_exame,

                "data_exame":
                    data_exame.strftime(
                        "%d/%m/%Y"
                    ),

                "data_vencimento":
                    data_vencimento.strftime(
                        "%d/%m/%Y"
                    ),

                "status": status

            }).execute()

        st.success(
            "Exames adicionados"
        )

        st.rerun()


# ============================================================
# TABELA
# ============================================================

st.subheader(
    "Tabela de exames"
)


if not df.empty:

    df["Excluir"] = False


    # --------------------------------------------------------
    # FILTRO
    # --------------------------------------------------------

    with st.popover(
        "🔎 Filtrar exames"
    ):

        filtro = st.radio(

            "Mostrar:",

            [
                "Todos os exames",
                "🔴 Vencidos",
                "🟡 Em alerta",
                "🟢 Válidos"
            ],

            index=0
        )


    st.caption(
        f"Filtro atual: {filtro}"
    )


    if filtro == "🔴 Vencidos":

        df_tabela = df[
            df["status"].str.contains(
                "VENCIDO",
                na=False
            )
        ]

    elif filtro == "🟡 Em alerta":

        df_tabela = df[
            df["status"].str.contains(
                "ALERTA",
                na=False
            )
        ]

    elif filtro == "🟢 Válidos":

        df_tabela = df[
            df["status"].str.contains(
                "VALIDO",
                na=False
            )
        ]

    else:

        df_tabela = df


    colunas = [

        "cpf",

        "paciente",

        "prontuario_registro",

        "exame",

        "data_exame",

        "data_vencimento",

        "status",

        "Excluir"
    ]


    # --------------------------------------------------------
    # TABELA
    # --------------------------------------------------------

    tabela = st.data_editor(

        df_tabela[colunas],

        use_container_width=True,

        disabled=[
            "cpf",
            "paciente",
            "prontuario_registro",
            "exame",
            "data_exame",
            "data_vencimento",
            "status"
        ],

        hide_index=True
    )


    # --------------------------------------------------------
    # IDENTIFICAR EXCLUSÕES SELECIONADAS
    # --------------------------------------------------------

    exclusoes = tabela[
        tabela["Excluir"] == True
    ].index.tolist()


    st.session_state.exclusoes_pendentes = (
        len(exclusoes) > 0
    )


    # --------------------------------------------------------
    # SALVAR ALTERAÇÕES
    # --------------------------------------------------------

    if st.button(
        "Salvar alterações"
    ):

        excluir_index = tabela[
            tabela["Excluir"] == True
        ].index.tolist()


        for index in excluir_index:

            id_excluir = df.loc[
                index,
                "id"
            ]

            supabase.table(
                "exames"
            ).delete().eq(
                "id",
                id_excluir
            ).execute()


        st.session_state.exclusoes_pendentes = False

        st.success(
            "Alterações salvas"
        )

        st.rerun()


else:

    st.info(
        "Nenhum exame cadastrado"
    )

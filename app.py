import streamlit as st
import pandas as pd
import pdfplumber
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from supabase import create_client

# 🔑 SUPABASE
url = "https://dpouzkapdaipnfnlsrio.supabase.co"
key = "sb_publishable_hhN-A_o0Q9Y6o8lTGr2xCw_iBbSSXca"
supabase = create_client(url, key)

st.set_page_config(page_title="Controle de Exames", layout="wide")


# ================= FUNÇÕES DE STATUS =================

def calcular_status(data_vencimento):

    hoje = datetime.now(
        ZoneInfo("America/Sao_Paulo")
    ).date()

    if isinstance(data_vencimento, datetime):

        data_vencimento = data_vencimento.date()

    dias_para_vencer = (
        data_vencimento - hoje
    ).days

    if dias_para_vencer < 0:

        return "🔴 VENCIDO"

    if dias_para_vencer <= 30:

        return "🟡 EM ALERTA"

    return "🟢 VALIDO"


def atualizar_status_exames(user_id):

    """
    Atualiza os status de todos os exames do usuário.
    Esta é a mesma função utilizada pelo botão manual
    e pela atualização automática.
    """

    exames_atualizados = supabase.table(
        "exames"
    ).select(
        "id, data_vencimento, status"
    ).eq(
        "hospital_id",
        user_id
    ).execute()

    alterou = False

    for exame in exames_atualizados.data:

        try:

            data_vencimento = datetime.strptime(
                exame["data_vencimento"],
                "%d/%m/%Y"
            )

            novo_status = calcular_status(
                data_vencimento
            )

            status_atual = exame.get("status")

            if status_atual != novo_status:

                supabase.table("exames").update({
                    "status": novo_status
                }).eq(
                    "id",
                    exame["id"]
                ).execute()

                alterou = True

        except Exception:

            pass

    return alterou


# ================= LOGIN =================

if "user" not in st.session_state:
    st.session_state.user = None

if "exclusoes_pendentes" not in st.session_state:
    st.session_state.exclusoes_pendentes = set()

if "confirmar_saida" not in st.session_state:
    st.session_state.confirmar_saida = False

if "ultima_atualizacao" not in st.session_state:
    st.session_state.ultima_atualizacao = None


# Controle dos filtros
if "filtro_status" not in st.session_state:
    st.session_state.filtro_status = "Todos os exames"

if "busca_paciente" not in st.session_state:
    st.session_state.busca_paciente = ""

if "busca_prontuario" not in st.session_state:
    st.session_state.busca_prontuario = ""


st.title("Sistema de Controle de Exames")


if not st.session_state.user:

    st.subheader("Login")

    # ================= FORMULÁRIO LOGIN/CADASTRO =================

    with st.form("form_login"):

        email = st.text_input("Email")

        senha = st.text_input(
            "Senha",
            type="password"
        )

        col1, col2 = st.columns(2)

        with col1:
            entrar = st.form_submit_button("Entrar")

        with col2:
            cadastrar = st.form_submit_button("Cadastrar")


    # ================= ENTRAR =================

    if entrar:

        if not email or not senha:

            st.warning(
                "Digite o email e a senha para efetuar o login."
            )

        else:

            try:

                user = supabase.auth.sign_in_with_password({
                    "email": email,
                    "password": senha
                })

                # ================= ATUALIZA STATUS AO LOGAR =================

                user_id_login = user.user.id

                atualizar_status_exames(
                    user_id_login
                )

                st.session_state.user = user
                st.session_state.exclusoes_pendentes = set()
                st.session_state.confirmar_saida = False
                st.session_state.ultima_atualizacao = None

                st.rerun()

            except Exception as e:

                st.error(
                    f"Erro no login: {e}"
                )


    # ================= CADASTRAR =================

    if cadastrar:

        if not email or not senha:

            st.warning(
                "Digite o email e a senha para realizar o cadastro."
            )

        else:

            try:

                supabase.auth.sign_up({
                    "email": email,
                    "password": senha
                })

                st.success(
                    "Cadastro realizado! "
                    "Enviamos um email de confirmação para o endereço informado. "
                    "Para efetuar o login, é necessário confirmar o email. "
                    "Verifique também a caixa de spam."
                )

            except Exception as e:

                st.error(
                    f"Erro ao cadastrar: {e}"
                )

    st.stop()


# ================= SESSÃO SUPABASE =================

if st.session_state.user:

    supabase.auth.set_session(
        st.session_state.user.session.access_token,
        st.session_state.user.session.refresh_token
    )

user_id = st.session_state.user.user.id


# ================= FUNÇÕES =================

def identificar_exame(texto):

    if texto.lower().count("resultado") > 5:
        return "LAUDO PRÉ TRANSPLANTE"

    linhas = texto.split("\n")

    palavras_chave = [
        "ELETROCARDIOGRAMA", "ULTRASSONOGRAFIA", "ENDOSCOPIA",
        "ECOCARDIOGRAMA", "TESTE ERGOMÉTRICO", "TESTE ERGOMETRICO",
        "DOPPLER", "HEMODINÂMICO", "HEMODINAMICO",
        "CORONARIOGRAFIA", "CATETERISMO"
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


    # ================= DATA DE NASCIMENTO =================

    data_nascimento = None

    padroes_nascimento = [
        r'Dt\.\s*Nascimento[:\s]*([0-9]{2}/[0-9]{2}/[0-9]{4})',
        r'Data\s+de\s+Nascimento[:\s]*([0-9]{2}/[0-9]{2}/[0-9]{4})',
        r'Nascimento[:\s]*([0-9]{2}/[0-9]{2}/[0-9]{4})'
    ]

    for padrao in padroes_nascimento:

        match_nascimento = re.search(
            padrao,
            texto,
            re.IGNORECASE
        )

        if match_nascimento:

            data_nascimento = datetime.strptime(
                match_nascimento.group(1),
                "%d/%m/%Y"
            )

            break


    # ================= NOME =================

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


    # ================= DATA DO EXAME =================

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


    # ================= PRONTUÁRIO / REGISTRO =================

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
        data_nascimento,
        nome,
        data_exame,
        tipo_exame,
        prontuario_registro
    )


# ================= BANCO =================

res = supabase.table("exames").select("*").eq(
    "hospital_id",
    user_id
).execute()

df = pd.DataFrame(res.data)


# ================= ATUALIZAÇÃO AUTOMÁTICA INICIAL =================

if not df.empty:

    for index, exame in df.iterrows():

        try:

            data_vencimento = datetime.strptime(
                exame["data_vencimento"],
                "%d/%m/%Y"
            )

            novo_status = calcular_status(
                data_vencimento
            )

            status_atual = exame.get("status")

            if status_atual != novo_status:

                supabase.table("exames").update({
                    "status": novo_status
                }).eq(
                    "id",
                    exame["id"]
                ).execute()

                df.loc[index, "status"] = novo_status

        except Exception:

            pass


# ================= DASHBOARD =================

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


# ================= ATUALIZAÇÃO AUTOMÁTICA A CADA 1 HORA =================

@st.fragment(run_every="1h")
def verificacao_automatica_status():

    if st.session_state.exclusoes_pendentes:

        st.warning(
            "⚠️ Existem alterações não salvas. "
            "Salve ou desmarque as alterações antes da "
            "atualização automática dos status."
        )

        return

    try:

        houve_alteracao = atualizar_status_exames(
            user_id
        )

        if houve_alteracao:

            st.rerun(scope="app")

    except Exception:

        pass


verificacao_automatica_status()


# ================= ATUALIZAR STATUS + SAIR =================

col_atualizar, col_espaco, col_sair = st.columns([1, 5, 1])


with col_atualizar:

    if st.button("Atualizar status"):

        try:

            atualizar_status_exames(
                user_id
            )

            st.session_state.ultima_atualizacao = datetime.now(
                ZoneInfo("America/Sao_Paulo")
            )

            st.rerun()

        except Exception as e:

            st.error(
                f"Erro ao atualizar os status: {e}"
            )


if st.session_state.ultima_atualizacao:

    st.caption(
        f"Atualizado em: "
        f"{st.session_state.ultima_atualizacao.strftime('%d/%m/%Y às %H:%M:%S')}"
    )


with col_sair:

    if st.button("Sair"):

        if st.session_state.exclusoes_pendentes:

            st.session_state.confirmar_saida = True

        else:

            try:
                supabase.auth.sign_out()
            except Exception:
                pass

            st.session_state.user = None
            st.session_state.exclusoes_pendentes = set()
            st.session_state.confirmar_saida = False

            st.rerun()


# ================= CONFIRMAÇÃO DE SAÍDA =================

if st.session_state.confirmar_saida:

    st.warning(
        "⚠️ Existem alterações não salvas. "
        "Se você sair agora, essas alterações serão perdidas."
    )

    col_continuar, col_sair_confirmar = st.columns(2)

    with col_continuar:

        if st.button("Continuar editando"):

            st.session_state.confirmar_saida = False

            st.rerun()

    with col_sair_confirmar:

        if st.button("Sair sem salvar"):

            try:
                supabase.auth.sign_out()
            except Exception:
                pass

            st.session_state.user = None
            st.session_state.exclusoes_pendentes = set()
            st.session_state.confirmar_saida = False

            st.rerun()


st.divider()


# ================= UPLOAD =================

arquivos = st.file_uploader(
    "Selecionar PDFs",
    type=["pdf"],
    accept_multiple_files=True
)


if st.button("Ler exames"):

    if not arquivos:

        st.warning("Selecione PDFs")

    else:

        for arquivo in arquivos:

            (
                data_nascimento,
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
                data_exame + timedelta(days=180)
            )


            status = calcular_status(
                data_vencimento
            )


            supabase.table("exames").insert({

                "hospital_id": user_id,

                "data_nascimento": (
                    data_nascimento.strftime("%d/%m/%Y")
                    if data_nascimento
                    else None
                ),

                "paciente": nome,

                "prontuario_registro": prontuario,

                "exame": tipo_exame,

                "data_exame": data_exame.strftime(
                    "%d/%m/%Y"
                ),

                "data_vencimento": data_vencimento.strftime(
                    "%d/%m/%Y"
                ),

                "status": status

            }).execute()


        st.success(
            "Exames adicionados"
        )

        st.rerun()


# ================= TABELA =================

st.subheader(
    "Tabela de exames"
)


if not df.empty:

    # ================= FILTROS =================

    col_filtro_status, col_filtro_paciente, col_filtro_prontuario = st.columns(3)


    # ================= FILTRO STATUS =================

    with col_filtro_status:

        with st.popover("🔎 Status", use_container_width=True):

            filtro_status = st.radio(
                "Mostrar:",
                [
                    "Todos os exames",
                    "🔴 Vencidos",
                    "🟡 Em alerta",
                    "🟢 Válidos"
                ],
                index=[
                    "Todos os exames",
                    "🔴 Vencidos",
                    "🟡 Em alerta",
                    "🟢 Válidos"
                ].index(st.session_state.filtro_status),
                key="filtro_status_input"
            )

            st.session_state.filtro_status = filtro_status


    # ================= FILTRO PACIENTE =================

    with col_filtro_paciente:

        with st.popover("👤 Paciente", use_container_width=True):

            paciente_busca = st.text_input(
                "Buscar paciente",
                value=st.session_state.busca_paciente,
                placeholder="Digite o nome",
                key="paciente_busca_input"
            )

            st.session_state.busca_paciente = paciente_busca


    # ================= FILTRO PRONTUÁRIO =================

    with col_filtro_prontuario:

        with st.popover("📋 Prontuário", use_container_width=True):

            prontuario_busca = st.text_input(
                "Buscar prontuário",
                value=st.session_state.busca_prontuario,
                placeholder="Digite o número",
                key="prontuario_busca_input"
            )

            st.session_state.busca_prontuario = prontuario_busca


    filtro = st.session_state.filtro_status
    paciente_busca = st.session_state.busca_paciente
    prontuario_busca = st.session_state.busca_prontuario


    # ================= FILTRO POR STATUS =================

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


    # ================= FILTRO POR PACIENTE =================

    if paciente_busca:

        df_tabela = df_tabela[
            df_tabela["paciente"]
            .fillna("")
            .astype(str)
            .str.contains(
                re.escape(paciente_busca),
                case=False,
                na=False
            )
        ]


    # ================= FILTRO POR PRONTUÁRIO =================

    if prontuario_busca:

        df_tabela = df_tabela[
            df_tabela["prontuario_registro"]
            .fillna("")
            .astype(str)
            .str.contains(
                re.escape(prontuario_busca),
                case=False,
                na=False
            )
        ]


    # ================= ESPECIFICAÇÕES DOS FILTROS =================

    filtros_ativos = []

    if filtro != "Todos os exames":
        filtros_ativos.append(
            f"Status: {filtro}"
        )

    if paciente_busca:
        filtros_ativos.append(
            f"Paciente: {paciente_busca}"
        )

    if prontuario_busca:
        filtros_ativos.append(
            f"Prontuário: {prontuario_busca}"
        )

    if filtros_ativos:

        st.caption(
            "Filtros ativos: " +
            " | ".join(filtros_ativos)
        )

    else:

        st.caption(
            "Filtros ativos: Nenhum"
        )


    # ================= COLUNA EXCLUIR =================

    df_tabela = df_tabela.copy()

    df_tabela["Excluir"] = df_tabela.index.isin(
        st.session_state.exclusoes_pendentes
    )


    colunas = [
        "data_nascimento",
        "paciente",
        "prontuario_registro",
        "exame",
        "data_exame",
        "data_vencimento",
        "status",
        "Excluir"
    ]


    # ================= FUNÇÃO PARA CONTROLAR EXCLUSÕES =================

    def atualizar_exclusoes():

        estado_editor = st.session_state.get(
            "editor_exames",
            {}
        )

        alteracoes = estado_editor.get(
            "edited_rows",
            {}
        )

        indices_visiveis = list(
            df_tabela.index
        )

        for linha, valores in alteracoes.items():

            try:

                linha = int(linha)

                if linha < 0 or linha >= len(indices_visiveis):
                    continue

                indice_df = indices_visiveis[linha]

                id_exame = df.loc[
                    indice_df,
                    "id"
                ]

                if "Excluir" in valores:

                    if valores["Excluir"]:

                        st.session_state.exclusoes_pendentes.add(
                            id_exame
                        )

                    else:

                        st.session_state.exclusoes_pendentes.discard(
                            id_exame
                        )

            except Exception:

                pass


    # ================= TABELA BLOQUEADA =================

    tabela = st.data_editor(
        df_tabela[colunas],
        use_container_width=True,
        disabled=[
            "data_nascimento",
            "paciente",
            "prontuario_registro",
            "exame",
            "data_exame",
            "data_vencimento",
            "status"
        ],
        key="editor_exames",
        on_change=atualizar_exclusoes
    )


    # ================= SALVAR ALTERAÇÕES =================

    if st.button(
        "Salvar alterações"
    ):

        try:

            for id_excluir in st.session_state.exclusoes_pendentes:

                supabase.table(
                    "exames"
                ).delete().eq(
                    "id",
                    id_excluir
                ).execute()

            st.session_state.exclusoes_pendentes = set()

            st.success(
                "Alterações salvas"
            )

            st.rerun()

        except Exception as e:

            st.error(
                f"Erro ao salvar as alterações: {e}"
            )


else:

    st.info(
        "Nenhum exame cadastrado"
    )

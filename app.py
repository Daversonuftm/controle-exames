import streamlit as st
import pandas as pd
import pdfplumber
import re
import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from supabase import create_client


# ============================================================
# SUPABASE
# ============================================================

url = "https://dpouzkapdaipnfnlsrio.supabase.co"

key = "sb_publishable_hhN-A_o0Q9Y6o8lTGr2xCw_iBbSSXca"

supabase = create_client(
    url,
    key
)

st.set_page_config(
    page_title="Controle de Exames",
    layout="wide"
)


# ============================================================
# FUNÇÕES DE STATUS
# ============================================================

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
    Esta é a mesma função utilizada pelo botão manual,
    pelo login e pela atualização automática.
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

            status_atual = exame.get(
                "status"
            )

            if status_atual != novo_status:

                supabase.table(
                    "exames"
                ).update({
                    "status": novo_status
                }).eq(
                    "id",
                    exame["id"]
                ).execute()

                alterou = True

        except Exception:

            pass

    return alterou


# ============================================================
# FUNÇÕES PARA COMPARAÇÃO DOS EXAMES
# ============================================================

def normalizar_texto_comparacao(texto):

    if texto is None:

        return ""

    texto = str(texto)

    texto = texto.upper()

    texto = re.sub(
        r"\s+",
        " ",
        texto
    )

    return texto.strip()


def converter_data_exame(data):

    if not data:

        return None

    if isinstance(data, datetime):

        return data

    if isinstance(data, str):

        try:

            return datetime.strptime(
                data,
                "%d/%m/%Y"
            )

        except Exception:

            return None

    return None


def formatar_data(data):

    data_convertida = converter_data_exame(
        data
    )

    if data_convertida:

        return data_convertida.strftime(
            "%d/%m/%Y"
        )

    return str(data)


def buscar_exames_anteriores(
    user_id,
    paciente,
    tipo_exame
):

    resposta = supabase.table(
        "exames"
    ).select(
        "*"
    ).eq(
        "hospital_id",
        user_id
    ).execute()

    exames = resposta.data or []

    paciente_comparacao = normalizar_texto_comparacao(
        paciente
    )

    exame_comparacao = normalizar_texto_comparacao(
        tipo_exame
    )

    encontrados = []

    for exame in exames:

        paciente_existente = normalizar_texto_comparacao(
            exame.get("paciente")
        )

        exame_existente = normalizar_texto_comparacao(
            exame.get("exame")
        )

        if (
            paciente_existente == paciente_comparacao
            and
            exame_existente == exame_comparacao
        ):

            encontrados.append(
                exame
            )

    return encontrados


# ============================================================
# FUNÇÃO PARA CRIAR LINK DO PDF
# ============================================================

def criar_link_pdf(linha):

    arquivo_path = linha.get(
        "arquivo_path"
    )

    nome_exame = str(
        linha.get(
            "exame",
            "EXAME"
        )
    )

    if not arquivo_path:

        return nome_exame

    try:

        resposta = supabase.storage.from_(
            "exames-pdf"
        ).create_signed_url(
            arquivo_path,
            3600
        )

        if isinstance(
            resposta,
            dict
        ):

            link = (
                resposta.get("signedURL")
                or resposta.get("signed_url")
                or resposta.get("signedUrl")
            )

        else:

            link = getattr(
                resposta,
                "signed_url",
                None
            )

            if not link:

                link = getattr(
                    resposta,
                    "signedURL",
                    None
                )

        if link:

            return (
                f"{link}#EXAME_{nome_exame}"
            )

    except Exception:

        pass

    return nome_exame


# ============================================================
# FUNÇÕES DE LEITURA DOS PDFS
# ============================================================

def identificar_exame(texto):

    if texto.lower().count(
        "resultado"
    ) > 5:

        return "LAUDO PRÉ TRANSPLANTE"

    linhas = texto.split(
        "\n"
    )

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

    if (
        "endoscopia" in texto
        or
        "eda" in texto
    ):

        return "ENDOSCOPIA"

    if (
        "ecocardiograma" in texto
        or
        "ecocardiografia" in texto
    ):

        return "ECOCARDIOGRAMA"

    if (
        "ultrassom" in texto
        or
        "ultrassonografia" in texto
    ):

        return "ULTRASSOM"

    if (
        "pré tx" in texto
        or
        "pre tx" in texto
    ):

        return "LAUDO PRÉ TRANSPLANTE"

    return "EXAME"


def limpar_nome(nome):

    nome = nome.split(
        "\n"
    )[0]

    nome = re.split(
        r'Origem|Sexo|Idade|Nascimento|Dt\.|Convênio',
        nome
    )[0]

    return nome.strip()


def ler_pdf(arquivo):

    texto = ""

    with pdfplumber.open(
        arquivo
    ) as pdf:

        for page in pdf.pages:

            conteudo = page.extract_text()

            if conteudo:

                texto += (
                    conteudo
                    +
                    "\n"
                )


    # ========================================================
    # DATA DE NASCIMENTO
    # ========================================================

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


    # ========================================================
    # NOME
    # ========================================================

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


    # ========================================================
    # DATA DO EXAME
    # ========================================================

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

        for linha in texto.split(
            "\n"
        ):

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


    # ========================================================
    # TIPO DO EXAME
    # ========================================================

    tipo_exame = identificar_exame(
        texto
    )


    # ========================================================
    # PRONTUÁRIO / REGISTRO
    # ========================================================

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

            prontuario_registro = (
                match_registro.group(1)
            )


    return (

        data_nascimento,

        nome,

        data_exame,

        tipo_exame,

        prontuario_registro

    )


# ============================================================
# CONTROLE DA SESSÃO
# ============================================================

if "user" not in st.session_state:

    st.session_state.user = None


if "ultima_atualizacao" not in st.session_state:

    st.session_state.ultima_atualizacao = None


if "filtro_status" not in st.session_state:

    st.session_state.filtro_status = (
        "Todos os exames"
    )


if "busca_paciente" not in st.session_state:

    st.session_state.busca_paciente = ""


if "busca_prontuario" not in st.session_state:

    st.session_state.busca_prontuario = ""


if "mensagens_processamento" not in st.session_state:

    st.session_state.mensagens_processamento = []


if "exclusoes_pendentes" not in st.session_state:

    st.session_state.exclusoes_pendentes = set()


if "confirmar_exclusao" not in st.session_state:

    st.session_state.confirmar_exclusao = False


# ============================================================
# TÍTULO
# ============================================================

st.title(
    "Sistema de Controle de Exames"
)


# ============================================================
# LOGIN
# ============================================================

if not st.session_state.user:

    st.subheader(
        "Login"
    )

    with st.form(
        "form_login"
    ):

        email = st.text_input(
            "Email"
        )

        senha = st.text_input(
            "Senha",
            type="password"
        )

        col1, col2 = st.columns(
            2
        )

        with col1:

            entrar = st.form_submit_button(
                "Entrar"
            )

        with col2:

            cadastrar = st.form_submit_button(
                "Cadastrar"
            )


    # ========================================================
    # ENTRAR
    # ========================================================

    if entrar:

        if not email or not senha:

            st.warning(
                "Digite o email e a senha para efetuar o login."
            )

        else:

            try:

                user = (
                    supabase.auth.sign_in_with_password(
                        {
                            "email": email,
                            "password": senha
                        }
                    )
                )

                user_id_login = user.user.id

                atualizar_status_exames(
                    user_id_login
                )

                st.session_state.user = user

                st.session_state.ultima_atualizacao = None

                st.session_state.exclusoes_pendentes = set()

                st.session_state.confirmar_exclusao = False

                st.session_state.mensagens_processamento = []

                st.rerun()

            except Exception as e:

                st.error(
                    f"Erro no login: {e}"
                )


    # ========================================================
    # CADASTRAR
    # ========================================================

    if cadastrar:

        if not email or not senha:

            st.warning(
                "Digite o email e a senha para realizar o cadastro."
            )

        else:

            try:

                supabase.auth.sign_up(
                    {
                        "email": email,
                        "password": senha
                    }
                )

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


# ============================================================
# SESSÃO SUPABASE
# ============================================================

if st.session_state.user:

    supabase.auth.set_session(

        st.session_state.user.session.access_token,

        st.session_state.user.session.refresh_token

    )


user_id = st.session_state.user.user.id


# ============================================================
# CAIXA DE RESULTADO DO PROCESSAMENTO
# ============================================================

if st.session_state.mensagens_processamento:

    with st.container(
        border=True
    ):

        st.subheader(
            "Resultado do processamento"
        )

        for tipo_mensagem, mensagem in (
            st.session_state.mensagens_processamento
        ):

            if tipo_mensagem == "success":

                st.success(
                    mensagem
                )

            elif tipo_mensagem == "info":

                st.info(
                    mensagem
                )

            elif tipo_mensagem == "warning":

                st.warning(
                    mensagem
                )

            elif tipo_mensagem == "error":

                st.error(
                    mensagem
                )


        if st.button(
            "OK, entendi",
            key="ok_resultado_processamento"
        ):

            st.session_state.mensagens_processamento = []

            st.rerun()


# ============================================================
# BANCO
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
# ATUALIZAÇÃO INICIAL DOS STATUS
# ============================================================

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

            status_atual = exame.get(
                "status"
            )

            if status_atual != novo_status:

                supabase.table(
                    "exames"
                ).update(
                    {
                        "status": novo_status
                    }
                ).eq(
                    "id",
                    exame["id"]
                ).execute()

                df.loc[
                    index,
                    "status"
                ] = novo_status

        except Exception:

            pass


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


c1, c2, c3 = st.columns(
    3
)


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
# ATUALIZAÇÃO AUTOMÁTICA A CADA 1 HORA
# ============================================================

@st.fragment(
    run_every="1h"
)
def verificacao_automatica_status():

    try:

        houve_alteracao = atualizar_status_exames(
            user_id
        )

        if houve_alteracao:

            st.rerun(
                scope="app"
            )

    except Exception:

        pass


verificacao_automatica_status()


# ============================================================
# ATUALIZAR STATUS + SAIR
# ============================================================

col_atualizar, col_espaco, col_sair = st.columns(
    [1, 5, 1]
)


with col_atualizar:

    if st.button(
        "Atualizar status"
    ):

        try:

            atualizar_status_exames(
                user_id
            )

            st.session_state.ultima_atualizacao = (
                datetime.now(
                    ZoneInfo(
                        "America/Sao_Paulo"
                    )
                )
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

    if st.button(
        "Sair"
    ):

        try:

            supabase.auth.sign_out()

        except Exception:

            pass

        st.session_state.user = None

        st.session_state.exclusoes_pendentes = set()

        st.session_state.confirmar_exclusao = False

        st.session_state.mensagens_processamento = []

        st.rerun()


st.divider()


# ============================================================
# UPLOAD
# ============================================================

arquivos = st.file_uploader(
    "Selecionar PDFs",
    type=["pdf"],
    accept_multiple_files=True
)


if st.button(
    "Ler exames"
):

    mensagens = []

    if not arquivos:

        mensagens.append(
            (
                "warning",
                "Selecione PDFs."
            )
        )

    else:

        for arquivo in arquivos:

            # =================================================
            # LER PDF
            # =================================================

            try:

                arquivo_bytes = arquivo.getvalue()

                (
                    data_nascimento,
                    nome,
                    data_exame,
                    tipo_exame,
                    prontuario
                ) = ler_pdf(
                    arquivo
                )

            except Exception as e:

                mensagens.append(
                    (
                        "error",
                        f"Erro ao ler o PDF {arquivo.name}: {e}"
                    )
                )

                continue


            # =================================================
            # VALIDAR DATA
            # =================================================

            if not data_exame:

                mensagens.append(
                    (
                        "warning",
                        f"Data não encontrada em {arquivo.name}."
                    )
                )

                continue


            # =================================================
            # VALIDAR NOME
            # =================================================

            if not nome:

                mensagens.append(
                    (
                        "warning",
                        f"Nome do paciente não encontrado em {arquivo.name}."
                    )
                )

                continue


            # =================================================
            # BUSCAR EXAMES EXISTENTES
            # =================================================

            exames_anteriores = buscar_exames_anteriores(
                user_id,
                nome,
                tipo_exame
            )


            data_novo_exame = converter_data_exame(
                data_exame
            )


            # =================================================
            # VERIFICAR SE JÁ EXISTE EXAME IGUAL/MAIS NOVO
            # =================================================

            exame_mais_recente = None

            data_mais_recente = None

            for exame_existente in exames_anteriores:

                data_existente = converter_data_exame(
                    exame_existente.get(
                        "data_exame"
                    )
                )

                if not data_existente:

                    continue

                if (
                    data_mais_recente is None
                    or
                    data_existente > data_mais_recente
                ):

                    data_mais_recente = data_existente

                    exame_mais_recente = exame_existente


            if (
                exame_mais_recente is not None
                and
                data_novo_exame <= data_mais_recente
            ):

                mensagens.append(
                    (
                        "info",
                        f"ℹ️ O exame {tipo_exame} do paciente "
                        f"{nome} não foi cadastrado, pois já existe "
                        f"um exame mais recente ou com a mesma data "
                        f"({formatar_data(data_mais_recente)})."
                    )
                )

                continue


            # =================================================
            # CALCULAR VALIDADE
            # =================================================

            data_vencimento = (
                data_exame
                +
                timedelta(
                    days=180
                )
            )

            status = calcular_status(
                data_vencimento
            )


            # =================================================
            # CRIAR CAMINHO DO PDF
            # =================================================

            nome_arquivo = re.sub(
                r"[^A-Za-z0-9._-]",
                "_",
                arquivo.name
            )

            nome_unico = (
                f"{uuid.uuid4().hex}_{nome_arquivo}"
            )

            arquivo_path = (
                f"{user_id}/{nome_unico}"
            )


            # =================================================
            # UPLOAD DO PDF
            # =================================================

            try:

                supabase.storage.from_(
                    "exames-pdf"
                ).upload(
                    arquivo_path,
                    arquivo_bytes,
                    {
                        "content-type": "application/pdf",
                        "upsert": "false"
                    }
                )

            except Exception as e:

                mensagens.append(
                    (
                        "error",
                        f"Erro ao armazenar o PDF "
                        f"{arquivo.name}: {e}"
                    )
                )

                continue


            # =================================================
            # SALVAR NOVO EXAME NO BANCO
            # =================================================

            try:

                supabase.table(
                    "exames"
                ).insert(

                    {

                        "hospital_id": user_id,

                        "data_nascimento": (
                            data_nascimento.strftime(
                                "%d/%m/%Y"
                            )
                            if data_nascimento
                            else None
                        ),

                        "paciente": nome,

                        "prontuario_registro": prontuario,

                        "exame": tipo_exame,

                        "data_exame": (
                            data_exame.strftime(
                                "%d/%m/%Y"
                            )
                        ),

                        "data_vencimento": (
                            data_vencimento.strftime(
                                "%d/%m/%Y"
                            )
                        ),

                        "status": status,

                        "arquivo_path": arquivo_path

                    }

                ).execute()

            except Exception as e:

                try:

                    supabase.storage.from_(
                        "exames-pdf"
                    ).remove(
                        [
                            arquivo_path
                        ]
                    )

                except Exception:

                    pass

                mensagens.append(
                    (
                        "error",
                        f"Erro ao salvar os dados de "
                        f"{arquivo.name}: {e}"
                    )
                )

                continue


            # =================================================
            # NOVO EXAME MAIS RECENTE:
            # EXCLUIR OS EXAMES ANTIGOS
            # =================================================

            exames_substituidos = []

            for exame_existente in exames_anteriores:

                data_existente = converter_data_exame(
                    exame_existente.get(
                        "data_exame"
                    )
                )

                if not data_existente:

                    continue

                if data_existente < data_novo_exame:

                    id_antigo = exame_existente.get(
                        "id"
                    )

                    arquivo_antigo = exame_existente.get(
                        "arquivo_path"
                    )

                    try:

                        supabase.table(
                            "exames"
                        ).delete().eq(
                            "id",
                            id_antigo
                        ).execute()

                    except Exception:

                        continue


                    if arquivo_antigo:

                        try:

                            supabase.storage.from_(
                                "exames-pdf"
                            ).remove(
                                [
                                    arquivo_antigo
                                ]
                            )

                        except Exception:

                            pass

                    exames_substituidos.append(
                        exame_existente
                    )


            # =================================================
            # MENSAGEM DO RESULTADO
            # =================================================

            if exames_substituidos:

                exame_antigo_mais_recente = max(
                    exames_substituidos,
                    key=lambda x: (
                        converter_data_exame(
                            x.get(
                                "data_exame"
                            )
                        )
                        or datetime.min
                    )
                )

                data_antiga = converter_data_exame(
                    exame_antigo_mais_recente.get(
                        "data_exame"
                    )
                )

                mensagens.append(
                    (
                        "success",
                        f"🔄 O exame {tipo_exame} do paciente "
                        f"{nome} foi atualizado. "
                        f"O exame anterior, realizado em "
                        f"{formatar_data(data_antiga)}, "
                        f"foi substituído."
                    )
                )

            else:

                mensagens.append(
                    (
                        "success",
                        f"➕ O exame {tipo_exame} do paciente "
                        f"{nome} foi cadastrado com sucesso."
                    )
                )


    # =========================================================
    # GUARDAR MENSAGENS PARA APARECEREM APÓS O RERUN
    # =========================================================

    st.session_state.mensagens_processamento = mensagens

    st.rerun()


# ============================================================
# TABELA
# ============================================================

st.subheader(
    "Tabela de exames"
)


if not df.empty:

    # ========================================================
    # FILTROS
    # ========================================================

    col_filtro_status, col_filtro_paciente, col_filtro_prontuario = st.columns(
        3
    )


    # ========================================================
    # FILTRO STATUS
    # ========================================================

    with col_filtro_status:

        with st.popover(
            "🔎 Status"
        ):

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
                ].index(
                    st.session_state.filtro_status
                ),

                key="filtro_status_input"

            )

            st.session_state.filtro_status = (
                filtro_status
            )


        st.caption(
            st.session_state.filtro_status
        )


    # ========================================================
    # FILTRO PACIENTE
    # ========================================================

    with col_filtro_paciente:

        with st.popover(
            "👤 Paciente"
        ):

            paciente_busca = st.text_input(

                "Buscar paciente",

                value=st.session_state.busca_paciente,

                placeholder="Digite o nome",

                key="paciente_busca_input"

            )

            st.session_state.busca_paciente = (
                paciente_busca
            )


        if st.session_state.busca_paciente:

            st.caption(
                f"Paciente: "
                f"{st.session_state.busca_paciente}"
            )

        else:

            st.caption(
                "Nenhum paciente selecionado"
            )


    # ========================================================
    # FILTRO PRONTUÁRIO
    # ========================================================

    with col_filtro_prontuario:

        with st.popover(
            "📋 Prontuário"
        ):

            prontuario_busca = st.text_input(

                "Buscar prontuário",

                value=st.session_state.busca_prontuario,

                placeholder="Digite o número",

                key="prontuario_busca_input"

            )

            st.session_state.busca_prontuario = (
                prontuario_busca
            )


        if st.session_state.busca_prontuario:

            st.caption(
                f"Prontuário: "
                f"{st.session_state.busca_prontuario}"
            )

        else:

            st.caption(
                "Nenhum prontuário selecionado"
            )


    filtro = (
        st.session_state.filtro_status
    )

    paciente_busca = (
        st.session_state.busca_paciente
    )

    prontuario_busca = (
        st.session_state.busca_prontuario
    )


    # ========================================================
    # FILTRO POR STATUS
    # ========================================================

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


    # ========================================================
    # FILTRO PACIENTE
    # ========================================================

    if paciente_busca:

        df_tabela = df_tabela[
            df_tabela["paciente"]
            .fillna("")
            .astype(str)
            .str.contains(
                re.escape(
                    paciente_busca
                ),
                case=False,
                na=False
            )
        ]


    # ========================================================
    # FILTRO PRONTUÁRIO
    # ========================================================

    if prontuario_busca:

        df_tabela = df_tabela[
            df_tabela[
                "prontuario_registro"
            ]
            .fillna("")
            .astype(str)
            .str.contains(
                re.escape(
                    prontuario_busca
                ),
                case=False,
                na=False
            )
        ]


    # ========================================================
    # PREPARAR TABELA
    # ========================================================

    df_tabela = df_tabela.copy()


    df_tabela["Excluir"] = (
        df_tabela.index.isin(
            st.session_state.exclusoes_pendentes
        )
    )


    # ========================================================
    # LINK DO EXAME
    # ========================================================

    df_tabela["exame_link"] = df_tabela.apply(
        criar_link_pdf,
        axis=1
    )


    colunas = [

        "data_nascimento",

        "paciente",

        "prontuario_registro",

        "exame_link",

        "data_exame",

        "data_vencimento",

        "status",

        "Excluir"

    ]


    # ========================================================
    # CONTROLAR EXCLUSÕES
    # ========================================================

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

        for linha, valores in (
            alteracoes.items()
        ):

            try:

                linha = int(
                    linha
                )

                if (
                    linha < 0
                    or
                    linha >= len(
                        indices_visiveis
                    )
                ):

                    continue

                indice_df = (
                    indices_visiveis[
                        linha
                    ]
                )

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


    # ========================================================
    # TABELA
    # ========================================================

    tabela = st.data_editor(

        df_tabela[colunas],

        use_container_width=True,

        hide_index=True,

        disabled=[

            "data_nascimento",

            "paciente",

            "prontuario_registro",

            "exame_link",

            "data_exame",

            "data_vencimento",

            "status"

        ],

        column_config={

            "exame_link": st.column_config.LinkColumn(

                "exame",

                display_text=r".*#EXAME_(.*)"

            )

        },

        key="editor_exames",

        on_change=atualizar_exclusoes

    )


    # ========================================================
    # BOTÃO EXCLUIR
    # ========================================================

    if st.session_state.exclusoes_pendentes:

        if st.button(
            "Excluir selecionados"
        ):

            st.session_state.confirmar_exclusao = True

            st.rerun()


    # ========================================================
    # CONFIRMAÇÃO DA EXCLUSÃO
    # ========================================================

    if st.session_state.confirmar_exclusao:

        with st.container(
            border=True
        ):

            st.warning(
                "⚠️ Tem certeza que deseja excluir "
                "os exames selecionados? "
                "O registro será removido do sistema "
                "e o PDF correspondente também será excluído."
            )

            col_cancelar, col_confirmar = st.columns(
                2
            )


            with col_cancelar:

                if st.button(
                    "Cancelar",
                    key="cancelar_exclusao"
                ):

                    st.session_state.confirmar_exclusao = False

                    st.session_state.exclusoes_pendentes = set()

                    st.rerun()


            with col_confirmar:

                # CORREÇÃO:
                # a key do botão não pode ser igual à variável
                # usada no st.session_state.

                if st.button(
                    "Confirmar exclusão",
                    key="botao_confirmar_exclusao"
                ):

                    erros = []

                    for id_excluir in (
                        st.session_state.exclusoes_pendentes
                    ):

                        try:

                            exame_excluir = df[
                                df["id"] == id_excluir
                            ]

                            arquivo_path = None

                            if not exame_excluir.empty:

                                arquivo_path = (
                                    exame_excluir.iloc[0].get(
                                        "arquivo_path"
                                    )
                                )


                            # Primeiro exclui do banco

                            supabase.table(
                                "exames"
                            ).delete().eq(
                                "id",
                                id_excluir
                            ).execute()


                            # Depois exclui o PDF

                            if arquivo_path:

                                try:

                                    supabase.storage.from_(
                                        "exames-pdf"
                                    ).remove(
                                        [
                                            arquivo_path
                                        ]
                                    )

                                except Exception:

                                    pass

                        except Exception as e:

                            erros.append(
                                str(e)
                            )


                    st.session_state.exclusoes_pendentes = set()

                    st.session_state.confirmar_exclusao = False


                    if erros:

                        st.session_state.mensagens_processamento = [

                            (
                                "error",
                                "Erro ao excluir um ou mais exames."
                            )

                        ]

                    else:

                        st.session_state.mensagens_processamento = [

                            (
                                "success",
                                "Os exames selecionados foram excluídos com sucesso."
                            )

                        ]


                    st.rerun()


else:

    st.info(
        "Nenhum exame cadastrado"
    )

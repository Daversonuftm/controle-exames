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
        st.session_state.modal_mensagem = None
        st.rerun()


def calcular_status(data_vencimento):
    hoje = datetime.now(
        ZoneInfo("America/Sao_Paulo")
    ).date()

    if isinstance(data_vencimento, datetime):
        data_vencimento = data_vencimento.date()

    dias_para_vencer = (data_vencimento - hoje).days

    if dias_para_vencer < 0:
        return "🔴 VENCIDO"

    if dias_para_vencer <= 30:
        return "🟡 EM ALERTA"

    return "🟢 VALIDO"


def atualizar_status_exames(user_id):
    resposta = executar_com_tentativa(
        lambda: supabase.table(
            "exames"
        ).select(
            "id, data_vencimento, status"
        ).eq(
            "hospital_id", user_id
        ).execute()
    )

    exames = resposta.data or []

    ids_vencidos = []
    ids_alerta = []
    ids_validos = []

    for exame in exames:
        try:
            data_vencimento = datetime.strptime(
                exame["data_vencimento"],
                "%d/%m/%Y"
            )

            novo_status = calcular_status(data_vencimento)
            status_atual = exame.get("status")

            if status_atual == novo_status:
                continue

            if novo_status == "🔴 VENCIDO":
                ids_vencidos.append(exame["id"])
            elif novo_status == "🟡 EM ALERTA":
                ids_alerta.append(exame["id"])
            elif novo_status == "🟢 VALIDO":
                ids_validos.append(exame["id"])
        except Exception:
            pass

    if ids_vencidos:
        executar_com_tentativa(
            lambda: supabase.table(
                "exames"
            ).update(
                {"status": "🔴 VENCIDO"}
            ).eq(
                "hospital_id", user_id
            ).in_(
                "id", ids_vencidos
            ).execute()
        )

    if ids_alerta:
        executar_com_tentativa(
            lambda: supabase.table(
                "exames"
            ).update(
                {"status": "🟡 EM ALERTA"}
            ).eq(
                "hospital_id", user_id
            ).in_(
                "id", ids_alerta
            ).execute()
        )

    if ids_validos:
        executar_com_tentativa(
            lambda: supabase.table(
                "exames"
            ).update(
                {"status": "🟢 VALIDO"}
            ).eq(
                "hospital_id", user_id
            ).in_(
                "id", ids_validos
            ).execute()
        )

    return bool(
        ids_vencidos or ids_alerta or ids_validos
    )


def normalizar_texto_comparacao(texto):
    if texto is None:
        return ""

    texto = str(texto).upper()
    texto = re.sub(r"\s+", " ", texto)
    return texto.strip()


def converter_data_exame(data):
    if not data:
        return None

    if isinstance(data, datetime):
        return data

    if isinstance(data, str):
        try:
            return datetime.strptime(data, "%d/%m/%Y")
        except Exception:
            return None

    return None


def formatar_data(data):
    data_convertida = converter_data_exame(data)

    if data_convertida:
        return data_convertida.strftime("%d/%m/%Y")

    return str(data)


def buscar_exames_usuario(user_id):
    resposta = executar_com_tentativa(
        lambda: supabase.table(
            "exames"
        ).select(
            "id, data_nascimento, paciente, prontuario_registro, exame, data_exame, data_vencimento, status, arquivo_path"
        ).eq(
            "hospital_id", user_id
        ).execute()
    )

    return resposta.data or []


if "cache_links_pdf" not in st.session_state:
    st.session_state.cache_links_pdf = {}


def criar_link_pdf(linha):
    arquivo_path = linha.get("arquivo_path")
    nome_exame = str(linha.get("exame", "EXAME"))

    if not arquivo_path:
        return nome_exame

    agora = datetime.now(
        ZoneInfo("America/Sao_Paulo")
    )

    cache = st.session_state.cache_links_pdf.get(arquivo_path)

    if cache:
        link_cache = cache.get("link")
        validade_cache = cache.get("validade")

        if (
            link_cache
            and validade_cache
            and agora < validade_cache
        ):
            return f"{link_cache}#EXAME_{nome_exame}"

    try:
        resposta = executar_com_tentativa(
            lambda: supabase.storage.from_(
                "exames-pdf"
            ).create_signed_url(
                arquivo_path, 3600
            )
        )

        if isinstance(resposta, dict):
            link = (
                resposta.get("signedURL")
                or resposta.get("signed_url")
                or resposta.get("signedUrl")
            )
        else:
            link = getattr(
                resposta, "signed_url", None
            )

            if not link:
                link = getattr(
                    resposta, "signedURL", None
                )

        if link:
            st.session_state.cache_links_pdf[
                arquivo_path
            ] = {
                "link": link,
                "validade": (
                    agora + timedelta(minutes=55)
                )
            }

            return f"{link}#EXAME_{nome_exame}"

    except Exception:
        pass

    return nome_exame


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

    data_nascimento = None

    padroes_nascimento = [
        r'Dt\.\s*Nascimento[:\s]*([0-9]{2}/[0-9]{2}/[0-9]{4})',
        r'Data\s+de\s+Nascimento[:\s]*([0-9]{2}/[0-9]{2}/[0-9]{4})',
        r'Nascimento[:\s]*([0-9]{2}/[0-9]{2}/[0-9]{4})'
    ]

    for padrao in padroes_nascimento:
        match_nascimento = re.search(
            padrao, texto, re.IGNORECASE
        )

        if match_nascimento:
            data_nascimento = datetime.strptime(
                match_nascimento.group(1),
                "%d/%m/%Y"
            )
            break

    nome = None

    padroes_nome = [
        r'Nome Civil:\s*(.*)',
        r'Nome\s*\.{0,}\s*:\s*(.*)',
        r'Paciente:\s*(.*)'
    ]

    for padrao in padroes_nome:
        match = re.search(padrao, texto)

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
            padrao, texto, re.IGNORECASE
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
        texto, re.IGNORECASE
    )

    if match_prontuario:
        prontuario_registro = re.sub(
            r'\D', '',
            match_prontuario.group(1)
        )

    if not prontuario_registro:
        match_registro = re.search(
            r'Registro.*?([0-9]{5,})',
            texto, re.IGNORECASE
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


if "user" not in st.session_state:
    st.session_state.user = None

if "ultima_atualizacao" not in st.session_state:
    st.session_state.ultima_atualizacao = None

if "filtro_status" not in st.session_state:
    st.session_state.filtro_status = "Todos os exames"

if "busca_paciente" not in st.session_state:
    st.session_state.busca_paciente = ""

if "busca_prontuario" not in st.session_state:
    st.session_state.busca_prontuario = ""

if "exclusoes_pendentes" not in st.session_state:
    st.session_state.exclusoes_pendentes = set()

if "confirmar_exclusao" not in st.session_state:
    st.session_state.confirmar_exclusao = False


st.title("Sistema de Controle de Exames")


if st.session_state.modal_mensagem:
    mostrar_modal_mensagem()
    st.stop()


if not st.session_state.user:
    st.subheader("Login")

    with st.form("form_login"):
        email = st.text_input("Email")
        senha = st.text_input("Senha", type="password")

        col1, col2 = st.columns(2)

        with col1:
            entrar = st.form_submit_button("Entrar")

        with col2:
            cadastrar = st.form_submit_button("Cadastrar")

    if entrar:
        if not email or not senha:
            abrir_modal(
                "Digite o email e a senha para efetuar o login.",
                "Dados incompletos",
                "warning"
            )
            st.rerun()

        try:
            resposta_login = executar_com_tentativa(
                lambda: supabase.auth.sign_in_with_password(
                    {
                        "email": email,
                        "password": senha
                    }
                )
            )

            user_id_login = resposta_login.user.id

            atualizar_status_exames(user_id_login)

            st.session_state.user = resposta_login
            st.session_state.ultima_atualizacao = None
            st.session_state.exclusoes_pendentes = set()
            st.session_state.confirmar_exclusao = False
            st.session_state.modal_mensagem = None
            st.session_state.cache_links_pdf = {}

            st.rerun()

        except Exception as e:
            if eh_timeout_ou_erro_conexao(e):
                abrir_modal(
                    "Houve uma demora na comunicação com o servidor. "
                    "Verifique sua conexão e tente novamente em alguns segundos.",
                    "Não foi possível conectar",
                    "error"
                )
            else:
                abrir_modal(
                    f"Não foi possível entrar no sistema.\n\n{e}",
                    "Erro no login",
                    "error"
                )

            st.rerun()

    if cadastrar:
        if not email or not senha:
            abrir_modal(
                "Digite o email e a senha para realizar o cadastro.",
                "Dados incompletos",
                "warning"
            )
            st.rerun()

        try:
            executar_com_tentativa(
                lambda: supabase.auth.sign_up(
                    {
                        "email": email,
                        "password": senha
                    }
                )
            )

            abrir_modal(
                "Cadastro realizado! Enviamos um email de confirmação "
                "para o endereço informado. Para efetuar o login, é "
                "necessário confirmar o email. Verifique também a caixa de spam.",
                "Cadastro realizado",
                "success"
            )
            st.rerun()

        except Exception as e:
            if eh_timeout_ou_erro_conexao(e):
                abrir_modal(
                    "Houve uma demora na comunicação com o servidor. "
                    "Tente novamente em alguns segundos.",
                    "Não foi possível conectar",
                    "error"
                )
            else:
                abrir_modal(
                    f"Erro ao cadastrar: {e}",
                    "Erro no cadastro",
                    "error"
                )

            st.rerun()

    st.stop()


user_id = st.session_state.user.user.id


try:
    res = executar_com_tentativa(
        lambda: supabase.table(
            "exames"
        ).select(
            "id, data_nascimento, paciente, prontuario_registro, exame, data_exame, data_vencimento, status, arquivo_path"
        ).eq(
            "hospital_id", user_id
        ).execute()
    )

    df = pd.DataFrame(res.data or [])

except Exception as e:
    if eh_timeout_ou_erro_conexao(e):
        abrir_modal(
            "Houve uma demora na comunicação com o servidor. "
            "Tente novamente em alguns segundos.",
            "Conexão temporariamente indisponível",
            "error"
        )
    else:
        abrir_modal(
            f"Não foi possível carregar os exames.\n\n{e}",
            "Erro ao carregar os exames",
            "error"
        )

    st.rerun()


if not df.empty:
    vencidos = len(
        df[
            df["status"].fillna("").str.contains(
                "VENCIDO", na=False
            )
        ]
    )

    alerta = len(
        df[
            df["status"].fillna("").str.contains(
                "ALERTA", na=False
            )
        ]
    )

    validos = len(
        df[
            df["status"].fillna("").str.contains(
                "VALIDO", na=False
            )
        ]
    )
else:
    vencidos = 0
    alerta = 0
    validos = 0


c1, c2, c3 = st.columns(3)

c1.metric("🔴 VENCIDOS", vencidos)
c2.metric("🟡 EM ALERTA", alerta)
c3.metric("🟢 VÁLIDOS", validos)


@st.fragment(run_every="1h")
def verificacao_automatica_status():
    try:
        houve_alteracao = atualizar_status_exames(user_id)

        if houve_alteracao:
            st.rerun(scope="app")
    except Exception:
        pass


verificacao_automatica_status()


col_atualizar, col_espaco, col_sair = st.columns([1, 5, 1])

with col_atualizar:
    if st.button("Atualizar status"):
        try:
            atualizar_status_exames(user_id)

            st.session_state.ultima_atualizacao = datetime.now(
                ZoneInfo("America/Sao_Paulo")
            )

            st.rerun()

        except Exception as e:
            if eh_timeout_ou_erro_conexao(e):
                abrir_modal(
                    "Houve uma demora na comunicação com o servidor. "
                    "Tente novamente em alguns segundos.",
                    "Não foi possível atualizar",
                    "error"
                )
            else:
                abrir_modal(
                    f"Erro ao atualizar os status: {e}",
                    "Erro",
                    "error"
                )

            st.rerun()


if st.session_state.ultima_atualizacao:
    st.caption(
        f"Atualizado em: "
        f"{st.session_state.ultima_atualizacao.strftime('%d/%m/%Y às %H:%M:%S')}"
    )


with col_sair:
    if st.button("Sair"):
        try:
            supabase.auth.sign_out()
        except Exception:
            pass

        st.session_state.user = None
        st.session_state.exclusoes_pendentes = set()
        st.session_state.confirmar_exclusao = False
        st.session_state.modal_mensagem = None
        st.session_state.cache_links_pdf = {}

        st.rerun()


st.divider()


arquivos = st.file_uploader(
    "Selecionar PDFs",
    type=["pdf"],
    accept_multiple_files=True
)


if st.button("Ler exames"):
    mensagens = []

    if not arquivos:
        abrir_modal(
            "Selecione pelo menos um PDF.",
            "Nenhum PDF selecionado",
            "warning"
        )
        st.rerun()

    try:
        exames_existentes = buscar_exames_usuario(user_id)
    except Exception as e:
        if eh_timeout_ou_erro_conexao(e):
            abrir_modal(
                "Houve uma demora na comunicação com o servidor. "
                "Tente novamente em alguns segundos.",
                "Não foi possível consultar os exames",
                "error"
            )
        else:
            abrir_modal(
                f"Erro ao consultar os exames: {e}",
                "Erro",
                "error"
            )
        st.rerun()

    quantidade_cadastrados = 0
    quantidade_atualizados = 0
    quantidade_ignorados = 0
    detalhes_atualizados = []
    novos_exames_processamento = []

    for arquivo in arquivos:
        try:
            arquivo_bytes = arquivo.getvalue()

            (
                data_nascimento,
                nome,
                data_exame,
                tipo_exame,
                prontuario
            ) = ler_pdf(arquivo)

        except Exception as e:
            mensagens.append(
                (
                    "error",
                    f"Erro ao ler o PDF {arquivo.name}: {e}"
                )
            )
            continue

        if not data_exame:
            mensagens.append(
                (
                    "warning",
                    f"Data não encontrada em {arquivo.name}."
                )
            )
            continue

        if not nome:
            mensagens.append(
                (
                    "warning",
                    f"Nome do paciente não encontrado em {arquivo.name}."
                )
            )
            continue

        paciente_comparacao = normalizar_texto_comparacao(nome)
        exame_comparacao = normalizar_texto_comparacao(tipo_exame)

        exames_anteriores = []

        for exame_existente in exames_existentes:
            paciente_existente = normalizar_texto_comparacao(
                exame_existente.get("paciente")
            )

            tipo_existente = normalizar_texto_comparacao(
                exame_existente.get("exame")
            )

            if (
                paciente_existente == paciente_comparacao
                and tipo_existente == exame_comparacao
            ):
                exames_anteriores.append(exame_existente)

        data_novo_exame = converter_data_exame(data_exame)

        exame_mais_recente = None
        data_mais_recente = None

        for exame_existente in exames_anteriores:
            data_existente = converter_data_exame(
                exame_existente.get("data_exame")
            )

            if not data_existente:
                continue

            if (
                data_mais_recente is None
                or data_existente > data_mais_recente
            ):
                data_mais_recente = data_existente
                exame_mais_recente = exame_existente

        if (
            exame_mais_recente is not None
            and data_novo_exame <= data_mais_recente
        ):
            quantidade_ignorados += 1
            continue

        data_vencimento = data_exame + timedelta(days=180)
        status = calcular_status(data_vencimento)

        nome_arquivo = re.sub(
            r"[^A-Za-z0-9._-]",
            "_",
            arquivo.name
        )

        nome_unico = f"{uuid.uuid4().hex}_{nome_arquivo}"
        arquivo_path = f"{user_id}/{nome_unico}"

        try:
            executar_com_tentativa(
                lambda: supabase.storage.from_(
                    "exames-pdf"
                ).upload(
                    arquivo_path,
                    arquivo_bytes,
                    {
                        "content-type": "application/pdf",
                        "upsert": "false"
                    }
                )
            )
        except Exception as e:
            if eh_timeout_ou_erro_conexao(e):
                mensagens.append(
                    (
                        "error",
                        f"Não foi possível armazenar o PDF {arquivo.name} "
                        f"porque a comunicação com o servidor demorou demais."
                    )
                )
            else:
                mensagens.append(
                    (
                        "error",
                        f"Erro ao armazenar o PDF {arquivo.name}: {e}"
                    )
                )
            continue

        novo_exame = {
            "hospital_id": user_id,
            "data_nascimento": (
                data_nascimento.strftime("%d/%m/%Y")
                if data_nascimento else None
            ),
            "paciente": nome,
            "prontuario_registro": prontuario,
            "exame": tipo_exame,
            "data_exame": data_exame.strftime("%d/%m/%Y"),
            "data_vencimento": data_vencimento.strftime("%d/%m/%Y"),
            "status": status,
            "arquivo_path": arquivo_path
        }

        try:
            resposta_insert = executar_com_tentativa(
                lambda: supabase.table(
                    "exames"
                ).insert(
                    novo_exame
                ).execute()
            )
        except Exception as e:
            try:
                executar_com_tentativa(
                    lambda: supabase.storage.from_(
                        "exames-pdf"
                    ).remove([arquivo_path])
                )
            except Exception:
                pass

            if eh_timeout_ou_erro_conexao(e):
                mensagens.append(
                    (
                        "error",
                        f"Não foi possível salvar os dados de {arquivo.name} "
                        f"porque a comunicação com o servidor demorou demais."
                    )
                )
            else:
                mensagens.append(
                    (
                        "error",
                        f"Erro ao salvar os dados de {arquivo.name}: {e}"
                    )
                )
            continue

        dados_novo = novo_exame.copy()

        if resposta_insert.data:
            dados_novo = resposta_insert.data[0]

        exames_existentes.append(dados_novo)

        ids_antigos = []
        arquivos_antigos = []
        exames_substituidos = []

        for exame_existente in exames_anteriores:
            data_existente = converter_data_exame(
                exame_existente.get("data_exame")
            )

            if not data_existente:
                continue

            if data_existente < data_novo_exame:
                ids_antigos.append(
                    exame_existente.get("id")
                )

                arquivo_antigo = exame_existente.get(
                    "arquivo_path"
                )

                if arquivo_antigo:
                    arquivos_antigos.append(
                        arquivo_antigo
                    )

                exames_substituidos.append(
                    exame_existente
                )

        exclusao_antigos_ok = True

        if ids_antigos:
            try:
                executar_com_tentativa(
                    lambda: supabase.table(
                        "exames"
                    ).delete().eq(
                        "hospital_id", user_id
                    ).in_(
                        "id", ids_antigos
                    ).execute()
                )
            except Exception:
                exclusao_antigos_ok = False

                mensagens.append(
                    (
                        "error",
                        f"O novo exame de {nome} foi cadastrado, "
                        f"mas não foi possível remover todos os "
                        f"exames anteriores. Verifique a tabela."
                    )
                )

        if exclusao_antigos_ok and arquivos_antigos:
            try:
                executar_com_tentativa(
                    lambda: supabase.storage.from_(
                        "exames-pdf"
                    ).remove(arquivos_antigos)
                )
            except Exception:
                mensagens.append(
                    (
                        "warning",
                        f"O novo exame de {nome} foi cadastrado, "
                        f"mas um ou mais PDFs anteriores não puderam "
                        f"ser removidos do armazenamento."
                    )
                )

        for caminho in arquivos_antigos:
            st.session_state.cache_links_pdf.pop(
                caminho, None
            )

        if ids_antigos:
            exames_existentes = [
                exame
                for exame in exames_existentes
                if exame.get("id") not in ids_antigos
            ]

        if exames_substituidos:
            exame_antigo_mais_recente = max(
                exames_substituidos,
                key=lambda x: (
                    converter_data_exame(
                        x.get("data_exame")
                    ) or datetime.min
                )
            )

            data_antiga = converter_data_exame(
                exame_antigo_mais_recente.get("data_exame")
            )

            detalhes_atualizados.append(
                (
                    tipo_exame,
                    nome,
                    formatar_data(data_antiga),
                    formatar_data(data_novo_exame)
                )
            )

            quantidade_atualizados += 1
        else:
            quantidade_cadastrados += 1
            novos_exames_processamento.append(nome)

    # ========================================================
    # RESUMO DO PROCESSAMENTO
    # ========================================================

    quantidade_erros = sum(
        1
        for tipo, mensagem in mensagens
        if tipo == "error"
    )

    quantidade_alertas = sum(
        1
        for tipo, mensagem in mensagens
        if tipo == "warning"
    )

    novos_por_paciente = {}

    for paciente_novo in novos_exames_processamento:
        novos_por_paciente[paciente_novo] = (
            novos_por_paciente.get(paciente_novo, 0) + 1
        )

    linhas_resumo = [
        "Processamento concluído",
        "",
        "Novos exames:"
    ]

    if novos_por_paciente:
        for paciente_novo, quantidade_nova in novos_por_paciente.items():
            palavra_exame = (
                "exame" if quantidade_nova == 1 else "exames"
            )
            linhas_resumo.append(
                f"• {paciente_novo}: {quantidade_nova} {palavra_exame}"
            )
    else:
        linhas_resumo.append(
            "• Nenhum exame novo foi cadastrado."
        )

    linhas_resumo += [
        "",
        "Exames atualizados:"
    ]

    if detalhes_atualizados:
        for tipo_exame, paciente, data_antiga, data_nova in detalhes_atualizados:
            linhas_resumo.append(
                f"• {tipo_exame} — {paciente} — "
                f"{data_antiga} → {data_nova}"
            )
    else:
        linhas_resumo.append(
            "• Nenhum exame foi atualizado."
        )

    if quantidade_ignorados > 0:
        linhas_resumo.append("")

        if quantidade_ignorados == 1:
            linhas_resumo.append(
                "1 exame não foi cadastrado, pois já havia uma versão "
                "igual ou mais recente."
            )
        else:
            linhas_resumo.append(
                f"{quantidade_ignorados} exames não foram cadastrados, "
                "pois já havia uma versão igual ou mais recente."
            )

    linhas_resumo += [
        "",
        "Erros:"
    ]

    if quantidade_erros == 0:
        linhas_resumo.append(
            "• Nenhum erro encontrado."
        )
    else:
        for tipo, mensagem in mensagens:
            if tipo == "error":
                linhas_resumo.append(
                    f"• {mensagem}"
                )

    st.session_state.modal_mensagem = "\n".join(linhas_resumo)

    if quantidade_erros > 0:
        st.session_state.modal_tipo = "error"
    elif quantidade_alertas > 0:
        st.session_state.modal_tipo = "warning"
    elif quantidade_cadastrados > 0 or quantidade_atualizados > 0:
        st.session_state.modal_tipo = "success"
    else:
        st.session_state.modal_tipo = "info"

    st.session_state.modal_titulo = "Resultado"

    st.rerun()


st.subheader("Tabela de exames")


if not df.empty:
    col_filtro_status, col_filtro_paciente, col_filtro_prontuario = st.columns(3)

    with col_filtro_status:
        with st.popover("🔎 Status"):
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

            st.session_state.filtro_status = filtro_status

        st.caption(st.session_state.filtro_status)

    with col_filtro_paciente:
        with st.popover("👤 Paciente"):
            paciente_busca = st.text_input(
                "Buscar paciente",
                value=st.session_state.busca_paciente,
                placeholder="Digite o nome",
                key="paciente_busca_input"
            )

            st.session_state.busca_paciente = paciente_busca

        if st.session_state.busca_paciente:
            st.caption(
                f"Paciente: {st.session_state.busca_paciente}"
            )
        else:
            st.caption("Nenhum paciente selecionado")

    with col_filtro_prontuario:
        with st.popover("📋 Prontuário"):
            prontuario_busca = st.text_input(
                "Buscar prontuário",
                value=st.session_state.busca_prontuario,
                placeholder="Digite o número",
                key="prontuario_busca_input"
            )

            st.session_state.busca_prontuario = prontuario_busca

        if st.session_state.busca_prontuario:
            st.caption(
                f"Prontuário: {st.session_state.busca_prontuario}"
            )
        else:
            st.caption("Nenhum prontuário selecionado")

    filtro = st.session_state.filtro_status
    paciente_busca = st.session_state.busca_paciente
    prontuario_busca = st.session_state.busca_prontuario

    if filtro == "🔴 Vencidos":
        df_tabela = df[
            df["status"].fillna("").str.contains(
                "VENCIDO", na=False
            )
        ]
    elif filtro == "🟡 Em alerta":
        df_tabela = df[
            df["status"].fillna("").str.contains(
                "ALERTA", na=False
            )
        ]
    elif filtro == "🟢 Válidos":
        df_tabela = df[
            df["status"].fillna("").str.contains(
                "VALIDO", na=False
            )
        ]
    else:
        df_tabela = df

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

    df_tabela = df_tabela.copy()

    df_tabela["Excluir"] = df_tabela.index.isin(
        st.session_state.exclusoes_pendentes
    )

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

    def atualizar_exclusoes():
        estado_editor = st.session_state.get(
            "editor_exames", {}
        )

        alteracoes = estado_editor.get(
            "edited_rows", {}
        )

        indices_visiveis = list(
            df_tabela.index
        )

        for linha, valores in alteracoes.items():
            try:
                linha = int(linha)

                if (
                    linha < 0
                    or linha >= len(indices_visiveis)
                ):
                    continue

                indice_df = indices_visiveis[linha]

                id_exame = df.loc[
                    indice_df, "id"
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

    if st.button(
        "Excluir selecionados",
        disabled=not bool(st.session_state.exclusoes_pendentes)
    ):
        st.session_state.confirmar_exclusao = True
        st.rerun()

    if st.session_state.confirmar_exclusao:
        @st.dialog("Pense bem!", dismissible=False)
        def mostrar_confirmacao_exclusao():
            quantidade = len(
                st.session_state.exclusoes_pendentes
            )

            if quantidade == 1:
                texto_quantidade = "Você selecionou 1 exame."
            else:
                texto_quantidade = (
                    f"Você selecionou {quantidade} exames."
                )

            st.write(texto_quantidade)

            st.write(
                "Tem certeza que deseja excluir os exames selecionados?"
            )

            st.write(
                "O registro será removido do sistema "
                "e o PDF correspondente também será excluído."
            )

            st.divider()

            col_cancelar, col_confirmar = st.columns(2)

            with col_cancelar:
                if st.button(
                    "Cancelar",
                    key="cancelar_exclusao",
                    use_container_width=True
                ):
                    st.session_state.confirmar_exclusao = False
                    st.session_state.exclusoes_pendentes = set()
                    st.rerun()

            with col_confirmar:
                if st.button(
                    "Confirmar exclusão",
                    key="botao_confirmar_exclusao",
                    use_container_width=True
                ):
                    ids_excluir = list(
                        st.session_state.exclusoes_pendentes
                    )

                    caminhos_pdfs = []

                    for id_excluir in ids_excluir:
                        exame_excluir = df[
                            df["id"] == id_excluir
                        ]

                        if not exame_excluir.empty:
                            arquivo_path = exame_excluir.iloc[0].get(
                                "arquivo_path"
                            )

                            if arquivo_path:
                                caminhos_pdfs.append(
                                    arquivo_path
                                )

                    try:
                        executar_com_tentativa(
                            lambda: supabase.table(
                                "exames"
                            ).delete().eq(
                                "hospital_id", user_id
                            ).in_(
                                "id", ids_excluir
                            ).execute()
                        )

                        erro_storage = False

                        if caminhos_pdfs:
                            try:
                                executar_com_tentativa(
                                    lambda: supabase.storage.from_(
                                        "exames-pdf"
                                    ).remove(caminhos_pdfs)
                                )
                            except Exception:
                                erro_storage = True

                        for caminho in caminhos_pdfs:
                            st.session_state.cache_links_pdf.pop(
                                caminho, None
                            )

                        st.session_state.exclusoes_pendentes = set()
                        st.session_state.confirmar_exclusao = False

                        if erro_storage:
                            abrir_modal(
                                "Os exames foram excluídos da tabela, "
                                "mas um ou mais PDFs não puderam ser "
                                "removidos do armazenamento.",
                                "Exclusão parcialmente concluída",
                                "warning"
                            )
                        else:
                            abrir_modal(
                                "Os exames selecionados foram excluídos com sucesso.",
                                "Exclusão concluída",
                                "success"
                            )

                        st.rerun()

                    except Exception as e:
                        st.session_state.confirmar_exclusao = False

                        if eh_timeout_ou_erro_conexao(e):
                            abrir_modal(
                                "Houve uma demora na comunicação com o servidor. "
                                "Nenhum exame deve ser removido até que a operação "
                                "seja concluída. Tente novamente em alguns segundos.",
                                "Não foi possível concluir a exclusão",
                                "error"
                            )
                        else:
                            abrir_modal(
                                f"Não foi possível excluir os exames.\n\n{e}",
                                "Erro na exclusão",
                                "error"
                            )

                        st.rerun()

        mostrar_confirmacao_exclusao()
else:
    st.info("Nenhum exame cadastrado")

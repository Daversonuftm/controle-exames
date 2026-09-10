import streamlit as st
import pandas as pd
import pdfplumber
import re
import extra_streamlit_components as stx

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from supabase import create_client


# 🔑 SUPABASE
url = "https://dpouzkapdaipnfnlsrio.supabase.co"
key = "sb_publishable_hhN-A_o0Q9Y6o8lTGr2xCw_iBbSSXca"

supabase = create_client(url, key)

st.set_page_config(
    page_title="Controle de Exames",
    layout="wide"
)


# ================= COOKIE MANAGER =================

cookie_manager = stx.CookieManager(
    key="controle_exames_cookies"
)


# ================= SESSION STATE =================

if "user" not in st.session_state:
    st.session_state.user = None

if "exclusoes_pendentes" not in st.session_state:
    st.session_state.exclusoes_pendentes = set()

if "confirmar_saida" not in st.session_state:
    st.session_state.confirmar_saida = False

if "aviso_recarregamento" not in st.session_state:
    st.session_state.aviso_recarregamento = False

if "ultima_atualizacao" not in st.session_state:
    st.session_state.ultima_atualizacao = None

if "status_verificado" not in st.session_state:
    st.session_state.status_verificado = False


# ================= RESTAURAR LOGIN APÓS F5 =================

if st.session_state.user is None:

    access_token = cookie_manager.get(
        "controle_exames_access"
    )

    refresh_token = cookie_manager.get(
        "controle_exames_refresh"
    )

    pendencia_recarregamento = cookie_manager.get(
        "controle_exames_pendente"
    )

    if access_token and refresh_token:

        try:

            supabase.auth.set_session(
                access_token,
                refresh_token
            )

            sessao = supabase.auth.get_session()

            usuario = supabase.auth.get_user()

            if sessao.session and usuario.user:

                st.session_state.user = {
                    "session": sessao.session,
                    "user": usuario.user
                }

                # Salva os tokens atualizados caso o Supabase
                # tenha renovado a sessão
                cookie_manager.set(
                    "controle_exames_access",
                    sessao.session.access_token,
                    max_age=60 * 60 * 24 * 30,
                    secure=True,
                    same_site="lax"
                )

                cookie_manager.set(
                    "controle_exames_refresh",
                    sessao.session.refresh_token,
                    max_age=60 * 60 * 24 * 30,
                    secure=True,
                    same_site="lax"
                )

                if pendencia_recarregamento == "1":

                    st.session_state.aviso_recarregamento = True

                    cookie_manager.delete(
                        "controle_exames_pendente"
                    )

        except Exception:

            st.session_state.user = None


# ================= TÍTULO =================

st.title(
    "Sistema de Controle de Exames"
)


# ================= LOGIN =================

if not st.session_state.user:

    st.subheader("Login")

    with st.form("form_login"):

        email = st.text_input(
            "Email"
        )

        senha = st.text_input(
            "Senha",
            type="password"
        )

        col1, col2 = st.columns(2)

        with col1:

            entrar = st.form_submit_button(
                "Entrar"
            )

        with col2:

            cadastrar = st.form_submit_button(
                "Cadastrar"
            )


    # ================= ENTRAR =================

    if entrar:

        if not email or not senha:

            st.warning(
                "Digite o email e a senha para efetuar o login."
            )

        else:

            try:

                resposta = supabase.auth.sign_in_with_password({

                    "email": email,

                    "password": senha

                })

                sessao = resposta.session

                usuario = resposta.user

                if sessao and usuario:

                    st.session_state.user = {

                        "session": sessao,

                        "user": usuario

                    }

                    # Guarda a sessão no navegador
                    cookie_manager.set(
                        "controle_exames_access",
                        sessao.access_token,
                        max_age=60 * 60 * 24 * 30,
                        secure=True,
                        same_site="lax"
                    )

                    cookie_manager.set(
                        "controle_exames_refresh",
                        sessao.refresh_token,
                        max_age=60 * 60 * 24 * 30,
                        secure=True,
                        same_site="lax"
                    )

                    st.session_state.exclusoes_pendentes = set()

                    st.session_state.confirmar_saida = False

                    st.rerun()

            except Exception as e:

                mensagem_erro = str(e)

                if (
                    "Email not confirmed" in mensagem_erro
                    or
                    "email not confirmed" in mensagem_erro.lower()
                    or
                    "not confirmed" in mensagem_erro.lower()
                ):

                    st.error(
                        "Para efetuar o login, é necessário confirmar o email. "
                        "Verifique sua caixa de entrada e, se necessário, "
                        "a caixa de spam."
                    )

                else:

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

try:

    supabase.auth.set_session(

        st.session_state.user["session"].access_token,

        st.session_state.user["session"].refresh_token

    )

except Exception:

    st.session_state.user = None

    cookie_manager.delete(
        "controle_exames_access"
    )

    cookie_manager.delete(
        "controle_exames_refresh"
    )

    st.rerun()


user_id = st.session_state.user["user"].id


# ================= FUNÇÕES =================

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


    tipo_exame = identificar_exame(
        texto
    )


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


    if isinstance(
        data_vencimento,
        datetime
    ):

        data_vencimento = data_vencimento.date()


    dias_para_vencer = (
        data_vencimento - hoje
    ).days


    if dias_para_vencer < 0:

        return "🔴 VENCIDO"


    if dias_para_vencer <= 30:

        return "🟡 EM ALERTA"


    return "🟢 VALIDO"


# ================= ATUALIZAR STATUS NO BANCO =================

def atualizar_status_banco():

    exames = supabase.table(
        "exames"
    ).select(
        "id, data_vencimento, status"
    ).eq(
        "hospital_id",
        user_id
    ).execute()


    houve_mudanca = False


    for exame in exames.data:

        try:

            data_vencimento = datetime.strptime(
                exame["data_vencimento"],
                "%d/%m/%Y"
            )


            novo_status = calcular_status(
                data_vencimento
            )


            if exame.get("status") != novo_status:

                supabase.table(
                    "exames"
                ).update({

                    "status": novo_status

                }).eq(
                    "id",
                    exame["id"]
                ).execute()


                houve_mudanca = True


        except Exception:

            pass


    return houve_mudanca


# ================= ATUALIZAÇÃO AO ENTRAR =================

if not st.session_state.status_verificado:

    if not st.session_state.exclusoes_pendentes:

        atualizar_status_banco()

    st.session_state.status_verificado = True


# ================= BANCO =================

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


# ================= ATUALIZAÇÃO AUTOMÁTICA A CADA 1 HORA =================

@st.fragment(
    run_every="1h"
)
def atualizacao_automatica():

    # Não atualiza automaticamente enquanto
    # existirem alterações não salvas
    if st.session_state.exclusoes_pendentes:

        return


    houve_mudanca = atualizar_status_banco()


    if houve_mudanca:

        st.rerun()


atualizacao_automatica()


# ================= DASHBOARD =================

if not df.empty:

    # Recalcula o dataframe depois das atualizações
    res_atualizado = supabase.table(
        "exames"
    ).select(
        "*"
    ).eq(
        "hospital_id",
        user_id
    ).execute()


    df = pd.DataFrame(
        res_atualizado.data
    )


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


# ================= ATUALIZAR STATUS + SAIR =================

col_atualizar, col_espaco, col_sair = st.columns(
    [1, 5, 1]
)


with col_atualizar:

    if st.button(
        "Atualizar status"
    ):

        if st.session_state.exclusoes_pendentes:

            st.warning(
                "Existem alterações não salvas. "
                "Salve ou desfaça essas alterações antes "
                "de atualizar os status."
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


if st.session_state.ultima_atualizacao:

    st.caption(
        f"Atualizado em: "
        f"{st.session_state.ultima_atualizacao.strftime('%d/%m/%Y às %H:%M:%S')}"
    )


# ================= SAIR =================

with col_sair:

    if st.button(
        "Sair"
    ):

        if st.session_state.exclusoes_pendentes:

            st.session_state.confirmar_saida = True

        else:

            try:

                supabase.auth.sign_out()

            except Exception:

                pass


            cookie_manager.delete(
                "controle_exames_access"
            )

            cookie_manager.delete(
                "controle_exames_refresh"
            )

            cookie_manager.delete(
                "controle_exames_pendente"
            )


            st.session_state.user = None

            st.session_state.exclusoes_pendentes = set()

            st.session_state.confirmar_saida = False

            st.rerun()


# ================= AVISO DE RECARREGAMENTO =================

if st.session_state.aviso_recarregamento:

    st.warning(
        "⚠️ A página foi recarregada e havia alterações "
        "que ainda não tinham sido salvas. "
        "Essas alterações não foram salvas."
    )


    if st.button(
        "Entendi"
    ):

        st.session_state.aviso_recarregamento = False

        st.rerun()


# ================= CONFIRMAÇÃO DE SAÍDA =================

if st.session_state.confirmar_saida:

    st.warning(
        "⚠️ Existem alterações não salvas. "
        "Se você sair agora, essas alterações serão perdidas."
    )


    col_continuar, col_sair_confirmar = st.columns(2)


    with col_continuar:

        if st.button(
            "Continuar editando"
        ):

            st.session_state.confirmar_saida = False

            st.rerun()


    with col_sair_confirmar:

        if st.button(
            "Sair sem salvar"
        ):

            try:

                supabase.auth.sign_out()

            except Exception:

                pass


            cookie_manager.delete(
                "controle_exames_access"
            )

            cookie_manager.delete(
                "controle_exames_refresh"
            )

            cookie_manager.delete(
                "controle_exames_pendente"
            )


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


if st.button(
    "Ler exames"
):

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
            ) = ler_pdf(
                arquivo
            )


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


            supabase.table(
                "exames"
            ).insert({

                "hospital_id": user_id,

                "cpf": cpf,

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


    df_tabela = df_tabela.copy()


    df_tabela["Excluir"] = df_tabela.index.isin(
        st.session_state.exclusoes_pendentes
    )


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


    # ================= FUNÇÃO EXCLUSÕES =================

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


                if (
                    linha < 0
                    or
                    linha >= len(indices_visiveis)
                ):

                    continue


                indice_df = indices_visiveis[
                    linha
                ]


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


        # Guarda a informação de que existem alterações
        # não salvas no navegador
        if st.session_state.exclusoes_pendentes:

            cookie_manager.set(
                "controle_exames_pendente",
                "1",
                max_age=60 * 60 * 24,
                secure=True,
                same_site="lax"
            )

        else:

            cookie_manager.delete(
                "controle_exames_pendente"
            )


    # ================= TABELA BLOQUEADA =================

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

        key="editor_exames",

        on_change=atualizar_exclusoes

    )


    # ================= SALVAR =================

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


            cookie_manager.delete(
                "controle_exames_pendente"
            )


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

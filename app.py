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

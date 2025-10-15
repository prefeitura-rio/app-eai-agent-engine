async def iptu_api(
    request_data: dict, 
    endpoint: str = "", 
    token: str = "", 
    inscricao: str = "", 
    exercicio: str = None, 
    guia: str = None, 
    cotas: str = None, 
    data: dict = {}
) -> Union[List[Dict], Dict]:
    params = {
        "token": token,
        "inscricao": inscricao,
    }

    if exercicio:
        params["exercicio"] = exercicio
    if guia:
        params["guia"] = guia
    if cotas:
        params["cotas"] = cotas
    
    query_string = urllib.parse.urlencode(params)
    url = f"{config.IPTU_API_URL}/{endpoint}?{query_string}"

    try:
        response = await internal_request(
            url=url,
            method="GET",
            request_kwargs={"verify": False},
        )
    except json_std.decoder.JSONDecodeError as e:
        logger_info_with_id(
            request_data,
            f"Erro ao decodificar a resposta da API: {str(e)}"
        )
        return {"success": False, "error": "Resposta da API inválida."}
    except Exception as e:
        logger_info_with_id(
            request_data,
            f"Erro ao chamar internal_request: {str(e)}"
        )
        return {"success": False, "error": str(e)}

    if response is None:
        logger_info_with_id(
            request_data,
            "A API não retornou nada. Algum erro aconteceu."
        )
        return {"success": False, "error": "Nenhuma resposta da API."}

    if isinstance(response, dict) and not response.get("success", True):
        logger_info_with_id(
            request_data,
            f"Erro na API do IPTU: {response.get('error')}"
        )
        return response

    logger_info_with_id(request_data, f'Resposta da solicitação GET: {response}')
    return response

async def upload_base64_to_gcs(base64_content, folder_name):
    """
    Faz o upload de um arquivo em base64 para o Google Cloud Storage e retorna uma URL assinada válida por 7 dias.

    Args:
        base64_content (str): Conteúdo do arquivo codificado em base64.
        folder_name (str): Nome da pasta dentro do bucket onde o arquivo será armazenado.

    Returns:
        str: URL assinada para download do arquivo válida por 7 dias.
    """
    google_credentials = await get_credentials_from_env()
    client = storage.Client(credentials=google_credentials)
    bucket = client.bucket("temp_files_chatbot")
    
    file_data = base64.b64decode(base64_content)
    
    file_name = f"{folder_name}/{uuid.uuid4()}.pdf"
    
    blob = bucket.blob(file_name)
    
    blob.upload_from_string(file_data, content_type='application/pdf')
    
    expiration = timedelta(days=7)

    signed_url = blob.generate_signed_url(expiration=expiration)
    
    return signed_url

def convert_list_to_string(input_list):
    """
    Converte uma lista de números float para uma string formatada.

    Args:
        input_list (list): Lista de números float.

    Returns:
        str: String formatada com dois dígitos para cada número, separados por vírgula.
    """
    formatted_string = ", ".join(f"{int(num):02}" for num in input_list)
    return formatted_string

async def get_short_url(url):
    """
    Envia uma URL para o endpoint de encurtamento de URL e retorna a URL encurtada.

    :param url: A URL que será encurtada.
    :return: A URL encurtada como string.
    """
    api_url = "https://share.dados.rio/api/urls/"
    headers = {
        "Authorization": f"Bearer {config.SHARE_DADOS_RIO_API_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {"url": url}

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(api_url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
            return f"https://share.dados.rio/{data['short_url']}"
        except httpx.RequestError as e:
            print(f"Erro ao encurtar a URL: {e}")
            return None
        
def validar_cotas_string(cotas_escolhidas: str) -> Tuple[bool, str]:
    """
    Valida e ajusta a string de cotas.

    A string deve:
    - Conter apenas números de "01" a "10".
    - Os números devem ser únicos e ordenados.
    - Estar no formato de dois dígitos, separados por vírgula e espaço.

    Args:
        cotas_str (str): String de cotas a ser validada.

    Returns:
        Tuple[bool, str]: Um booleano indicando se a validação passou e uma mensagem de erro ou a string ajustada.
    """
    if not cotas_escolhidas:
        return False, "A string de cotas está vazia."

    cotas_lista = cotas_escolhidas.split(", ")

    padrao = re.compile(r'^(0[1-9]|10)$')
    for cota in cotas_lista:
        if not padrao.match(cota):
            return False, f"A cota '{cota}' está em formato inválido. Deve estar entre '01' e '10'."

    try:
        cotas_numericas = [int(cota) for cota in cotas_lista]
    except ValueError:
        return False, "Todas as cotas devem ser números inteiros entre 01 e 10."

    cotas_numericas = sorted(set(cotas_numericas))

    for cota in cotas_numericas:
        if not 1 <= cota <= 10:
            return False, f"A cota '{cota:02}' está fora do intervalo permitido (01 a 10)."
        
    for i in range(1, len(cotas_numericas)):
        if cotas_numericas[i] != cotas_numericas[i - 1] + 1:
            return False, "As cotas não estão em sequência correta."

    cotas_ajustadas = ", ".join(f"{cota:02}" for cota in cotas_numericas)

    return True, cotas_ajustadas

async def consultar_sequencia_cotas(request_data: dict, cotas: str, inscricao: str, exercicio: str, guia: str) -> Dict[str, str]:
    cotas_list = [cota.strip() for cota in cotas.split(",")]
    cotas_resultado = {}

    for cota in cotas_list:
        api_response = await iptu_api(
            request_data=request_data,
            token=config.IPTU_API_TOKEN,
            endpoint="ConsultarDARM",
            inscricao=inscricao, 
            exercicio=exercicio,
            guia=guia,
            cotas=cota
        )
    
        sequencia_numerica = api_response.get("SequenciaNumerica", "Não disponível")
        cotas_resultado[cota] = sequencia_numerica

    return cotas_resultado

async def busca_imovel_rest_via_vpn(pem_public_key: str, raw_token: str, inscricao: str):
    """
    Faz uma requisição GET na API REST de IPTU utilizando a VPN interna.

    Args:
        pem_public_key (str): Chave pública no formato PEM.
        raw_token (str): Token original a ser criptografado.
        inscricao (str): Número da inscrição do imóvel.

    Returns:
        dict: Resposta JSON da API.
    """
    encrypted_token = encrypt_token_rsa(chave_publica_pem=pem_public_key, token=raw_token)

    auth_header = f"Basic {encrypted_token}"

    url = f"https://wbsvcp01.smf.rio.rj.gov.br/dotnet/webapi/wafazenda_iptu/api/BuscaImovel6/{inscricao}"
    headers = {
        "Authorization": auth_header
    }

    response = await internal_request(url, "GET", {"headers": headers})
    
    if not response or "logradouro" not in response:
        return {"error": "Dados inválidos ou imóvel não encontrado."}

    # Construindo o endereço completo
    endereco_completo = f"{response['tipoLogradouro']} {response['nomeLogradouro']}, {response['numPorta']}, {response.get('complEndereco', '')}, {response['bairro']}, {response['cep']}"

    # Retornando os dados desejados
    return {
        "endereco_completo": endereco_completo.strip(", "),
        "proprietario_principal": response["proprietarioPrincipal"]
    }

def encrypt_token_rsa(chave_publica_pem: str, token: str) -> str:
    utc_now = dt.datetime.now(dt.timezone.utc)
    datahora_str = utc_now.strftime("%d/%m/%Y %H:%M:%S")

    dataHoraToken = datahora_str + token

    dataHoraToken_bytes = dataHoraToken.encode("utf-16-le")

    pem_formatado = convert_base64_to_pem(chave_publica_pem)
    public_key = serialization.load_pem_public_key(
        pem_formatado.encode()
    )
    
    encrypted = public_key.encrypt(
        dataHoraToken_bytes,
        padding.PKCS1v15()
    )

    return base64.b64encode(encrypted).decode("ascii")


def convert_base64_to_pem(base64_key: str) -> str:
    if "BEGIN PUBLIC KEY" in base64_key:
        return base64_key.strip()
    wrapped = textwrap.fill(base64_key, 64)
    return f"-----BEGIN PUBLIC KEY-----\n{wrapped}\n-----END PUBLIC KEY-----"


### PART 2

async def get_consultar_guias_iptu(request_data: dict) -> Tuple[str, Dict[str, Any]]:
    parameters = request_data.get("sessionInfo", {}).get("parameters", {})
    parameters["inscricao"] = parameters['inscricao'].translate(str.maketrans('', '', string.punctuation))
    api_kwargs = {
        "request_data": request_data,
        "token": config.IPTU_API_TOKEN,
        "endpoint": "ConsultarGuias",
        "inscricao": parameters["inscricao"]
    }
    
    api_response = await iptu_api(**api_kwargs)

    if isinstance(api_response, dict) and not api_response.get("success", True):
        parameters["error_iptu_guias"] = True
        return MESSAGE, parameters
    
    guias = {}

    for guia in api_response:
        if guia.get("Situacao", {}).get("codigo") == "01": # em aberto
            guias.setdefault(guia.get("Exercicio"), []).append(guia.get("NGuia"))
            
    if not guias:
        parameters["sem_guias"] = True
        return MESSAGE, parameters
    
    k, v = list(guias.keys()), list(guias.values())

    parameters.update({
        "guias": guias,
        "exercicios": k,
        "mais_de_um_exercicio": len(k) > 1,
        "mais_de_uma_guia": not((len(k) == 1) and (len(v) == 1)),
        "guias_formatadas": "\n".join([f"{i + 1}. Guia {mes}/{ano}" for i, (ano, meses) in enumerate(guias.items()) for mes in meses])
    })
    
    if not parameters["mais_de_uma_guia"]:
        parameters.update({"guia": v[0][0], "exercicio": k[0]})

    return MESSAGE, parameters

async def verifica_guia(request_data: dict) -> Tuple[str, Dict[str, Any]]:
    parameters = request_data.get("sessionInfo", {}).get("parameters", {})
    
    try:
        idx = int(parameters["guia"]) - 1
        exercicio, guia = [(e, g) for e, guia in parameters["guias"].items() for g in guia][idx]
        parameters["exercicio"] = exercicio
        parameters["guia"] = guia
    except:
        parameters["error_iptu_guias"] = True

    return MESSAGE, parameters

async def get_consultar_cotas_iptu(request_data: dict) -> Tuple[str, Dict[str, Any]]:
    parameters = request_data.get("sessionInfo", {}).get("parameters", {})

    api_response = await iptu_api(
        request_data=request_data,
        token=config.IPTU_API_TOKEN,
        endpoint="ConsultarCotas",
        inscricao=parameters.get("inscricao"), 
        exercicio=parameters.get("exercicio"),
        guia=parameters.get("guia")
    )

    if isinstance(api_response, dict) and not api_response.get("success", True):
        parameters["error_iptu_cotas"] = True
        message = "Não foram encontradas cotas para a guia de IPTU informada. Confira os dados e tente novamente."
        return message, parameters
    
    cotas = []
    for _, cota in enumerate(api_response.get("Cotas", [])):
        if cota.get("Situacao", {}).get("codigo") != "01":
            cota_info = {
                "NCota": cota.get("NCota"),
                "ValorCota": cota.get("ValorCota", "0"),
                "DataVencimento": cota.get("DataVencimento"),
            }
            cotas.append(cota_info)

    if not cotas:
        parameters["sem_cotas"] = True
        return MESSAGE, parameters

    message_lines = [
        f"*Cota:* {cota['NCota']}\nR$ {cota['ValorCota']} - Vencimento em {cota['DataVencimento']}\n\n"
        for cota in cotas
    ]
    
    message = "".join(message_lines)

    return message, parameters


def formatar_valor_cota(valor: str) -> float:
    return float(valor.replace(".", "").replace(",", "."))


def gerar_detalhes(api_response: dict) -> Dict[str, str]:
    return {
        "Exercicio": api_response.get("Exercicio", "Não disponível"),
        "NGuia": api_response.get("NGuia", "Não disponível"),
        "ValorAPagar": api_response.get("ValorAPagar", "Não disponível"),
        "SequenciaNumerica": api_response.get("SequenciaNumerica", "Não disponível"),
        "Endereco": api_response.get("Endereco", "Não disponível"),
        "Nome": api_response.get("Nome", "Não disponível"),
    }


async def gerar_mensagem(inscricao, cotas_detalhes: List[Dict[str, str]], cotas: str, valor_total: float) -> str:
    cotas_formatadas = cotas.replace(", ", "\n")
    
    public_key_pem = config.WA_IPTU_PUBLIC_KEY
    raw_token = config.WA_IPTU_TOKEN
    
    response = await busca_imovel_rest_via_vpn(pem_public_key=public_key_pem, raw_token=raw_token, inscricao=inscricao)
    
    endereco = response.get("endereco_completo", "Não disponível")
    nome = response.get("proprietario_principal", "Não disponível")
    
    return "\n".join([
        "Confirma os dados do imóvel abaixo para emitir a guia de pagamento?\n\nResponda SIM ou NÃO.\n",
        f"*Endereço do imóvel:*\n{endereco}\n",
        f"*Contribuinte:*\n{nome}\n",
        f"*Guia:*\n{cotas_detalhes['NGuia']}/{cotas_detalhes['Exercicio']}\n",
        f"*Cotas:*\n{cotas_formatadas}\n",
        f"*Valor total:*\nR$ {valor_total:.2f}"
    ])


async def get_consultar_darm_iptu(request_data: dict) -> Tuple[str, Dict[str, Any]]:
    parameters = request_data.get("sessionInfo", {}).get("parameters", {})
    cotas = convert_list_to_string(parameters.get("cotas"))
    is_valid, cotas = validar_cotas_string(cotas)

    if not is_valid:
        parameters["error_api_iptu"] = True
        return MESSAGE, parameters

    api_response = await iptu_api(
        request_data=request_data,
        token=config.IPTU_API_TOKEN,
        endpoint="ConsultarDARM",
        inscricao=parameters.get("inscricao"), 
        exercicio=parameters.get("exercicio"),
        guia=parameters.get("guia"),
        cotas=cotas
    )

    if not api_response.get("success", True):
        parameters["error_api_iptu"] = True
        return MESSAGE, parameters
    
    sequencia_numerica = api_response.get("SequenciaNumerica")
    if not sequencia_numerica:
        parameters["error_api_iptu"] = True
        return MESSAGE, parameters

    valor_total = sum(
        formatar_valor_cota(cota.get("valor", "0")) for cota in api_response.get("Cotas", [])
    )

    cotas_detalhes = gerar_detalhes(api_response)

    if not api_response.get("Cotas"):
        message = "Não foram encontradas cotas de IPTU para os dados informados."
    else:
        message = await gerar_mensagem(parameters.get("inscricao"), cotas_detalhes, cotas, valor_total)
        parameters["msg_cotas_mensais"] = message

    return MESSAGE, parameters


async def get_consultar_darm_cota_unica_iptu(request_data: dict) -> Tuple[str, Dict[str, Any]]:
    parameters = request_data.get("sessionInfo", {}).get("parameters", {})
    cotas = "00"

    api_response = await iptu_api(
        request_data=request_data,
        token=config.IPTU_API_TOKEN,
        endpoint="ConsultarDARM",
        inscricao=parameters.get("inscricao"), 
        exercicio=parameters.get("exercicio"),
        guia=parameters.get("guia"),
        cotas=cotas
    )

    if not api_response.get("success", True):
        parameters["error_api_iptu"] = True
        return MESSAGE, parameters
    
    sequencia_numerica = api_response.get("SequenciaNumerica")
    if not sequencia_numerica:
        parameters["error_api_iptu"] = True
        return MESSAGE, parameters

    try:
        data_vencimento = datetime.strptime(api_response.get("DataVencimento"), "%d/%m/%Y").date()
        parameters["cota_unica"] = data_vencimento >= datetime.now().date()
    except (ValueError, TypeError):
        parameters["error_api_iptu"] = True
        return MESSAGE, parameters
    
    valor_total = sum(
        formatar_valor_cota(cota.get("valor", "0")) for cota in api_response.get("Cotas", [])
    )

    cotas_detalhes = gerar_detalhes(api_response)

    if parameters["cota_unica"]:
        message = await gerar_mensagem(parameters.get("inscricao"), cotas_detalhes, cotas, valor_total)
        parameters["msg_cota_unica"] = message

    return MESSAGE, parameters


async def get_download_darm_iptu(request_data: dict) -> Tuple[str, Dict[str, Any]]:
    parameters = request_data.get("sessionInfo", {}).get("parameters", {})
    inscricao = parameters.get("inscricao")
    exercicio = parameters.get("exercicio")
    guia = parameters.get("guia")
    cotas = convert_list_to_string(parameters.get("cotas"))

    if not all([inscricao, exercicio, guia, cotas]):
        parameters["error_api_iptu"] = True
        return MESSAGE, parameters

    api_response = await iptu_api(
        request_data=request_data,
        token=config.IPTU_API_TOKEN,
        endpoint="DownloadPdfDARM",
        inscricao=inscricao, 
        exercicio=exercicio,
        guia=guia,
        cotas=cotas
    )

    api_response_seq = await iptu_api(
        request_data=request_data,
        token=config.IPTU_API_TOKEN,
        endpoint="ConsultarDARM",
        inscricao=inscricao, 
        exercicio=exercicio,
        guia=guia,
        cotas=cotas
    )
        
    seq_numerica = api_response_seq.get("SequenciaNumerica", "Não disponível")

    try:
        download_link = await upload_base64_to_gcs(base64_content=api_response, folder_name="iptu")
        shorted_link = await get_short_url(download_link)
    except Exception as e:
        parameters["error_api_iptu"] = True
        return MESSAGE, parameters

    if parameters["cota_unica"] and parameters["forma_pagamento"] == "Em Cota Única com desconto":
        message = [
            f"*Link para download da sua DARM de IPTU para Cota Única:*",
            shorted_link,
            f"*Sequência numérica para Cota Única:*",
            seq_numerica
        ]
    else:
        message = [
            f"*Link para download da sua DARM de IPTU para a(s) cota(s) {cotas}:*",
            shorted_link,
            f"*Sequência numérica para a(s) cota(s) {cotas}:*",
            seq_numerica
        ]
    
    return message, parameters


async def get_download_todas_cotas_parceladas_iptu(request_data: dict) -> Tuple[str, Dict[str, Any]]:
    parameters = request_data.get("sessionInfo", {}).get("parameters", {})
    inscricao = parameters.get("inscricao")
    exercicio = parameters.get("exercicio")
    guia = parameters.get("guia")
    cotas = convert_list_to_string(parameters.get("cotas"))

    if not all([inscricao, exercicio, guia, cotas]):
        parameters["error_api_iptu"] = True
        return MESSAGE, parameters

    seq_numerica = await consultar_sequencia_cotas(request_data, cotas, inscricao, exercicio, guia)
    cota_list = [cota.strip() for cota in cotas.split(",")]
    message = []

    for cota in cota_list:
        try:
            api_response = await iptu_api(
                request_data=request_data,
                token=config.IPTU_API_TOKEN,
                endpoint="DownloadPdfDARM",
                inscricao=inscricao,
                exercicio=int(exercicio),
                guia=guia,
                cotas=cota,
            )

            download_link = await upload_base64_to_gcs(base64_content=api_response, folder_name="iptu")
            shorted_link = await get_short_url(download_link)
        except Exception as e:
            parameters["error_api_iptu"] = f"Falha ao processar a cota {cota.strip()}. {e}"
            continue

        message.append(f"*Link para download da sua DARM de IPTU para cota {cota}:*")
        message.append(shorted_link)
        message.append(f"*Sequência numérica para o pagamento da cota {cota}:*")
        message.append(seq_numerica[cota])

    if not message:
        message = "Não foi possível processar nenhuma DARM no momento. Por favor, confira os dados enviados."
        return message, parameters

    return message, parameters
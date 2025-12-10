"""
Workflow de Poda de Árvore

Implementa o fluxo de solicitação de poda com verificação de cadastro.
"""

from datetime import datetime
from typing import Any, Dict, Union
import time

from langgraph.graph import StateGraph, END
from loguru import logger

from src.tools.multi_step_service.core.base_workflow import BaseWorkflow, handle_errors
from src.tools.multi_step_service.core.models import ServiceState, AgentResponse
from src.tools.multi_step_service.workflows.poda_de_arvore.api.api_service import SGRCAPIService, AddressAPIService
from src.tools.multi_step_service.workflows.poda_de_arvore.models import (
    CPFPayload,
    EmailPayload,
    NomePayload,
    AddressPayload,
    AddressData,
    AddressValidationState,
    AddressConfirmationPayload,
    PontoReferenciaPayload,
)
from src.tools.multi_step_service.workflows.poda_de_arvore.templates import solicitar_cpf

from prefeitura_rio.integrations.sgrc.models import Address, NewTicket, Requester, Phones
from prefeitura_rio.integrations.sgrc.exceptions import (
    SGRCBusinessRuleException,
    SGRCInvalidBodyException,
    SGRCMalformedBodyException,
    SGRCDuplicateTicketException,
    SGRCEquivalentTicketException,
    SGRCInternalErrorException,
)
from prefeitura_rio.integrations.sgrc import async_new_ticket


class PodaDeArvoreWorkflow(BaseWorkflow):
    """
    Workflow de Poda de Árvore.
    
    Fluxo completo:
    1. Coleta CPF
    2. Coleta email
    2. Verifica cadastro na API
    3. Se cadastrado: recupera nome e pede confirmação
    4. Se não cadastrado: solicita nome
    5. Coleta endereço
    6. Confirmação do endereco
    7. Abre chamado na API do SGRC
    """
    
    service_name = "poda_de_arvore"
    description = "Solicitação de poda de árvore com verificação de cadastro."

    def __init__(self, use_fake_api: bool = False):
        super().__init__()
        self.use_fake_api = use_fake_api
        self.service_id = "1614"
    
        if not use_fake_api:
            self.api_service = SGRCAPIService()
            self.address_service = AddressAPIService()

    @handle_errors
    async def _collect_cpf(
        self, 
        state: ServiceState
    ) -> ServiceState:
        """Coleta CPF do usuário."""
        logger.info("[ENTRADA] _collect_cpf")
        logger.info(f"[STATE.DATA] Chaves presentes: {list(state.data.keys())}")
        logger.info(f"[STATE.PAYLOAD] Conteúdo: {state.payload}")
        
        # Se está aguardando confirmação de usar DADOS PESSOAIS da memória
        if state.data.get("awaiting_user_memory_confirmation"):
            # Se o payload tem confirmacao, processa
            if "confirmacao" in state.payload:
                try:
                    validated = AddressConfirmationPayload.model_validate(state.payload)
                    state.data.pop("awaiting_user_memory_confirmation", None)
                    
                    if validated.confirmacao:
                        logger.info("[MEMÓRIA] Usuário confirmou usar dados pessoais anteriores")
                        # Mantém os dados e marca como verificado
                        state.data["cadastro_verificado"] = True
                        state.agent_response = None
                        return state
                    else:
                        logger.info("[MEMÓRIA] Usuário recusou dados pessoais anteriores. Limpando...")
                        # Limpa apenas dados pessoais
                        keys_to_clear = ["cpf", "email", "name", "phone", "cadastro_verificado", 
                                       "identificacao_pulada", "cpf_attempts", "email_attempts", "name_attempts",
                                       "awaiting_user_memory_confirmation"]
                        for key in keys_to_clear:
                            state.data.pop(key, None)
                        # Solicita CPF imediatamente após limpar dados
                        state.agent_response = AgentResponse(
                            description=solicitar_cpf(),
                            payload_schema=CPFPayload.model_json_schema(),
                        )
                        return state
                    
                except Exception as e:
                    logger.error(f"Erro ao processar confirmação de dados pessoais: {e}")
                    # Em caso de erro, continua normalmente
            else:
                # Verifica se o usuário quer pular/avançar
                user_input = str(state.payload.get("email", "")).lower() if "email" in state.payload else ""
                if user_input == "" and "email" in state.payload:
                    # Usuário enviou email vazio - quer pular
                    logger.info("[MEMÓRIA] Usuário optou por pular dados pessoais (avançar)")
                    # Trata como recusa - limpa dados pessoais
                    state.data.pop("awaiting_user_memory_confirmation", None)
                    keys_to_clear = ["cpf", "email", "name", "phone", "cadastro_verificado"]
                    for key in keys_to_clear:
                        state.data.pop(key, None)
                    # Continua sem dados pessoais
                    state.agent_response = None
                    return state
                else:
                    # Usuário perguntou algo ao invés de confirmar - repete a pergunta
                    logger.info("[MEMÓRIA] Usuário não enviou confirmação - repetindo pergunta")
                    # Mantém awaiting_user_memory_confirmation=True para continuar aguardando
                    # A pergunta será refeita no bloco abaixo
        
        # Verifica se tem dados pessoais na memória para confirmar
        # MAS SÓ DEPOIS que o endereço já foi processado
        # OU se foi marcado que precisa confirmar (novo atendimento)
        # Ignora se o payload contém apenas ponto_referencia (vindo do passo anterior)
        payload_is_empty = not state.payload or (len(state.payload) == 1 and "ponto_referencia" in state.payload)
        
        # Se está aguardando confirmação OU precisa perguntar pela primeira vez
        # Também pergunta se tem CPF="skip" mas não tem dados pessoais reais
        should_ask_about_data = (
            (state.data.get("address_confirmed") or state.data.get("personal_data_needs_confirmation")) or
            (state.data.get("cpf") == "skip" and not state.data.get("name") and not state.data.get("email"))
        )
        
        if (((payload_is_empty and not state.data.get("awaiting_user_memory_confirmation")) or 
            (state.data.get("awaiting_user_memory_confirmation") and "confirmacao" not in state.payload)) and 
            should_ask_about_data):
            has_user_data = []
            
            if state.data.get("name"):
                # Mascara o nome - mostra apenas primeiro nome e inicial do último
                nome_parts = state.data["name"].split()
                if len(nome_parts) > 1:
                    nome_mask = f"{nome_parts[0]} {nome_parts[-1][0]}."
                else:
                    nome_mask = nome_parts[0]
                has_user_data.append(f"• Nome: {nome_mask}")
                
            if state.data.get("cpf") and state.data["cpf"] != "skip":
                cpf = state.data["cpf"]
                if len(cpf) == 11:
                    # Formato XXX.456.789-XX mostrando apenas o meio do CPF
                    cpf_mask = f"XXX.{cpf[3:6]}.{cpf[6:9]}-XX"
                else:
                    cpf_mask = "X" * 3 + cpf[3:] if len(cpf) > 3 else "XXX"
                has_user_data.append(f"• CPF: {cpf_mask}")
                
            if state.data.get("email"):
                # Mascara email
                email_parts = state.data["email"].split("@")
                if len(email_parts) == 2:
                    user_part = email_parts[0]
                    if len(user_part) > 2:
                        email_mask = f"{user_part[:2]}***@{email_parts[1]}"
                    else:
                        email_mask = f"{user_part}***@{email_parts[1]}"
                else:
                    email_mask = state.data["email"]
                has_user_data.append(f"• Email: {email_mask}")
            
            if has_user_data:
                dados_str = "\n".join(has_user_data)
                
                # Se já estava aguardando e usuário perguntou algo, adiciona mensagem de segurança e orientação
                if state.data.get("awaiting_user_memory_confirmation") and state.payload:
                    message = f"Por questões de segurança, não posso exibir dados sensíveis completos.\n\nVocê tem os seguintes dados salvos:\n\n{dados_str}\n\nPor favor, confirme se deseja usar esses dados ou se prefere fornecer novos dados."
                else:
                    message = f"Vi que você tem dados pessoais salvos:\n\n{dados_str}\n\nGostaria de usar esses dados?"
                
                state.data["awaiting_user_memory_confirmation"] = True
                # Remove flag de confirmação pendente
                state.data.pop("personal_data_needs_confirmation", None)
                
                state.agent_response = AgentResponse(
                    description=message,
                    payload_schema=AddressConfirmationPayload.model_json_schema()
                )
                return state
        
        # Se já verificou cadastro, pula
        if "cpf" in state.payload:
            try:
                validated_data = CPFPayload.model_validate(state.payload)
                cpf_novo = validated_data.cpf
                
                # TODO: Implementar lógica de reset quando CPF mudar
                # cpf_antigo = state.data.get("cpf")
                # if cpf_antigo != cpf_novo:
                #     # Limpar dados do cadastro anterior
                #     pass
                
                # Verifica se o usuário optou por pular a identificação
                if not cpf_novo:
                    state.data["cpf"] = "skip"  # Precisa marcar que já processou CPF
                    state.data["identificacao_pulada"] = True
                    logger.info("Usuário optou por não se identificar")
                    state.agent_response = None
                    return state
                
                state.data["cpf"] = cpf_novo
                logger.info(f"CPF coletado: {cpf_novo}")

                if not self.use_fake_api:
                    try:
                        user_info = await self.api_service.get_user_info(cpf_novo)
                        ## caso existam infos do usuário, verificar se tem e-mail e nome. caso alguma das infos esteja faltando, pedir apenas a info faltante
           
                        email_sgrc = str(user_info.get("email", "")).strip().lower() if user_info.get("email") else ""    
                        nome_sgrc = str(user_info.get("name", "")).strip() if user_info.get("name") else ""

                        if email_sgrc:
                            state.data["email"] = email_sgrc
                            state.payload["email"] = email_sgrc
                        if nome_sgrc:
                            state.data["name"] = nome_sgrc
                            state.payload["name"] = nome_sgrc
                        if "phones" in user_info and user_info["phones"]:
                            telefone_sgrc = str(user_info["phones"][0]).strip() if user_info["phones"][0] else ""
                            state.data["phone"] = telefone_sgrc
                            state.payload["phone"] = telefone_sgrc
                        
                        # Marca como verificado com sucesso
                        state.data["cadastro_verificado"] = True
                        logger.info(f"Cadastro encontrado para CPF XXX.{cpf_novo[3:6]}.{cpf_novo[6:9]}-XX" if len(cpf_novo) == 11 else f"Cadastro encontrado para CPF {cpf_novo[:3]}XXX")
                        
                    except AttributeError as e:
                        # Erro de estrutura de dados - API retornou formato inesperado
                        logger.error(f"Erro ao processar resposta da API de cadastro: {str(e)}")
                        state.data["cadastro_verificado"] = False
                        
                    except (ConnectionError, TimeoutError) as e:
                        # Erro de conexão - API indisponível
                        logger.error(f"API de cadastro indisponível: {str(e)}")
                        state.data["cadastro_verificado"] = False
                        state.data["api_indisponivel"] = True
                        
                    except Exception as e:
                        # Outros erros (ex: usuário não encontrado)
                        logger.info(f"Usuário não encontrado no cadastro ou erro na consulta: {str(e)}")
                        state.data["cadastro_verificado"] = False
                state.agent_response = None
                return state
            
            except Exception as e:
                # Incrementa contador de tentativas de CPF
                cpf_attempts = state.data.get("cpf_attempts", 0) + 1
                state.data["cpf_attempts"] = cpf_attempts
                
                if cpf_attempts >= 3:
                    # Excedeu tentativas - pula CPF
                    state.data["cpf"] = "skip"
                    state.data["identificacao_pulada"] = True
                    state.data["cpf_max_attempts_reached"] = True
                    logger.warning(f"CPF: máximo de tentativas ({cpf_attempts}) excedido. Pulando identificação.")
                    state.agent_response = AgentResponse(
                        description="Número máximo de tentativas excedido. Continuando sem identificação.",
                        error_message="Máximo de tentativas excedido"
                    )
                    return state  # Retorna para prosseguir sem CPF
                else:
                    state.agent_response = AgentResponse(
                        description=f"CPF inválido. Tentativa {cpf_attempts}/3. {solicitar_cpf()}",
                        payload_schema=CPFPayload.model_json_schema(),
                        error_message=f"CPF inválido: {str(e)}"
                    )
                # Não retorna aqui - continua para verificar se deve solicitar CPF novamente
                # ou terminar o fluxo

        # Se já tem CPF processado e não é um novo valor sendo enviado
        # MAS se CPF é "skip" e acabou de coletar ponto de referência, solicita CPF novamente
        if "cpf" in state.data and "cpf" not in state.payload:
            # Se CPF é "skip" e acabou de processar ponto de referência, pergunta CPF
            if (state.data.get("cpf") == "skip" and 
                state.data.get("reference_point_collected") and 
                "ponto_referencia" in state.payload):
                logger.info("CPF é 'skip' mas acabou de coletar ponto de referência - solicitando CPF")
                # Limpa o CPF skip para solicitar novamente
                state.data.pop("cpf", None)
                state.data.pop("identificacao_pulada", None)
            else:
                logger.info("CPF já existe em state.data, prosseguindo")
                return state

        # Se já temos uma resposta de erro (validação falhou), retorna com erro
        if state.agent_response and state.agent_response.error_message:
            return state

        # Se chegou aqui e não tem CPF, solicita
        if "cpf" not in state.data:
            state.agent_response = AgentResponse(
                description=solicitar_cpf(),
                payload_schema=CPFPayload.model_json_schema(),
            )

        return state
    

    @handle_errors
    async def _collect_email(self, state: ServiceState) -> ServiceState:
        """Coleta email do usuário (opcional)."""
        logger.info("[ENTRADA] _collect_email")
        logger.info(f"[STATE.DATA] Chaves presentes: {list(state.data.keys())}")
        logger.info(f"[STATE.PAYLOAD] Conteúdo: {state.payload}")
        
        # Se já processou email (coletado ou pulado), não pede novamente
        if state.data.get("email_processed"):
            return state
        
        if "email" in state.payload:
            # Se enviou vazio, marca como pulado
            if state.payload.get("email", "").strip() == "":
                state.data["email_skipped"] = True
                state.data["email_processed"] = True
                logger.info("Usuário optou por não informar email")
                state.agent_response = None
                return state
            
            # Se forneceu algo, valida
            try:
                validated_data = EmailPayload.model_validate(state.payload)
                email_novo = validated_data.email
                
                # TODO: Implementar lógica de reset quando email mudar
                # email_antigo = state.data.get("email")
                # if email_antigo != email_novo:
                #     # Avaliar se precisa atualizar algo
                #     pass
                
                state.data["email"] = email_novo
                state.data["email_processed"] = True
                logger.info(f"Email coletado: {email_novo}")
                state.agent_response = None
                return state
            
            except Exception as e:
                # Incrementa contador de tentativas de email
                email_attempts = state.data.get("email_attempts", 0) + 1
                state.data["email_attempts"] = email_attempts
                logger.info(f"[EMAIL] Tentativa {email_attempts}/3 - Erro: {str(e)}")
                
                if email_attempts >= 3:
                    # Excedeu tentativas - pula email
                    state.data["email_skipped"] = True
                    state.data["email_processed"] = True
                    state.data["email_max_attempts_reached"] = True
                    logger.warning(f"Email: máximo de tentativas ({email_attempts}) excedido. Pulando email.")
                    state.agent_response = AgentResponse(
                        description="Número máximo de tentativas excedido. Continuando sem email.",
                        error_message="Máximo de tentativas excedido"
                    )
                else:
                    state.agent_response = AgentResponse(
                        description=f"Email inválido. Tentativa {email_attempts}/3. Por favor, informe um email válido (ou deixe em branco para pular):",
                        payload_schema=EmailPayload.model_json_schema(),
                        error_message=f"Email inválido: {str(e)}"
                    )
                return state

        # Se já processou (tem email ou foi pulado), retorna
        if state.data.get("email_processed") and "email" not in state.payload:
            logger.info("Email já processado, prosseguindo")
            return state

        # Se já temos uma resposta de erro (validação falhou), retorna com erro
        if state.agent_response and state.agent_response.error_message:
            return state

        # Se chegou aqui e não processou email ainda, solicita
        if not state.data.get("email_processed"):
            state.agent_response = AgentResponse(
                description="Por favor, informe seu email (opcional - você pode deixar em branco para pular):",
                payload_schema=EmailPayload.model_json_schema(),
            )

        return state
    

    @handle_errors
    async def _collect_name(self, state: ServiceState) -> ServiceState:
        """Coleta nome do usuário (opcional)."""
        logger.info("[ENTRADA] _collect_name")
        logger.info(f"[STATE.DATA] Chaves presentes: {list(state.data.keys())}")
        logger.info(f"[STATE.PAYLOAD] Conteúdo: {state.payload}")
        
        # Se já processou nome (coletado ou pulado), não pede novamente
        if state.data.get("name_processed"):
            return state
        
        if "name" in state.payload:
            # Se enviou vazio, marca como pulado
            if state.payload.get("name", "").strip() == "":
                state.data["name_skipped"] = True
                state.data["name_processed"] = True
                logger.info("Usuário optou por não informar nome")
                state.agent_response = None
                return state
            
            # Se forneceu algo, valida
            try:
                validated_data = NomePayload.model_validate(state.payload)
                nome_novo = validated_data.name
                
                # TODO: Implementar lógica de reset quando nome mudar
                # nome_antigo = state.data.get("name")
                # if nome_antigo != nome_novo:
                #     # Avaliar se precisa atualizar algo
                #     pass
                
                state.data["name"] = nome_novo
                state.data["name_processed"] = True
                logger.info(f"Nome coletado: {nome_novo}")
                state.agent_response = None
                return state
            
            except Exception as e:
                # Incrementa contador de tentativas de nome
                name_attempts = state.data.get("name_attempts", 0) + 1
                state.data["name_attempts"] = name_attempts
                
                if name_attempts >= 3:
                    # Excedeu tentativas - pula nome
                    state.data["name_skipped"] = True
                    state.data["name_processed"] = True
                    state.data["name_max_attempts_reached"] = True
                    logger.warning(f"Nome: máximo de tentativas ({name_attempts}) excedido. Pulando nome.")
                    state.agent_response = AgentResponse(
                        description="Número máximo de tentativas excedido. Continuando sem nome.",
                        error_message="Máximo de tentativas excedido"
                    )
                else:
                    state.agent_response = AgentResponse(
                        description=f"Nome inválido. Tentativa {name_attempts}/3. Por favor, informe um nome válido com nome e sobrenome (ou deixe em branco para pular):",
                        payload_schema=NomePayload.model_json_schema(),
                        error_message=f"Nome inválido: {str(e)}"
                    )
                return state

        # Se já processou (tem nome ou foi pulado), retorna
        if state.data.get("name_processed") and "name" not in state.payload:
            logger.info("Nome já processado, prosseguindo")
            return state

        # Se já temos uma resposta de erro (validação falhou), retorna com erro
        if state.agent_response and state.agent_response.error_message:
            return state

        # Se chegou aqui e não processou nome ainda, solicita
        if not state.data.get("name_processed"):
            state.agent_response = AgentResponse(
                description="Por favor, informe seu nome completo (opcional - você pode deixar em branco para pular):",
                payload_schema=NomePayload.model_json_schema(),
            )

        return state

    
    @handle_errors
    async def _collect_address(self, state: ServiceState) -> ServiceState:
        """Coleta endereço do usuário para a solicitação."""
        logger.info("[ENTRADA] _collect_address")
        logger.info(f"[STATE.DATA] Chaves presentes: {list(state.data.keys())}")
        logger.info(f"[STATE.PAYLOAD] Conteúdo: {state.payload}")
        
        # IMPORTANTE: PRIMEIRO detecta se é novo atendimento (antes de qualquer return!)
        # Se é primeira execução (payload vazio) e tem qualquer dado anterior
        if not state.payload and not state.data.get("restarting_after_error"):
            # Se tem QUALQUER dado anterior (endereço, CPF, nome, etc)
            if state.data and len(state.data) > 0:
                # Se já finalizou um atendimento anterior OU tem confirmações antigas
                # (awaiting_user_memory_confirmation indica sessão anterior não finalizada)
                if (state.data.get("ticket_created") or state.data.get("error") or 
                    state.data.get("awaiting_user_memory_confirmation") or
                    state.data.get("awaiting_address_memory_confirmation")):
                    logger.info("[NOVO ATENDIMENTO] Detectado início de nova solicitação após atendimento anterior")
                    
                    # Reseta TODOS os flags de confirmação - nova sessão, novas confirmações!
                    state.data.pop("ticket_created", None)
                    state.data.pop("error", None)
                    state.data.pop("address_confirmed", None)
                    state.data.pop("address_validated", None)
                    state.data.pop("awaiting_address_memory_confirmation", None)
                    state.data.pop("awaiting_user_memory_confirmation", None)
                    state.data.pop("reference_point_collected", None)
                    state.data.pop("need_reference_point", None)
                    state.data.pop("ponto_referencia", None)
                    state.data.pop("cadastro_verificado", None)
                    state.data.pop("address_needs_confirmation", None)
                    state.data.pop("address_validation", None)  # IMPORTANTE: reseta contador de tentativas
                    state.data.pop("address_max_attempts_reached", None)  # IMPORTANTE: reseta flag de tentativas
                    
                    # Se tem endereço ou dados pessoais, marca para confirmar
                    if state.data.get("address") or state.data.get("address_temp"):
                        # Tem endereço salvo, marca para confirmar dados pessoais depois
                        if state.data.get("cpf") or state.data.get("email") or state.data.get("name"):
                            state.data["personal_data_needs_confirmation"] = True
                        # Continua para perguntar sobre endereço
                    elif state.data.get("cpf") or state.data.get("email") or state.data.get("name"):
                        # Tem só dados pessoais, marca para confirmar depois do endereço
                        state.data["personal_data_needs_confirmation"] = True
        
        # Se já coletou endereço validado e confirmado, pula
        # MAS não pula se houver erro/ticket (novo atendimento) ou confirmações pendentes
        # TAMBÉM não pula se é o primeiro payload vazio (novo atendimento)
        if (state.data.get("address_validated") and state.data.get("address_confirmed") 
            and not state.data.get("ticket_created") and not state.data.get("error")
            and not state.data.get("awaiting_user_memory_confirmation")
            and not state.data.get("awaiting_address_memory_confirmation")
            and state.payload):  # Se tem payload, não é novo atendimento
            return state
        
        # Se endereço está aguardando confirmação, não processa novamente
        if state.data.get("address_needs_confirmation"):
            return state
        
        # Se está aguardando confirmação de dados PESSOAIS, não processa aqui
        # (será processado em _collect_cpf)
        if state.data.get("awaiting_user_memory_confirmation"):
            return state
        
        # Se está aguardando confirmação de usar ENDEREÇO da memória
        if state.data.get("awaiting_address_memory_confirmation") and "confirmacao" in state.payload:
            try:
                validated = AddressConfirmationPayload.model_validate(state.payload)
                state.data.pop("awaiting_address_memory_confirmation", None)
                
                if validated.confirmacao:
                    logger.info("[MEMÓRIA] Usuário confirmou usar endereço anterior")
                    # Marca endereço como confirmado
                    if state.data.get("address"):
                        state.data["address_confirmed"] = True
                        state.data["address_validated"] = True
                        state.data["need_reference_point"] = True  # Precisa pedir ponto de referência
                    elif state.data.get("address_temp"):
                        # Move address_temp para address
                        state.data["address"] = state.data["address_temp"]
                        state.data["address_confirmed"] = True
                        state.data["address_validated"] = True
                        state.data["need_reference_point"] = True  # Precisa pedir ponto de referência
                        state.data.pop("address_temp", None)
                else:
                    logger.info("[MEMÓRIA] Usuário recusou endereço anterior. Limpando endereço...")
                    # Limpa apenas dados de endereço
                    keys_to_clear = ["address", "address_temp", "address_validated", "address_confirmed",
                                   "address_needs_confirmation", "address_validation", "last_address_text"]
                    for key in keys_to_clear:
                        state.data.pop(key, None)
                    
                # Remove agent_response para continuar fluxo
                state.agent_response = None
                return state
                
            except Exception as e:
                logger.error(f"Erro ao processar confirmação de endereço da memória: {e}")
                # Em caso de erro, limpa endereço e começa novo
                keys_to_clear = ["address", "address_temp", "address_validated", "address_confirmed",
                               "address_needs_confirmation", "address_validation", "last_address_text"]
                for key in keys_to_clear:
                    state.data.pop(key, None)
        
        # Se tem endereço anterior (após processar novo atendimento), confirma ENDEREÇO
        # MAS só se não está aguardando outra confirmação
        if (not state.payload and (state.data.get("address") or state.data.get("address_temp"))
            and not state.data.get("awaiting_user_memory_confirmation")
            and not state.data.get("awaiting_address_memory_confirmation")):
                    logger.info("[MEMÓRIA] Detectado endereço de atendimento anterior")
                    
                    # Pega o endereço disponível
                    addr = state.data.get("address") or state.data.get("address_temp")
                    
                    # Formata endereço
                    endereco_parts = []
                    if addr.get('logradouro_nome_ipp'):
                        endereco_parts.append(f"• Logradouro: {addr['logradouro_nome_ipp']}")
                    elif addr.get('logradouro'):
                        endereco_parts.append(f"• Logradouro: {addr['logradouro']}")
                    
                    if addr.get('numero'):
                        endereco_parts.append(f"• Número: {addr['numero']}")
                    
                    if addr.get('bairro_nome_ipp'):
                        endereco_parts.append(f"• Bairro: {addr['bairro_nome_ipp']}")
                    elif addr.get('bairro'):
                        endereco_parts.append(f"• Bairro: {addr['bairro']}")
                    
                    endereco_parts.append(f"• Cidade: {addr.get('cidade', 'Rio de Janeiro')}, {addr.get('estado', 'RJ')}")
                    
                    endereco_str = "\n".join(endereco_parts)
                    
                    # Marca que está aguardando confirmação do endereço da memória
                    state.data["awaiting_address_memory_confirmation"] = True
                    
                    state.agent_response = AgentResponse(
                        description=f"Vi que você tem um endereço registrado no histórico. Gostaria de solicitar a poda de árvore para o endereço abaixo?\n\n{endereco_str}\n\nEste endereço está correto?",
                        payload_schema=AddressConfirmationPayload.model_json_schema()
                    )
                    return state
        
        # Se está recomeçando após erro de ticket
        if state.data.get("restarting_after_error"):
            state.data.pop("restarting_after_error", None)
            # Usa a mensagem de erro original, se disponível
            error_msg = state.data.pop("error_message", "Não foi possível criar o ticket.")
            # Mostra mensagem informando que está recomeçando
            state.agent_response = AgentResponse(
                description=f"❌ {error_msg}\n\nVamos tentar novamente.\n\n📍 Por favor, informe novamente o endereço completo onde está a árvore que necessita poda:",
                payload_schema=AddressPayload.model_json_schema()
            )
            return state
        
        # Se já coletou endereço validado e confirmado, pula
        # MAS não pula se houver erro/ticket (novo atendimento) ou confirmações pendentes
        # TAMBÉM não pula se é o primeiro payload vazio (novo atendimento)
        if (state.data.get("address_validated") and state.data.get("address_confirmed") 
            and not state.data.get("ticket_created") and not state.data.get("error")
            and not state.data.get("awaiting_user_memory_confirmation")
            and not state.data.get("awaiting_address_memory_confirmation")
            and state.payload):  # Se tem payload, não é novo atendimento
            return state
            
        # Inicializa estado de validação se não existe
        if "address_validation" not in state.data:
            state.data["address_validation"] = AddressValidationState().model_dump()
        
        validation_state = AddressValidationState(**state.data["address_validation"])
        
        # Se tem endereço no payload, processa
        if "address" in state.payload:
            try:
                validated_data = AddressPayload.model_validate(state.payload)
                address_text = validated_data.address.strip()
                
                if not address_text:
                    raise ValueError("Endereço não pode estar vazio")
                
                # Sempre incrementa o contador (tentativas são globais)
                validation_state.attempts += 1
                state.data["last_address_text"] = address_text
                
                # Verifica se excedeu tentativas
                if validation_state.attempts >= validation_state.max_attempts:
                    state.agent_response = AgentResponse(
                        description="Não foi possível validar o endereço após 3 tentativas. Por favor, tente novamente mais tarde ou entre em contato pelo telefone 1746. Seu atendimento está finalizado.",
                        error_message="Máximo de tentativas excedido"
                    )
                    state.data["address_validation"] = validation_state.model_dump()
                    state.data["address_max_attempts_reached"] = True  # Marca que atingiu o limite
                    return state
                
                # Adiciona cidade e estado se não estiverem no endereço
                address_to_google = f"{address_text}, Rio de Janeiro - RJ"
                
                if self.use_fake_api:
                    # Simula validação bem-sucedida
                    address_info = {
                        "valid": True,
                        "logradouro": "Rua Teste",
                        "numero": "123",
                        "bairro": "Centro",
                        "cidade": "Rio de Janeiro",
                        "estado": "RJ",
                        "latitude": -22.9068,
                        "longitude": -43.1729
                    }
                else:
                    # Valida endereço com Google
                    address_info = await self.address_service.google_geolocator(address_to_google)
                
                if not address_info.get("valid"):
                    error_msg = address_info.get("error", "Endereço não encontrado ou inválido")
                    validation_state.last_error = error_msg
                    state.data["address_validation"] = validation_state.model_dump()
                    
                    # Mensagem personalizada baseada no erro
                    if "fora do município" in error_msg.lower():
                        description = "O endereço informado está fora do município do Rio de Janeiro. Por favor, informe um endereço dentro do município."
                    else:
                        description = f"Não consegui localizar o endereço informado. Por favor, verifique e informe novamente (tentativa {validation_state.attempts}/{validation_state.max_attempts})."
                    
                    state.agent_response = AgentResponse(
                        description=description,
                        payload_schema=AddressPayload.model_json_schema(),
                        error_message=error_msg
                    )
                    return state
                
                # Obtém informações do IPP
                if not self.use_fake_api and address_info.get("latitude") and address_info.get("longitude"):
                    ipp_info = await self.address_service.get_endereco_info(
                        latitude=address_info["latitude"],
                        longitude=address_info["longitude"],
                        logradouro_google=address_info.get("logradouro"),
                        bairro_google=address_info.get("bairro")
                    )
                    
                    # Mescla informações do IPP se disponíveis
                    if ipp_info and not ipp_info.get("error"):
                        address_info.update(ipp_info)
                    
                    # Valida se conseguiu identificar códigos IPP necessários
                    if not address_info.get("logradouro_id") or address_info.get("bairro_id") in [None, "0", ""]:
                        logger.warning("Não foi possível identificar códigos IPP válidos")
                        validation_state.last_error = "Não foi possível identificar o endereço na base de dados da Prefeitura"
                        state.data["address_validation"] = validation_state.model_dump()
                        
                        # Verifica tentativas
                        if validation_state.attempts >= validation_state.max_attempts:
                            state.agent_response = AgentResponse(
                                description="Não foi possível validar o endereço após 3 tentativas. Por favor, tente novamente mais tarde ou entre em contato pelo telefone 1746. Seu atendimento está finalizado.",
                                error_message="Máximo de tentativas excedido"
                            )
                            state.data["address_max_attempts_reached"] = True
                        else:
                            state.agent_response = AgentResponse(
                                description=f"Não consegui identificar este endereço na base de dados da Prefeitura. Por favor, verifique o endereço e tente novamente com mais detalhes (tentativa {validation_state.attempts}/{validation_state.max_attempts}).",
                                payload_schema=AddressPayload.model_json_schema(),
                                error_message="Endereço não identificado na base IPP"
                            )
                        return state
                
                # Formata número se necessário
                numero_formatado = str(address_info.get("numero", "")).split(".")[0] if address_info.get("numero") else ""
                
                # Cria objeto AddressData
                address_data = AddressData(
                    logradouro=address_info.get("logradouro", ""),
                    numero=numero_formatado,
                    bairro=address_info.get("bairro", ""),
                    cep=address_info.get("cep"),
                    cidade=address_info.get("cidade", "Rio de Janeiro"),
                    estado=address_info.get("estado", "RJ"),
                    latitude=address_info.get("latitude"),
                    longitude=address_info.get("longitude"),
                    logradouro_id_ipp=address_info.get("logradouro_id"),
                    logradouro_nome_ipp=address_info.get("logradouro_nome"),
                    bairro_id_ipp=address_info.get("bairro_id"),
                    bairro_nome_ipp=address_info.get("bairro_nome"),
                    formatted_address=address_info.get("formatted_address", address_text),
                    original_text=address_text
                )
                
                # Armazena dados do endereço temporáriamente para confirmação
                state.data["address_temp"] = address_data.model_dump()
                state.data["address_needs_confirmation"] = True
                validation_state.validated = True
                state.data["address_validation"] = validation_state.model_dump()
                
                logger.info(f"Endereço identificado: {address_text}")
                state.agent_response = None  # Não envia resposta, vai para confirmação
                return state
                
            except Exception as e:
                logger.error(f"Erro ao processar endereço: {e}")
                validation_state.last_error = str(e)
                # Não incrementa aqui pois já foi incrementado acima
                state.data["address_validation"] = validation_state.model_dump()
                
                # Verifica se ainda tem tentativas
                if validation_state.attempts >= validation_state.max_attempts:
                    state.agent_response = AgentResponse(
                        description="Não foi possível validar o endereço após 3 tentativas. Por favor, tente novamente mais tarde ou entre em contato pelo telefone 1746. Seu atendimento está finalizado.",
                        error_message="Máximo de tentativas excedido"
                    )
                    state.data["address_max_attempts_reached"] = True
                else:
                    state.agent_response = AgentResponse(
                        description=f"Ocorreu um erro ao processar o endereço. Por favor, tente novamente (tentativa {validation_state.attempts}/{validation_state.max_attempts}).",
                        payload_schema=AddressPayload.model_json_schema(),
                        error_message=f"Erro: {str(e)}"
                    )
                return state
        
        # Solicita endereço pela primeira vez
        state.agent_response = AgentResponse(
            description="""Informe o endereço para atendimento contendo o seguinte:

• Nome da rua, avenida, praça, estrada etc
• Número mais próximo, sempre que possível
• Bairro

Exemplo:
Rua Afonso Cavalcanti, 455, Cidade Nova""",
            payload_schema=AddressPayload.model_json_schema()
        )
        
        return state

    
    async def new_ticket(
        self,
        classification_code: str,
        description: str = "",
        address: Address = None,
        date_time: Union[datetime, str] = None,
        requester: Requester = None,
        occurrence_origin_code: str = "28",
        specific_attributes: Dict[str, Any] = {},
    ):
        """Cria um novo ticket no SGRC."""
        start_time = time.time()
        end_time = None
        try:
            new_ticket_response: NewTicket = await async_new_ticket(
                classification_code=classification_code,
                description=description,
                address=address,
                date_time=date_time,
                requester=requester,
                occurrence_origin_code=occurrence_origin_code,
                specific_attributes=specific_attributes,
            )
            end_time = time.time()
            logger.info(f"Ticket criado com sucesso. Protocol ID: {new_ticket_response.protocol_id}. Tempo: {end_time - start_time:.2f}s")
            return new_ticket_response
        except Exception as exc:
            end_time = end_time if end_time else time.time()
            logger.error(f"Erro ao criar ticket. Tempo: {end_time - start_time:.2f}s. Erro: {exc}")
            raise exc


    @handle_errors
    async def _open_ticket(self, state: ServiceState) -> ServiceState:
        """Abre um ticket no SGRC com os dados coletados."""
        logger.info("[ENTRADA] _open_ticket")
        logger.info(f"[STATE.DATA] Chaves presentes: {list(state.data.keys())}")
        logger.info(f"[STATE.DATA] Endereço: {state.data.get('address')}")
        logger.info(f"[STATE.DATA] CPF: {state.data.get('cpf')}")
        logger.info(f"[STATE.DATA] Email: {state.data.get('email')}")
        logger.info(f"[STATE.DATA] Nome: {state.data.get('name')}")
        
        # Se estiver usando API fake, simula criação de ticket
        if self.use_fake_api:
            state.data["protocol_id"] = f"FAKE-{int(time.time())}"
            state.data["ticket_created"] = True
            logger.info(f"Ticket fake criado: {state.data['protocol_id']}")
            state.agent_response = AgentResponse(
                description=f"Sua solicitação foi criada com sucesso. O número do protocolo é {state.data['protocol_id']}. Você pode acompanhar sua solicitação informando o protocolo em https://www.1746.rio/hc/pt-br/p/solicitacoes."
            )
            return state
        
        try:
            # Prepara o objeto Phones
            phones_obj = Phones()
            if state.data.get("phone"):
                phones_obj.telefone1 = state.data.get("phone")
            
            requester = Requester(
                email=state.data.get("email", ""),
                cpf=state.data.get("cpf", ""),
                name=state.data.get("name", ""),
                phones=phones_obj,
            )
            
            # Cria objeto Address com os dados coletados
            address_data = state.data.get("address", {})
            
            # Extraí apenas dígitos do número
            street_number = address_data.get("numero", "1") or "1"
            street_number = "".join(filter(str.isdigit, str(street_number)))
            if not street_number:
                street_number = "1"  # Default se não houver número
            
            # Ponto de referência - pode vir de state.data ou do address_data
            ponto_ref = state.data.get("ponto_referencia", "") or address_data.get("ponto_referencia", "")
            
            # Cria objeto Address com os parâmetros corretos do SGRC
            address = Address(
                street=address_data.get("logradouro_nome_ipp", address_data.get("logradouro", "")),
                street_code=address_data.get("logradouro_id_ipp", ""),
                neighborhood=address_data.get("bairro_nome_ipp", address_data.get("bairro", "")),
                neighborhood_code=address_data.get("bairro_id_ipp", ""),
                number=street_number,
                locality=ponto_ref,
                zip_code=address_data.get("cep", "")
            )
            
            # Descrição do chamado
            # Monta endereço formatado para a descrição
            logradouro = address_data.get("logradouro_nome_ipp", address_data.get("logradouro", ""))
            numero = address_data.get("numero", "")
            bairro = address_data.get("bairro_nome_ipp", address_data.get("bairro", ""))
            
            endereco_formatado = f"{logradouro}"
            if numero:
                endereco_formatado += f", {numero}"
            if bairro:
                endereco_formatado += f", {bairro}"
            
            description = f"Solicitação de poda de árvore.\nEndereço: {endereco_formatado}"
            
            if ponto_ref:
                description += f"\nPonto de referência: {ponto_ref}"
            
            ticket = await self.new_ticket(
                classification_code=self.service_id,
                description=description,
                address=address,
                requester=requester,
            )
            
            state.data["protocol_id"] = ticket.protocol_id
            state.data["ticket_created"] = True
            state.agent_response = AgentResponse(
                description=f"Sua solicitação foi criada com sucesso. O número do protocolo é {ticket.protocol_id}.\n\nVocê pode acompanhar sua solicitação informando o protocolo em https://www.1746.rio/hc/pt-br/p/solicitacoes"
            )
            return state
        except (SGRCBusinessRuleException, SGRCInvalidBodyException, SGRCMalformedBodyException, ValueError) as exc:
            logger.exception(exc)
            state.data["ticket_created"] = False
            state.data["error"] = "erro_interno"
            state.agent_response = AgentResponse(
                description="Infelizmente houve um erro e a solicitação não pôde ser criada.\n\nPor favor, tente novamente em alguns minutos ou entre em contato pelo telefone 1746.",
                error_message="Erro ao criar solicitação"
            )
            return state
        except (SGRCDuplicateTicketException, SGRCEquivalentTicketException) as exc:
            logger.exception(exc)
            state.data["ticket_created"] = False
            state.data["error"] = "erro_ticket_duplicado"
            # Extrair o protocolo do erro se disponível
            protocol = getattr(exc, 'protocol_id', 'seu protocolo')
            state.agent_response = AgentResponse(
                description=f"A solicitação {protocol} já existe.\n\nVocê pode acompanhar sua solicitação informando o protocolo em https://www.1746.rio/hc/pt-br/p/solicitacoes"
            )
            return state
        except SGRCInternalErrorException as exc:
            logger.exception(exc)
            state.data["ticket_created"] = False
            state.data["error"] = "erro_sgrc"
            state.agent_response = AgentResponse(
                description="O sistema está indisponível no momento.\n\nPor favor, tente novamente em alguns minutos.",
                error_message="Sistema indisponível"
            )
            return state
        except Exception as exc:
            logger.exception(exc)
            state.data["ticket_created"] = False
            state.data["error"] = "erro_geral"
            state.agent_response = AgentResponse(
                description="Houve um erro ao abrir o chamado.\n\nPor favor, tente novamente mais tarde ou entre em contato pelo telefone 1746.",
                error_message=f"Erro: {str(exc)}"
            )
            return state


    # --- Roteamento Condicional ---
    
    def _route_after_cpf(self, state: ServiceState) -> str:
        logger.info("[ROTEAMENTO] _route_after_cpf")
        logger.info(f"[STATE.DATA] cpf: {state.data.get('cpf')}")
        logger.info(f"[STATE.DATA] cadastro_verificado: {state.data.get('cadastro_verificado')}")
        logger.info(f"[STATE.DATA] cpf_max_attempts_reached: {state.data.get('cpf_max_attempts_reached')}")
        
        # Se excedeu tentativas máximas, continua sem CPF
        if state.data.get("cpf_max_attempts_reached"):
            # Remove agent_response para não terminar o fluxo
            state.agent_response = None
            return "collect_email"  # Vai para email
        
        # Se há agent_response (erro) mas NÃO tem CPF ainda, termina para aguardar novo input
        if state.agent_response and "cpf" not in state.data:
            return END  # Termina e aguarda novo input do usuário
            
        # Se está aguardando confirmação de dados pessoais, termina para aguardar resposta
        if state.data.get("awaiting_user_memory_confirmation"):
            return END  # Aguarda confirmação do usuário
            
        # Se há qualquer agent_response E já tem CPF (mas não é confirmação), termina o fluxo
        if state.agent_response and "cpf" in state.data:
            return END
            
        if "cpf" in state.data:
            # Se o usuário pulou a identificação, vai direto para abrir ticket
            if state.data.get("identificacao_pulada"):
                return "open_ticket"
            
            if state.data.get("cadastro_verificado"):
                # Se já tem email e nome do cadastro, vai para abrir ticket
                if state.data.get("email") and state.data.get("name"):
                    return "open_ticket"
                # Se falta email, coleta (opcional)
                elif not state.data.get("email"):
                    return "collect_email"
                # Se falta nome, coleta (opcional)
                elif not state.data.get("name"):
                    return "collect_name"
                else:
                    return "open_ticket"
            else:
                # CPF não encontrado - solicita email (opcional)
                return "collect_email"
        # Se chegou aqui sem processar, aguarda input
        return END
    
    def _route_after_email(self, state: ServiceState) -> str:
        logger.info("[ROTEAMENTO] _route_after_email")
        logger.info(f"[STATE.DATA] email_processed: {state.data.get('email_processed')}")
        logger.info(f"[STATE.DATA] email_max_attempts_reached: {state.data.get('email_max_attempts_reached')}")
        
        # Se excedeu tentativas máximas, continua sem email
        if state.data.get("email_max_attempts_reached"):
            # Remove agent_response para não terminar o fluxo
            state.agent_response = None
            # Vai para próxima etapa
            if state.data.get("cadastro_verificado"):
                if state.data.get("name") or state.data.get("name_processed"):
                    return "open_ticket"
                else:
                    return "collect_name"
            else:
                return "collect_name"
        
        # Se há agent_response (erro) mas NÃO processou email, termina para aguardar novo input
        if state.agent_response and not state.data.get("email_processed"):
            return END  # Termina e aguarda novo input do usuário
            
        # Se há qualquer agent_response E já processou, termina o fluxo
        if state.agent_response and state.data.get("email_processed"):
            return END
            
        # Se já processou email (informou ou pulou)
        if state.data.get("email_processed"):
            if state.data.get("cadastro_verificado"):
                # Se já tem nome do cadastro, vai para abrir ticket
                if state.data.get("name") or state.data.get("name_processed"):
                    return "open_ticket"
                else:
                    return "collect_name"
            else:
                # Não está cadastrado, pede nome (opcional)
                if state.data.get("name_processed"):
                    return "open_ticket"
                else:
                    return "collect_name"
        # Se chegou aqui sem processar, aguarda input
        return END
    
    def _route_after_name(self, state: ServiceState) -> str:
        logger.info("[ROTEAMENTO] _route_after_name")
        logger.info(f"[STATE.DATA] name_processed: {state.data.get('name_processed')}")
        logger.info(f"[STATE.DATA] name_max_attempts_reached: {state.data.get('name_max_attempts_reached')}")
        
        # Se excedeu tentativas máximas, continua sem nome
        if state.data.get("name_max_attempts_reached"):
            # Remove agent_response para não terminar o fluxo
            state.agent_response = None
            return "open_ticket"  # Vai para abrir ticket
        
        # Se há agent_response (erro) mas NÃO processou nome ainda, termina para aguardar novo input
        if state.agent_response and not state.data.get("name_processed"):
            return END  # Termina e aguarda novo input do usuário
            
        # Se há qualquer agent_response E já processou, termina o fluxo
        if state.agent_response and state.data.get("name_processed"):
            return END
            
        # Se já processou nome (informou ou pulou), vai para abrir ticket
        if state.data.get("name_processed"):
            return "open_ticket"
        
        # Se chegou aqui sem processar, aguarda input
        return END
    
    @handle_errors
    async def _confirm_address(self, state: ServiceState) -> ServiceState:
        """Confirma o endereço identificado com o usuário."""
        logger.info("[ENTRADA] _confirm_address")
        logger.info(f"[STATE.DATA] address_needs_confirmation: {state.data.get('address_needs_confirmation')}")
        logger.info(f"[STATE.DATA] address_confirmed: {state.data.get('address_confirmed')}")
        logger.info(f"[STATE.PAYLOAD] Conteúdo: {state.payload}")
        
        # Se já confirmou, pula
        if state.data.get("address_confirmed"):
            return state
        
        # Se não precisa confirmar, pula
        if not state.data.get("address_needs_confirmation"):
            logger.warning("_confirm_address chamado mas não há endereço para confirmar")
            return state
        
        # Se tem resposta de confirmação no payload
        if "confirmacao" in state.payload:
            try:
                validated_data = AddressConfirmationPayload.model_validate(state.payload)
                
                if validated_data.confirmacao:
                    # Confirma e move dados temporários para definitivos
                    state.data["address"] = state.data["address_temp"]
                    state.data["address_confirmed"] = True
                    state.data["address_validated"] = True
                    state.data["address_needs_confirmation"] = False
                    state.data["need_reference_point"] = True  # Marca que precisa pedir ponto de referência
                    logger.info("Endereço confirmado pelo usuário")
                    state.agent_response = None
                    return state
                else:
                    # Usuário não confirmou, reseta para coletar novo endereço
                    state.data["address_needs_confirmation"] = False
                    state.data["address_temp"] = None
                    state.data["address_validated"] = False  # Importante: marca como não validado para voltar a coletar
                    logger.info("Endereço não confirmado, solicitando novo endereço")
                    
                    # NÃO incrementa contador aqui - já foi incrementado em _collect_address
                    validation_state = AddressValidationState(**state.data.get("address_validation", {}))
                    
                    # Verifica se ainda tem tentativas
                    if validation_state.attempts >= validation_state.max_attempts:
                        state.agent_response = AgentResponse(
                            description="Não foi possível validar o endereço após 3 tentativas. Por favor, tente novamente mais tarde ou entre em contato pelo telefone 1746. Seu atendimento está finalizado.",
                            error_message="Máximo de tentativas excedido"
                        )
                        state.data["address_max_attempts_reached"] = True
                    else:
                        state.agent_response = AgentResponse(
                            description=f"Por favor, informe novamente o endereço correto (tentativa {validation_state.attempts}/{validation_state.max_attempts}):",
                            payload_schema=AddressPayload.model_json_schema()
                        )
                    return state
            
            except Exception as e:
                state.agent_response = AgentResponse(
                    description="Por favor, confirme se o endereço está correto respondendo com 'sim' ou 'não'.",
                    payload_schema=AddressConfirmationPayload.model_json_schema(),
                    error_message=f"Resposta inválida: {str(e)}"
                )
                return state
        
        # Se chegou aqui, precisa montar mensagem de confirmação pela primeira vez
        if state.data.get("address_temp"):
            address_temp = state.data.get("address_temp", {})
            
            # Formata as partes do endereço
            confirmacao_parts = []
            
            if address_temp.get("logradouro_nome_ipp"):
                confirmacao_parts.append(f"• Logradouro: {address_temp['logradouro_nome_ipp']}")
            elif address_temp.get("logradouro"):
                confirmacao_parts.append(f"• Logradouro: {address_temp['logradouro']}")
            
            if address_temp.get("numero"):
                confirmacao_parts.append(f"• Número: {address_temp['numero']}")
            
            if address_temp.get("bairro_nome_ipp"):
                confirmacao_parts.append(f"• Bairro: {address_temp['bairro_nome_ipp']}")
            elif address_temp.get("bairro"):
                confirmacao_parts.append(f"• Bairro: {address_temp['bairro']}")
            
            confirmacao_parts.append(f"• Cidade: {address_temp.get('cidade', 'Rio de Janeiro')}, {address_temp.get('estado', 'RJ')}")
            
            mensagem_confirmacao = "\n".join(confirmacao_parts)
            
            # Verifica se está retomando uma conversa anterior (tem dados mas payload vazio)
            if not state.payload and state.data.get("address_temp"):
                # Mensagem mais contextual para retomada
                state.agent_response = AgentResponse(
                    description=f"Vi que você tem um endereço registrado no histórico. Gostaria de solicitar a poda de árvore para o endereço abaixo?\n\n{mensagem_confirmacao}\n\nEste endereço está correto?",
                    payload_schema=AddressConfirmationPayload.model_json_schema()
                )
            else:
                # Mensagem padrão para primeira confirmação
                state.agent_response = AgentResponse(
                    description=f"Por favor, confirme se o endereço está correto:\n\n{mensagem_confirmacao}\n\nO endereço está correto?",
                    payload_schema=AddressConfirmationPayload.model_json_schema()
                )
        
        return state
    
    def _route_after_address(self, state: ServiceState) -> str:
        logger.info("[ROTEAMENTO] _route_after_address")
        logger.info(f"[STATE.DATA] address_max_attempts_reached: {state.data.get('address_max_attempts_reached')}")
        logger.info(f"[STATE.DATA] address_needs_confirmation: {state.data.get('address_needs_confirmation')}")
        logger.info(f"[STATE.DATA] address_confirmed: {state.data.get('address_confirmed')}")
        logger.info(f"[STATE.DATA] address_validated: {state.data.get('address_validated')}")
        logger.info(f"[STATE] agent_response: {state.agent_response}")
        
        # Se há qualquer agent_response (erro ou solicitação), termina o fluxo
        # EXCETO se o endereço já foi validado e confirmado (pode continuar o fluxo)
        if state.agent_response:
            # Se tem endereço confirmado, não termina aqui
            if not (state.data.get("address_validated") and state.data.get("address_confirmed")):
                return END
        
        # Se endereço foi validado mas precisa confirmação, vai para confirmar
        if state.data.get("address_needs_confirmation"):
            return "confirm_address"
            
        # Se endereço foi validado e confirmado, prossegue para ponto de referência
        if state.data.get("address_validated") and state.data.get("address_confirmed"):
            return "collect_reference_point"
            
        # Continua coletando endereço
        return "collect_address"
    
    @handle_errors
    async def _collect_reference_point(self, state: ServiceState) -> ServiceState:
        """Coleta ponto de referência opcional."""
        logger.info("[ENTRADA] _collect_reference_point")
        logger.info(f"[STATE.DATA] Chaves presentes: {list(state.data.keys())}")
        logger.info(f"[STATE.PAYLOAD] Conteúdo: {state.payload}")
        
        # Se já coletou ou não precisa coletar
        if state.data.get("reference_point_collected") or not state.data.get("need_reference_point"):
            return state
        
        # Se tem resposta no payload
        if "ponto_referencia" in state.payload:
            try:
                validated_data = PontoReferenciaPayload.model_validate(state.payload)
                
                # Se informou ponto de referência
                if validated_data.ponto_referencia:
                    state.data["ponto_referencia"] = validated_data.ponto_referencia
                    logger.info(f"Ponto de referência coletado: {validated_data.ponto_referencia}")
                else:
                    # Usuário optou por não informar
                    state.data["ponto_referencia"] = None
                    logger.info("Usuário optou por não informar ponto de referência")
                
                state.data["reference_point_collected"] = True
                state.agent_response = None
                return state
                
            except Exception as e:
                # Em caso de erro, assume que não quer informar
                logger.warning(f"Erro ao processar ponto de referência: {e}")
                state.data["ponto_referencia"] = None
                state.data["reference_point_collected"] = True
                state.agent_response = None
                return state
        
        # Solicita ponto de referência com novo texto
        state.agent_response = AgentResponse(
            description="""Agora você pode informar um ponto de referência para ajudar a encontrar o local para o atendimento.

Se for dentro de loteamento, conjunto habitacional, vila ou condomínio, descreva como chegar no local a partir do endereço de acesso.
Se for vila com portão, informe também a casa que abrirá o portão.
Se não for necessário, responda AVANÇAR.""",
            payload_schema=PontoReferenciaPayload.model_json_schema()
        )
        
        return state
    
    def _route_after_confirmation(self, state: ServiceState) -> str:
        """Roteamento após confirmação de endereço."""
        logger.info("[ROTEAMENTO] _route_after_confirmation")
        logger.info(f"[STATE.DATA] address_confirmed: {state.data.get('address_confirmed')}")
        logger.info(f"[STATE.DATA] address_max_attempts_reached: {state.data.get('address_max_attempts_reached')}")
        
        # Se atingiu o máximo de tentativas, sempre termina
        if state.data.get("address_max_attempts_reached"):
            return END
            
        # Se há qualquer agent_response (erro ou solicitação), termina o fluxo
        if state.agent_response:
            return END
            
        # Se confirmou o endereço, vai para ponto de referência
        if state.data.get("address_confirmed"):
            return "collect_reference_point"
        
        # Se não confirmou, volta para coletar novo endereço
        return "collect_address"
    
    def _route_after_reference(self, state: ServiceState) -> str:
        # Após ponto de referência, vai para CPF
        if state.agent_response:
            return END
            
        return "collect_cpf"
    

    
    def build_graph(self) -> StateGraph[ServiceState]:
        """
        Constrói o grafo do workflow de poda de árvore.
        
        Fluxo:
        1. Coleta endereço e confirma
        2. Coleta ponto de referência (opcional)
        3. Coleta CPF (opcional) e verifica cadastro
        4. Se não cadastrado ou faltando dados: coleta email e nome (opcionais)
        5. Abre chamado no SGRC
        """
        graph = StateGraph(ServiceState)
        
        # Adiciona os nós
        graph.add_node("collect_address", self._collect_address)
        graph.add_node("confirm_address", self._confirm_address)
        graph.add_node("collect_reference_point", self._collect_reference_point)
        graph.add_node("collect_cpf", self._collect_cpf)
        graph.add_node("collect_email", self._collect_email)
        graph.add_node("collect_name", self._collect_name)
        graph.add_node("open_ticket", self._open_ticket)
        
        # Define o ponto de entrada
        graph.set_entry_point("collect_address")
        
        # Adiciona as rotas condicionais
        graph.add_conditional_edges(
            "collect_address",
            self._route_after_address,
            {
                "collect_address": "collect_address",
                "confirm_address": "confirm_address",
                "collect_reference_point": "collect_reference_point",
                END: END
            }
        )
        
        graph.add_conditional_edges(
            "confirm_address",
            self._route_after_confirmation,
            {
                "collect_address": "collect_address",
                "collect_reference_point": "collect_reference_point",
                END: END
            }
        )
        
        graph.add_conditional_edges(
            "collect_reference_point",
            self._route_after_reference,
            {
                "collect_cpf": "collect_cpf",
                END: END
            }
        )
        
        graph.add_conditional_edges(
            "collect_cpf",
            self._route_after_cpf,
            {
                "collect_cpf": "collect_cpf",
                "collect_email": "collect_email",
                "collect_name": "collect_name",
                "open_ticket": "open_ticket",
                END: END
            }
        )
        
        graph.add_conditional_edges(
            "collect_email",
            self._route_after_email,
            {
                "collect_email": "collect_email",
                "collect_name": "collect_name",
                "open_ticket": "open_ticket",
                END: END
            }
        )
        
        graph.add_conditional_edges(
            "collect_name",
            self._route_after_name,
            {
                "collect_name": "collect_name",
                "open_ticket": "open_ticket",
                END: END
            }
        )
        
        # Após open_ticket, sempre termina (já tem agent_response definido)
        graph.add_edge("open_ticket", END)
        
        return graph
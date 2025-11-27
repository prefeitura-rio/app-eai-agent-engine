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
from src.tools.multi_step_service.workflows.poda_de_arvore.templates import (
    IdentificationMessageTemplates
)

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
        
        
        # Se já verificou cadastro, pula
        if "cpf" in state.payload:
            try:
                validated_data = CPFPayload.model_validate(state.payload)
                cpf_antigo = state.data.get("cpf")
                cpf_novo = validated_data.cpf
                if cpf_antigo != cpf_novo:
                    # reset?
                    pass
                
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
                                
                        state.data["cadastro_verificado"] = True
                    except:
                        logger.error("Erro ao chamar API para obter informações do usuário.")
                state.agent_response = None
                return state
            
            except Exception as e:
                state.agent_response = AgentResponse(
                    description=IdentificationMessageTemplates.solicitar_cpf(),
                    payload_schema=CPFPayload.model_json_schema(),
                    error_message=f"CPF inválido: {str(e)}"
                )
                # Não retorna aqui - continua para verificar se deve solicitar CPF novamente
                # ou terminar o fluxo

        if "cpf" in state.data:
            return state

        # Se já temos uma resposta de erro (validação falhou), retorna com erro
        if state.agent_response and state.agent_response.error_message:
            return state

        state.agent_response = AgentResponse(
            description=IdentificationMessageTemplates.solicitar_cpf(),
            payload_schema=CPFPayload.model_json_schema(),
        )

        return state
    

    @handle_errors
    async def _collect_email(self, state: ServiceState) -> ServiceState:
        """Coleta email do usuário (opcional)."""
        
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
                email_antigo = state.data.get("email")
                email_novo = validated_data.email
                if email_antigo != email_novo:
                    # reset?
                    pass
                
                state.data["email"] = email_novo
                state.data["email_processed"] = True
                logger.info(f"Email coletado: {email_novo}")
                state.agent_response = None
                return state
            
            except Exception as e:
                # Email inválido - solicita novamente
                state.agent_response = AgentResponse(
                    description="Por favor, informe um email válido (ou deixe em branco para pular):",
                    payload_schema=EmailPayload.model_json_schema(),
                    error_message=f"Email inválido: {str(e)}"
                )
                return state

        # Se já processou (tem email ou foi pulado), retorna
        if state.data.get("email_processed"):
            return state

        # Se já temos uma resposta de erro (validação falhou), retorna com erro
        if state.agent_response and state.agent_response.error_message:
            return state

        state.agent_response = AgentResponse(
            description="Por favor, informe seu email (opcional - você pode deixar em branco para pular):",
            payload_schema=EmailPayload.model_json_schema(),
        )

        return state
    

    @handle_errors
    async def _collect_name(self, state: ServiceState) -> ServiceState:
        """Coleta nome do usuário (opcional)."""
        
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
                nome_antigo = state.data.get("name")
                nome_novo = validated_data.name
                if nome_antigo != nome_novo:
                    # reset?
                    pass
                
                state.data["name"] = nome_novo
                state.data["name_processed"] = True
                logger.info(f"Nome coletado: {nome_novo}")
                state.agent_response = None
                return state
            
            except Exception as e:
                # Nome inválido - solicita novamente
                state.agent_response = AgentResponse(
                    description="Por favor, informe um nome válido com nome e sobrenome (ou deixe em branco para pular):",
                    payload_schema=NomePayload.model_json_schema(),
                    error_message=f"Nome inválido: {str(e)}"
                )
                return state

        # Se já processou (tem nome ou foi pulado), retorna
        if state.data.get("name_processed"):
            return state

        # Se já temos uma resposta de erro (validação falhou), retorna com erro
        if state.agent_response and state.agent_response.error_message:
            return state

        state.agent_response = AgentResponse(
            description="Por favor, informe seu nome completo (opcional - você pode deixar em branco para pular):",
            payload_schema=NomePayload.model_json_schema(),
        )

        return state

    
    @handle_errors
    async def _collect_address(self, state: ServiceState) -> ServiceState:
        """Coleta endereço do usuário para a solicitação."""
        
        # Se já coletou endereço validado e confirmado, pula
        if state.data.get("address_validated") and state.data.get("address_confirmed"):
            return state
            
        # Inicializa estado de validação se não existe
        if "address_validation" not in state.data:
            state.data["address_validation"] = AddressValidationState().model_dump()
        
        validation_state = AddressValidationState(**state.data["address_validation"])
        
        # Se está recebendo confirmação do endereço
        if "confirmacao" in state.payload and state.data.get("address_needs_confirmation"):
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
                    logger.info("Endereço não confirmado, solicitando novo endereço")
                    
                    # Incrementa contador de tentativas
                    validation_state.attempts += 1
                    state.data["address_validation"] = validation_state.model_dump()
                    
                    # Verifica se ainda tem tentativas
                    if validation_state.attempts >= validation_state.max_attempts:
                        state.agent_response = AgentResponse(
                            description="Não foi possível validar o endereço após 3 tentativas. Por favor, tente novamente mais tarde ou entre em contato pelo telefone 1746.",
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
                if validation_state.attempts > validation_state.max_attempts:
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
                
                logger.info(f"Endereço identificado, pedindo confirmação: {address_text}")
                
                # Monta mensagem de confirmação diretamente aqui
                confirmacao_parts = []
                
                if address_data.logradouro_nome_ipp:
                    confirmacao_parts.append(f"• Logradouro: {address_data.logradouro_nome_ipp}")
                elif address_data.logradouro:
                    confirmacao_parts.append(f"• Logradouro: {address_data.logradouro}")
                
                if address_data.numero:
                    confirmacao_parts.append(f"• Número: {address_data.numero}")
                
                if address_data.bairro_nome_ipp:
                    confirmacao_parts.append(f"• Bairro: {address_data.bairro_nome_ipp}")
                elif address_data.bairro:
                    confirmacao_parts.append(f"• Bairro: {address_data.bairro}")
                
                confirmacao_parts.append(f"• Cidade: {address_data.cidade}, {address_data.estado}")
                
                mensagem_confirmacao = "\n".join(confirmacao_parts)
                
                state.agent_response = AgentResponse(
                    description=f"Por favor, confirme se o endereço está correto:\n\n{mensagem_confirmacao}\n\nO endereço está correto?",
                    payload_schema=AddressConfirmationPayload.model_json_schema()
                )
                
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

    @handle_errors
    async def _format_data(self, state: ServiceState) -> ServiceState:
        """Formata dados para exibição (CPF com máscara)."""
        
        user_info = state.data.get("user_info", {})
        cpf = user_info.get("cpf", "")
        
        # Formata CPF para exibição: XXX.XXX.XXX-XX
        if cpf and len(cpf) == 11:
            state.data["cpf_formatted"] = f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}"
        
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
                description="Infelizmente houve um erro e a solicitação não pôde ser criada."
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
                description="O sistema está indisponível no momento.\n\nAguarde, que sua solicitação será criada assim que o sistema voltar ao normal. Nesse momento você vai receber o número de protocolo.\n\nSeu atendimento está finalizado, obrigado!"
            )
            return state
        except Exception as exc:
            logger.exception(exc)
            state.data["ticket_created"] = False
            state.data["error"] = "erro_geral"
            state.agent_response = AgentResponse(
                description="Houve um erro ao abrir o chamado. Por favor, tente novamente mais tarde.",
                error_message=str(exc)
            )
            return state


    # --- Roteamento Condicional ---

    def _decide_after_data_collection(self, state: ServiceState) -> str:
        if state.agent_response is not None:
            return END
        return "continue"
    
    def _route_after_cpf(self, state: ServiceState) -> str:
        
        # Se há qualquer agent_response (erro ou solicitação), termina o fluxo
        if state.agent_response:
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
        return "collect_cpf"
    
    def _route_after_email(self, state: ServiceState) -> str:
        
        # Se há qualquer agent_response (erro ou solicitação), termina o fluxo
        if state.agent_response:
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
        return "collect_email"
    
    def _route_after_name(self, state: ServiceState) -> str:
        # Se há qualquer agent_response (erro ou solicitação), termina o fluxo
        if state.agent_response:
            return END
            
        # Se já processou nome (informou ou pulou), vai para abrir ticket
        if state.data.get("name_processed"):
            return "open_ticket"
        
        return "collect_name"
    
    @handle_errors
    async def _confirm_address(self, state: ServiceState) -> ServiceState:
        """Confirma o endereço identificado com o usuário."""
        
        # Se já confirmou ou não precisa confirmar
        if state.data.get("address_confirmed") or not state.data.get("address_needs_confirmation"):
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
                    state.data["need_reference_point"] = True  # Marca que precisa pedir ponto de referência
                    logger.info("Endereço confirmado pelo usuário")
                    state.agent_response = None
                    return state
                else:
                    # Usuário não confirmou, volta para coletar endereço
                    state.data["address_needs_confirmation"] = False
                    state.data["address_temp"] = None
                    logger.info("Endereço não confirmado, solicitando novo endereço")
                    
                    # Incrementa contador de tentativas
                    validation_state = AddressValidationState(**state.data.get("address_validation", {}))
                    validation_state.attempts += 1
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
        
        # Monta mensagem de confirmação
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
        
        state.agent_response = AgentResponse(
            description=f"Por favor, confirme se o endereço está correto:\n\n{mensagem_confirmacao}\n\nO endereço está correto?",
            payload_schema=AddressConfirmationPayload.model_json_schema()
        )
        
        return state
    
    def _route_after_address(self, state: ServiceState) -> str:
        # Se atingiu o máximo de tentativas, sempre termina
        if state.data.get("address_max_attempts_reached"):
            return END
            
        # Se há qualquer agent_response (erro ou solicitação), termina o fluxo
        if state.agent_response:
            return END
        
        # Se endereço foi validado e confirmado, prossegue
        if state.data.get("address_validated") and state.data.get("address_confirmed"):
            return "collect_reference_point"
            
        # Continua coletando endereço (incluindo confirmação)
        return "collect_address"
    
    @handle_errors
    async def _collect_reference_point(self, state: ServiceState) -> ServiceState:
        """Coleta ponto de referência opcional."""
        
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
        # Se atingiu o máximo de tentativas, sempre termina
        if state.data.get("address_max_attempts_reached"):
            return END
            
        # Se há qualquer agent_response (erro ou solicitação), termina o fluxo
        if state.agent_response:
            return END
            
        # Se confirmou o endereço e precisa pedir ponto de referência
        if state.data.get("address_confirmed") and state.data.get("need_reference_point"):
            return "collect_reference_point"
        
        # Se confirmou e já tem ponto de referência (ou não precisa)
        if state.data.get("address_confirmed"):
            return "open_ticket"
        
        # Se não confirmou, volta para coletar
        return "collect_address"
    
    def _route_after_reference(self, state: ServiceState) -> str:
        # Após ponto de referência, vai para CPF
        if state.agent_response:
            return END
            
        return "collect_cpf"
    
    def _route_after_ticket(self, state: ServiceState) -> str:
        # Sempre termina após tentar criar o ticket
        return END
    
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
        graph.add_node("collect_reference_point", self._collect_reference_point)
        graph.add_node("collect_cpf", self._collect_cpf)
        graph.add_node("collect_email", self._collect_email)
        graph.add_node("collect_name", self._collect_name)
        graph.add_node("open_ticket", self._open_ticket)
        
        # Define o ponto de entrada - AGORA É ENDEREÇO
        graph.set_entry_point("collect_address")
        
        # Adiciona as rotas condicionais
        graph.add_conditional_edges(
            "collect_address",
            self._route_after_address,
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
        
        graph.add_conditional_edges(
            "open_ticket",
            self._route_after_ticket,
            {
                END: END
            }
        )
        
        return graph
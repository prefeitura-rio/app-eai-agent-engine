"""
Serviço avançado de conta bancária com estrutura de dados complexa e aninhada.
Demonstra capacidades de processamento de JSON estruturado e dependências avançadas.
"""

import json
from typing import Tuple, Dict, Any
from datetime import datetime

from src.services.base_service import BaseService
from src.services.schema import ServiceDefinition, StepInfo


class BankAccountAdvancedService(BaseService):
    """
    Serviço avançado para criação de conta bancária com dados estruturados.

    Estrutura final de dados:
    {
        "user_info": {
            "name": str,
            "document_number": str,
            "email": str,
            "document_type": str
        },
        "account_info": {
            "account_type": str,
            "bank_name": str,
            "agency_number": str,
            "account_number": str
        },
        "address": {
            "street": str,
            "number": int
        },
        "contact": {
            "email": str,
            "phone": str
        },
        "deposits": [
            {
                "amount": float,
                "date": str (ISO format)
            }
        ]
    }
    """

    service_name = "bank_account_advanced"

    def get_service_definition(self) -> ServiceDefinition:
        return ServiceDefinition(
            service_name=self.service_name,
            description="Hybrid bank account service with substeps for user_info and append-mode for deposits",
            steps=[
                # User Info - Step with substeps
                StepInfo(
                    name="user_info",
                    description="Informações completas do usuário (JSON final, mas com substeps)",
                    payload_example={
                        "name": "João Silva",
                        "document_number": "12345678901",
                        "email": "test@example.com",
                        "document_type": "CPF",
                    },
                    required=True,
                    data_type="dict",
                    substeps=[
                        StepInfo(
                            name="name",
                            description="Nome completo do usuário",
                            payload_example={"name": "João Silva"},
                            required=True,
                            data_type="str",
                        ),
                        StepInfo(
                            name="document_number",
                            description="Número do documento (CPF ou CNPJ)",
                            payload_example={"document_number": "12345678901"},
                            required=True,
                            data_type="str",
                        ),
                        StepInfo(
                            name="email",
                            description="E-mail do usuário",
                            payload_example={"email": "test@example.com"},
                            required=True,
                            data_type="str",
                        ),
                        StepInfo(
                            name="document_type",
                            description="Tipo de documento (CPF ou CNPJ)",
                            payload_example={"document_type": "CPF"},
                            required=True,
                            data_type="str",
                        ),
                    ],
                ),
                # Account Info Group (mantém JSON simples)
                StepInfo(
                    name="account_info",
                    description="Informações da conta bancária em formato JSON",
                    payload_example={
                        "account_info": {
                            "account_type": "corrente",
                            "bank_name": "Banco do Brasil",
                            "agency_number": "1234",
                            "account_number": "56789-0",
                        }
                    },
                    required=True,
                    data_type="dict",
                    depends_on=["user_info"],
                ),
                # Address Group (mantém JSON simples)
                StepInfo(
                    name="address",
                    description="Endereço completo em formato JSON",
                    payload_example={"address": {"street": "Rua A", "number": 123}},
                    required=True,
                    data_type="dict",
                    depends_on=["user_info"],
                ),
                # Contact Group (mantém JSON simples)
                StepInfo(
                    name="contact",
                    description="Informações de contato em formato JSON",
                    payload_example={
                        "contact": {"email": "test@example.com", "phone": "1234567890"}
                    },
                    required=True,
                    data_type="dict",
                    depends_on=["user_info"],
                ),
                # Deposits - Array step (append mode automático)
                StepInfo(
                    name="deposits",
                    description="Depósito individual ou lista de depósitos (modo append automático)",
                    payload_example={
                        "deposits": [
                            {"amount": 1000.0, "date": "2025-09-19T11:57:13.205906"}
                        ]
                    },
                    required=False,
                    data_type="list_dict",
                    depends_on=["account_info", "address", "contact"],
                ),
            ],
        )

    def execute_step(self, step: str, payload: str) -> Tuple[bool, str]:
        """
        Valida e processa cada step com detecção automática baseada em data_type.
        Suporta substeps individuais (user_info_name, user_info_email, etc.)
        - data_type="dict": salva JSON como dicionário
        - data_type="list_dict": detecção automática de append em arrays
        - data_type="string": salva como string (default)
        """
        payload = payload.strip()

        # Primeiro verificar se é um step principal válido
        definition = self.get_service_definition()
        step_info = definition.get_step_info(step)

        # Se é um step principal válido, processar como tal
        if step_info:
            pass  # Continue with main step logic
        # Se não é step principal e tem underscore, pode ser substep
        elif "_" in step:
            return self._handle_substep(step, payload)
        else:
            return False, f"Step '{step}' não reconhecido"

        # Processar baseado no data_type
        if step_info.data_type == "list_dict":
            # Modo append automático para listas de objetos
            return self._handle_array_step(step, payload)

        elif step_info.data_type == "dict":
            # JSON como dicionário
            return self._handle_dict_step(step, payload)

        elif step_info.data_type == "str":
            # String simples
            return self._handle_string_step(step, payload)

        else:
            return (
                False,
                f"data_type '{step_info.data_type}' não suportado para step '{step}'",
            )

    def _handle_array_step(self, step: str, payload: str) -> Tuple[bool, str]:
        """
        Manipula steps com data_type="list_dict" com detecção automática de append.
        Se o step já existe, faz append. Caso contrário, inicializa a lista.
        """
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            return False, f"{step} deve ser um JSON válido"

        # Inicializar array se não existir
        if step not in self.data:
            self.data[step] = []

        # Se recebeu um array, validar cada item e fazer extend
        if isinstance(data, list):
            for i, item in enumerate(data):
                if step == "deposits":
                    is_valid, error_msg = self._validate_single_deposit(item, i)
                    if not is_valid:
                        return False, error_msg

            # Se todas as validações passaram, adicionar todos ao array
            self.data[step].extend(data)
            return True, ""

        # Se recebeu um objeto único, validar e fazer append
        elif isinstance(data, dict):
            if step == "deposits":
                is_valid, error_msg = self._validate_single_deposit(
                    data, len(self.data[step]) + 1
                )
                if not is_valid:
                    return False, error_msg

            self.data[step].append(data)
            return True, ""

        else:
            return False, f"{step} deve ser um objeto JSON ou array de objetos"

    def _handle_substep(self, substep_key: str, payload: str) -> Tuple[bool, str]:
        """
        Manipula substeps individuais (ex: user_info_name, user_info_email).
        Acumula os dados e monta o JSON final quando todos estão completos.
        """
        # Separar step principal e substep - precisa encontrar o step principal correto
        definition = self.get_service_definition()

        # Tentar encontrar qual step principal possui substeps que correspondem
        main_step = None
        substep_name = None

        for step_info in definition.steps:
            if step_info.substeps and substep_key.startswith(step_info.name + "_"):
                main_step = step_info.name
                substep_name = substep_key[
                    len(step_info.name) + 1 :
                ]  # Remove "step_name_"
                break

        if not main_step or not substep_name:
            return False, f"Formato de substep inválido: {substep_key}"

        # Verificar se o step principal existe e tem substeps
        definition = self.get_service_definition()
        step_info = definition.get_step_info(main_step)
        if not step_info or not step_info.substeps:
            return False, f"Step '{main_step}' não tem substeps"

        # Verificar se o substep existe
        substep_info = None
        for sub in step_info.substeps:
            if sub.name == substep_name:
                substep_info = sub
                break

        if not substep_info:
            return False, f"Substep '{substep_name}' não encontrado em '{main_step}'"

        # Validar o valor do substep baseado no data_type
        if substep_info.data_type == "str":
            if not payload or not payload.strip():
                return False, f"{substep_name} não pode estar vazio"

            # Validações específicas para cada substep
            is_valid, error_msg = self._validate_substep_value(
                main_step, substep_name, payload.strip()
            )
            if not is_valid:
                return False, error_msg

        # Inicializar o step principal como dict se não existir
        if main_step not in self.data:
            self.data[main_step] = {}

        # Salvar o substep diretamente no step principal
        self.data[main_step][substep_name] = payload.strip()

        # Verificar se todos os substeps obrigatórios estão completos
        required_substeps = [sub.name for sub in step_info.substeps if sub.required]
        completed_substeps = self.data[main_step]

        # Se não tem todos os substeps obrigatórios, o step ainda não está "completo"
        # mas os dados estão sendo salvos de forma limpa
        if not all(sub in completed_substeps for sub in required_substeps):
            # Step parcialmente completo - dados salvos de forma limpa no formato final
            pass

        return True, ""

    def _validate_substep_value(
        self, main_step: str, substep_name: str, value: str
    ) -> Tuple[bool, str]:
        """Valida valores específicos de substeps"""
        if main_step == "user_info":
            if substep_name == "name":
                if len(value) < 2:
                    return False, "Nome deve ter pelo menos 2 caracteres"

            elif substep_name == "document_number":
                doc_clean = value.replace(".", "").replace("-", "").replace("/", "")
                if not doc_clean.isdigit() or len(doc_clean) not in [11, 14]:
                    return (
                        False,
                        "Documento deve ter 11 dígitos (CPF) ou 14 dígitos (CNPJ)",
                    )

            elif substep_name == "email":
                if "@" not in value or "." not in value:
                    return False, "Email deve ter formato válido"

            elif substep_name == "document_type":
                if value.upper() not in ["CPF", "CNPJ"]:
                    return False, "Tipo de documento deve ser 'CPF' ou 'CNPJ'"

        return True, ""

    def _is_partial_substeps(self, step: str, data: Dict[str, Any]) -> bool:
        """Detecta se os dados são substeps parciais ou dados completos"""
        definition = self.get_service_definition()
        step_info = definition.get_step_info(step)

        if not step_info or not step_info.substeps:
            return False

        # Obter nomes dos substeps
        substep_names = {substep.name for substep in step_info.substeps}
        data_keys = set(data.keys())

        # Se todas as chaves são substeps válidos mas não são todos os obrigatórios,
        # então é um conjunto parcial
        if data_keys.issubset(substep_names):
            required_substeps = {
                substep.name for substep in step_info.substeps if substep.required
            }
            # É parcial se não tem todos os obrigatórios
            return not required_substeps.issubset(data_keys)

        return False

    def _handle_partial_substeps(
        self, step: str, data: Dict[str, Any]
    ) -> Tuple[bool, str]:
        """Manipula substeps parciais - acumula dados e valida individualmente"""
        # Inicializar step se não existir
        if step not in self.data:
            self.data[step] = {}

        # Validar cada substep individualmente
        for substep_name, substep_value in data.items():
            is_valid, error_msg = self._validate_substep_value(
                step, substep_name, str(substep_value)
            )
            if not is_valid:
                return False, error_msg

            # Salvar substep se válido
            self.data[step][substep_name] = substep_value

        return True, ""

    def _handle_dict_step(self, step: str, payload: str) -> Tuple[bool, str]:
        """
        Manipula steps com data_type=dict - valida JSON e salva como dicionário.
        Detecta automaticamente se são substeps parciais ou JSON completo.
        """
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            return False, f"{step} deve ser um JSON válido"

        if not isinstance(data, dict):
            return False, f"{step} deve ser um objeto JSON"

        # Detectar se é um conjunto parcial de substeps ou dados completos
        if step == "user_info" and self._is_partial_substeps(step, data):
            # É um conjunto parcial de substeps - acumular
            return self._handle_partial_substeps(step, data)

        # Validação específica baseada no step (dados completos)
        if step == "user_info":
            is_valid, error_msg = self._validate_user_info(payload)
        elif step == "account_info":
            is_valid, error_msg = self._validate_account_info(payload)
        elif step == "address":
            is_valid, error_msg = self._validate_address(payload)
        elif step == "contact":
            is_valid, error_msg = self._validate_contact(payload)
        else:
            # Validação genérica para outros steps dict
            is_valid, error_msg = True, ""

        if is_valid:
            self.data[step] = data

        return is_valid, error_msg

    def _handle_string_step(self, step: str, payload: str) -> Tuple[bool, str]:
        """
        Manipula steps com data_type=str - salva como string.
        """
        if not payload or not payload.strip():
            return False, f"{step} não pode estar vazio"

        # Validação específica pode ser adicionada aqui baseada no step
        self.data[step] = payload.strip()
        return True, ""

    def _validate_single_deposit(
        self, deposit: Dict[str, Any], index: int
    ) -> Tuple[bool, str]:
        """Valida um único depósito"""
        if not isinstance(deposit, dict):
            return False, f"Depósito {index} deve ser um objeto JSON"

        if "amount" not in deposit:
            return False, f"Campo 'amount' obrigatório no depósito {index}"

        # amount pode ser float ou string numérica
        try:
            amount = float(deposit["amount"])
            if amount <= 0:
                return False, f"Amount no depósito {index} deve ser positivo"
        except (ValueError, TypeError):
            return False, f"Amount no depósito {index} deve ser numérico"

        if "date" not in deposit:
            return False, f"Campo 'date' obrigatório no depósito {index}"

        # Validar formato de data ISO
        try:
            datetime.fromisoformat(deposit["date"].replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            return (
                False,
                f"Date no depósito {index} deve estar em formato ISO (YYYY-MM-DDTHH:MM:SS)",
            )

        return True, ""

    def _validate_user_info(self, payload: str) -> Tuple[bool, str]:
        """Valida estrutura user_info"""
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            return False, "user_info deve ser um JSON válido"

        required_fields = ["name", "document_number", "email", "document_type"]
        for field in required_fields:
            if field not in data:
                return False, f"Campo obrigatório '{field}' ausente em user_info"
            if not isinstance(data[field], str) or not data[field].strip():
                return False, f"Campo '{field}' deve ser uma string não vazia"

        # Validações específicas
        if data["document_type"] not in ["CPF", "CNPJ"]:
            return False, "document_type deve ser 'CPF' ou 'CNPJ'"

        # Validar CPF/CNPJ
        doc_num = (
            data["document_number"].replace(".", "").replace("-", "").replace("/", "")
        )
        if data["document_type"] == "CPF" and len(doc_num) != 11:
            return False, "CPF deve ter 11 dígitos"
        elif data["document_type"] == "CNPJ" and len(doc_num) != 14:
            return False, "CNPJ deve ter 14 dígitos"

        # Validar email básico
        if "@" not in data["email"] or "." not in data["email"]:
            return False, "Email deve ter formato válido"

        return True, ""

    def _validate_account_info(self, payload: str) -> Tuple[bool, str]:
        """Valida estrutura account_info"""
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            return False, "account_info deve ser um JSON válido"

        required_fields = [
            "account_type",
            "bank_name",
            "agency_number",
            "account_number",
        ]
        for field in required_fields:
            if field not in data:
                return False, f"Campo obrigatório '{field}' ausente em account_info"
            if not isinstance(data[field], str) or not data[field].strip():
                return False, f"Campo '{field}' deve ser uma string não vazia"

        # Validações específicas
        if data["account_type"] not in ["corrente", "poupança", "investimento"]:
            return (
                False,
                "account_type deve ser 'corrente', 'poupança' ou 'investimento'",
            )

        # Validar números da agência e conta
        if not data["agency_number"].isdigit():
            return False, "agency_number deve conter apenas números"

        account_clean = data["account_number"].replace("-", "")
        if not account_clean.isdigit():
            return False, "account_number deve conter apenas números e hífen"

        return True, ""

    def _validate_address(self, payload: str) -> Tuple[bool, str]:
        """Valida estrutura address"""
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            return False, "address deve ser um JSON válido"
        if (
            "street" not in data
            or not isinstance(data["street"], str)
            or not data["street"].strip()
        ):
            return False, "Campo 'street' obrigatório e deve ser string não vazia"

        if "number" not in data:
            return False, "Campo 'number' obrigatório"
        data["number"] = int(data["number"])
        # number pode ser int ou string numérica
        if isinstance(data["number"], str):
            if not data["number"].isdigit():
                return False, "Campo 'number' deve ser numérico"
        elif not isinstance(data["number"], int):
            return False, "Campo 'number' deve ser número inteiro"

        return True, ""

    def _validate_contact(self, payload: str) -> Tuple[bool, str]:
        """Valida estrutura contact"""
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            return False, "contact deve ser um JSON válido"

        required_fields = ["email", "phone"]
        for field in required_fields:
            if field not in data:
                return False, f"Campo obrigatório '{field}' ausente em contact"
            if not isinstance(data[field], str) or not data[field].strip():
                return False, f"Campo '{field}' deve ser uma string não vazia"

        # Validar email
        if "@" not in data["email"] or "." not in data["email"]:
            return False, "Email deve ter formato válido"

        # Validar telefone (apenas dígitos)
        phone_clean = (
            data["phone"]
            .replace("(", "")
            .replace(")", "")
            .replace("-", "")
            .replace(" ", "")
        )
        if not phone_clean.isdigit():
            return False, "Phone deve conter apenas números"

        if len(phone_clean) < 10 or len(phone_clean) > 11:
            return False, "Phone deve ter 10 ou 11 dígitos"

        return True, ""

    def get_completion_message(self) -> str:
        """Mensagem de conclusão do serviço"""
        return f"🎉 Conta bancária avançada criada com sucesso! Dados estruturados processados para usuário {self.user_id}."

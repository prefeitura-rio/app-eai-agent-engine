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
                    example='{"name": "João Silva", "document_number": "12345678901", "email": "test@example.com", "document_type": "CPF"}',
                    required=True,
                    data_type="dict",
                    substeps=[
                        StepInfo(
                            name="name",
                            description="Nome completo do usuário",
                            example="João Silva",
                            required=True,
                            data_type="str"
                        ),
                        StepInfo(
                            name="document_number",
                            description="Número do documento (CPF ou CNPJ)",
                            example="12345678901",
                            required=True,
                            data_type="str"
                        ),
                        StepInfo(
                            name="email",
                            description="E-mail do usuário",
                            example="test@example.com",
                            required=True,
                            data_type="str"
                        ),
                        StepInfo(
                            name="document_type",
                            description="Tipo de documento (CPF ou CNPJ)",
                            example="CPF",
                            required=True,
                            data_type="str"
                        )
                    ]
                ),
                
                # Account Info Group (mantém JSON simples)
                StepInfo(
                    name="account_info", 
                    description="Informações da conta bancária em formato JSON",
                    example='{"account_type": "corrente", "bank_name": "Banco do Brasil", "agency_number": "1234", "account_number": "56789-0"}',
                    required=True,
                    data_type="dict",
                    depends_on=["user_info"]
                ),
                
                # Address Group (mantém JSON simples)
                StepInfo(
                    name="address",
                    description="Endereço completo em formato JSON",
                    example='{"street": "Rua A", "number": 123}',
                    required=True,
                    data_type="dict",
                    depends_on=["user_info"]
                ),
                
                # Contact Group (mantém JSON simples)
                StepInfo(
                    name="contact",
                    description="Informações de contato em formato JSON",
                    example='{"email": "test@example.com", "phone": "1234567890"}',
                    required=True,
                    data_type="dict",
                    depends_on=["user_info"]
                ),
                
                # Deposits - Array step (append mode automático)
                StepInfo(
                    name="deposits",
                    description="Depósito individual ou lista de depósitos (modo append automático)",
                    example='{"amount": 1000.0, "date": "2025-09-19T11:57:13.205906"}',
                    required=False,
                    data_type="list_dict",
                    depends_on=["account_info", "address", "contact"]
                )
            ]
        )
    
    def execute_step(self, step: str, payload: str) -> Tuple[bool, str]:
        """
        Valida e processa cada step com detecção automática baseada em data_type.
        - data_type="dict": salva JSON como dicionário
        - data_type="list_dict": detecção automática de append em arrays
        - data_type="string": salva como string (default)
        """
        payload = payload.strip()
        
        # Obter informações do step
        definition = self.get_service_definition()
        step_info = definition.get_step_info(step)
        if not step_info:
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
            return False, f"data_type '{step_info.data_type}' não suportado para step '{step}'"
    
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
                is_valid, error_msg = self._validate_single_deposit(data, len(self.data[step]) + 1)
                if not is_valid:
                    return False, error_msg
            
            self.data[step].append(data)
            return True, ""
        
        else:
            return False, f"{step} deve ser um objeto JSON ou array de objetos"
    
    def _handle_dict_step(self, step: str, payload: str) -> Tuple[bool, str]:
        """
        Manipula steps com data_type=dict - valida JSON e salva como dicionário.
        """
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            return False, f"{step} deve ser um JSON válido"
        
        if not isinstance(data, dict):
            return False, f"{step} deve ser um objeto JSON"
        
        # Validação específica baseada no step
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
    
    def _validate_single_deposit(self, deposit: Dict[str, Any], index: int) -> Tuple[bool, str]:
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
            return False, f"Date no depósito {index} deve estar em formato ISO (YYYY-MM-DDTHH:MM:SS)"
        
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
        doc_num = data["document_number"].replace(".", "").replace("-", "").replace("/", "")
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
        
        required_fields = ["account_type", "bank_name", "agency_number", "account_number"]
        for field in required_fields:
            if field not in data:
                return False, f"Campo obrigatório '{field}' ausente em account_info"
            if not isinstance(data[field], str) or not data[field].strip():
                return False, f"Campo '{field}' deve ser uma string não vazia"
        
        # Validações específicas
        if data["account_type"] not in ["corrente", "poupança", "investimento"]:
            return False, "account_type deve ser 'corrente', 'poupança' ou 'investimento'"
        
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
        
        if "street" not in data or not isinstance(data["street"], str) or not data["street"].strip():
            return False, "Campo 'street' obrigatório e deve ser string não vazia"
        
        if "number" not in data:
            return False, "Campo 'number' obrigatório"
        
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
        phone_clean = data["phone"].replace("(", "").replace(")", "").replace("-", "").replace(" ", "")
        if not phone_clean.isdigit():
            return False, "Phone deve conter apenas números"
        
        if len(phone_clean) < 10 or len(phone_clean) > 11:
            return False, "Phone deve ter 10 ou 11 dígitos"
        
        return True, ""
    
    
    def get_completion_message(self) -> str:
        """Mensagem de conclusão do serviço"""
        return f"🎉 Conta bancária avançada criada com sucesso! Dados estruturados processados para usuário {self.user_id}."
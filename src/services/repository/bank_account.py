import re
from typing import List, Tuple

from src.services.base_service import BaseService
from src.services.schema import StepInfo, ConditionalDependency


class BankAccountService(BaseService):
    """Advanced service demonstrating complex dependencies for bank account creation"""
    
    service_name = "bank_account"

    def get_steps_info(self) -> List[StepInfo]:
        return [
            StepInfo(
                name="document_type",
                description="Tipo de documento (CPF ou CNPJ)",
                example="CPF",
                required=True,
            ),
            StepInfo(
                name="document_number",
                description="Número do documento",
                example="12345678901",
                required=True,
                depends_on=["document_type"],
                validation_depends_on=["document_type"],
            ),
            StepInfo(
                name="account_type",
                description="Tipo de conta (corrente ou poupança)",
                example="corrente",
                required=True,
            ),
            StepInfo(
                name="initial_deposit",
                description="Depósito inicial em reais",
                example="1000.00",
                required=False,
                depends_on=["account_type"],
                conditional=ConditionalDependency(
                    if_condition={"account_type": "corrente"},
                    then_required=["initial_deposit"],
                    else_required=[]
                ),
            ),
            StepInfo(
                name="business_name",
                description="Nome da empresa (apenas para CNPJ)",
                example="Empresa XYZ Ltda",
                required=False,
                conditional=ConditionalDependency(
                    if_condition={"document_type": "CNPJ"},
                    then_required=["business_name"],
                    else_required=[]
                ),
                conflicts_with=["personal_name"],
            ),
            StepInfo(
                name="personal_name",
                description="Nome completo da pessoa (apenas para CPF)",
                example="João da Silva",
                required=False,
                conditional=ConditionalDependency(
                    if_condition={"document_type": "CPF"},
                    then_required=["personal_name"],
                    else_required=[]
                ),
                conflicts_with=["business_name"],
            ),
            StepInfo(
                name="email",
                description="E-mail para contato",
                example="contato@exemplo.com",
                required=True,
                depends_on=["document_number"],
            ),
        ]

    def execute_step(self, step: str, payload: str) -> Tuple[bool, str]:
        payload = payload.strip()

        if step == "document_type":
            return self._validate_document_type(payload)
        elif step == "document_number":
            return self._validate_document_number(payload)
        elif step == "account_type":
            return self._validate_account_type(payload)
        elif step == "initial_deposit":
            return self._validate_initial_deposit(payload)
        elif step == "business_name":
            return self._validate_business_name(payload)
        elif step == "personal_name":
            return self._validate_personal_name(payload)
        elif step == "email":
            return self._validate_email(payload)

        return False, "Step inválido"

    def get_completion_message(self) -> str:
        doc_type = self.data.get("document_type", "")
        name = self.data.get("personal_name") or self.data.get("business_name", "")
        account_type = self.data.get("account_type", "")
        
        return f"Conta {account_type} criada com sucesso para {name} ({doc_type}: {self.data.get('document_number', '')})"

    def _validate_document_type(self, doc_type: str) -> Tuple[bool, str]:
        if doc_type.upper() not in ["CPF", "CNPJ"]:
            return False, "Tipo de documento deve ser CPF ou CNPJ"
        return True, ""

    def _validate_document_number(self, doc_number: str) -> Tuple[bool, str]:
        doc_type = self.data.get("document_type", "").upper()
        
        if doc_type == "CPF":
            return self._validate_cpf(doc_number)
        elif doc_type == "CNPJ":
            return self._validate_cnpj(doc_number)
        
        return False, "Tipo de documento deve ser definido primeiro"

    def _validate_cpf(self, cpf: str) -> Tuple[bool, str]:
        cpf_clean = re.sub(r"[^0-9]", "", cpf)
        if len(cpf_clean) != 11:
            return False, "CPF deve ter 11 dígitos"
        if cpf_clean == cpf_clean[0] * 11:
            return False, "CPF inválido"
        return True, ""

    def _validate_cnpj(self, cnpj: str) -> Tuple[bool, str]:
        cnpj_clean = re.sub(r"[^0-9]", "", cnpj)
        if len(cnpj_clean) != 14:
            return False, "CNPJ deve ter 14 dígitos"
        if cnpj_clean == cnpj_clean[0] * 14:
            return False, "CNPJ inválido"
        return True, ""

    def _validate_account_type(self, account_type: str) -> Tuple[bool, str]:
        if account_type.lower() not in ["corrente", "poupança", "poupanca"]:
            return False, "Tipo de conta deve ser 'corrente' ou 'poupança'"
        return True, ""

    def _validate_initial_deposit(self, deposit: str) -> Tuple[bool, str]:
        try:
            value = float(deposit.replace(",", "."))
            if value < 0:
                return False, "Depósito não pode ser negativo"
            if self.data.get("account_type", "").lower() == "corrente" and value < 100:
                return False, "Conta corrente requer depósito mínimo de R$ 100,00"
            return True, ""
        except ValueError:
            return False, "Depósito deve ser um valor numérico válido"

    def _validate_business_name(self, name: str) -> Tuple[bool, str]:
        if len(name) < 2:
            return False, "Nome da empresa deve ter pelo menos 2 caracteres"
        return True, ""

    def _validate_personal_name(self, name: str) -> Tuple[bool, str]:
        if len(name) < 2:
            return False, "Nome deve ter pelo menos 2 caracteres"
        if not re.match(r"^[a-zA-ZÀ-ÿ\s]+$", name):
            return False, "Nome deve conter apenas letras e espaços"
        return True, ""

    def _validate_email(self, email: str) -> Tuple[bool, str]:
        email_pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
        if not re.match(email_pattern, email):
            return False, "E-mail inválido"
        return True, ""
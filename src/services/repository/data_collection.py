import re
from typing import List, Tuple

from src.services.base_service import BaseService
from src.services.schema import StepInfo, ServiceDefinition


class DataCollectionService(BaseService):
    """Service for collecting user personal data"""
    
    service_name = "data_collection"

    def get_service_definition(self) -> ServiceDefinition:
        return ServiceDefinition(
            service_name=self.service_name,
            description="Service for collecting user personal data",
            steps=[
                StepInfo(
                    name="cpf",
                    description="Coleta e valida o CPF do usuário",
                    example="12345678901",
                    required=True,
                ),
                StepInfo(
                    name="email",
                    description="Coleta e valida o e-mail do usuário",
                    example="example@gmail.com",
                    required=True,
                ),
                StepInfo(
                    name="name",
                    description="Coleta e valida o nome completo do usuário",
                    example="João da Silva",
                    required=True,
                ),
            ]
        )

    def execute_step(self, step: str, payload: str) -> Tuple[bool, str]:
        payload = payload.strip()

        if step == "cpf":
            return self._validate_cpf(payload)
        elif step == "email":
            return self._validate_email(payload)
        elif step == "name":
            return self._validate_name(payload)

        return False, "Step inválido"

    def get_completion_message(self) -> str:
        return f"Dados coletados com sucesso! CPF: {self.data['cpf']}, Email: {self.data['email']}, Nome: {self.data['name']}"

    def _validate_cpf(self, cpf: str) -> Tuple[bool, str]:
        # Remove formatação
        cpf_clean = re.sub(r"[^0-9]", "", cpf)

        if len(cpf_clean) != 11:
            return False, "CPF deve ter 11 dígitos. Tente novamente:"

        # Validação básica - todos os dígitos iguais
        if cpf_clean == cpf_clean[0] * 11:
            return False, "CPF inválido. Tente novamente:"

        return True, ""

    def _validate_email(self, email: str) -> Tuple[bool, str]:
        email_pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
        if not re.match(email_pattern, email):
            return False, "E-mail inválido. Tente novamente:"

        return True, ""

    def _validate_name(self, name: str) -> Tuple[bool, str]:
        if len(name) < 2:
            return False, "Nome deve ter pelo menos 2 caracteres. Tente novamente:"

        if not re.match(r"^[a-zA-ZÀ-ÿ\s]+$", name):
            return False, "Nome deve conter apenas letras e espaços. Tente novamente:"

        return True, ""
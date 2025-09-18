from abc import ABC, abstractmethod
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List


class BaseService(ABC):
    """Base class for all multi-step services"""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.data = {}
        self.created_at = datetime.now()

    @abstractmethod
    def get_steps_info(self) -> List[Dict[str, Any]]:
        """Return detailed information about all steps"""
        pass

    def get_steps(self) -> list:
        """Return list of step names in order"""
        steps_info = self.get_steps_info()
        return [step_data["name"] for step_data in steps_info]

    @abstractmethod
    def execute_step(self, step: str, payload: str) -> Tuple[bool, str]:
        """Validate input for a step. Returns (is_valid, error_message)"""
        pass

    def get_step_prompt(self, step: str) -> str:
        """Get prompt message for a specific step"""
        steps_info = self.get_steps_info()
        for step_data in steps_info:
            if step_data["name"] == step:
                return step_data["prompt"]
        return ""

    @abstractmethod
    def get_completion_message(self) -> str:
        """Get message when service is completed"""
        pass

    def process_step(self, step: str, payload: str) -> Dict[str, Any]:
        """Process a step and return result"""
        # Validate input
        is_valid, error_msg = self.execute_step(step, payload)
        if not is_valid:
            return {
                "status": "error",
                "message": error_msg,
                "next_step": step,
                "completed": False,
            }

        # Store valid data
        self.data[step] = payload

        # Determine next step
        steps = self.get_steps()
        try:
            current_idx = steps.index(step)
        except ValueError:
            return {
                "status": "error",
                "message": f"Step '{step}' não encontrado",
                "next_step": step,
                "completed": False,
            }

        if current_idx < len(steps) - 1:
            next_step = steps[current_idx + 1]
            return {
                "status": "success",
                "message": self.get_step_prompt(next_step),
                "next_step": next_step,
                "completed": False,
            }
        else:
            return {
                "status": "completed",
                "message": self.get_completion_message(),
                "next_step": None,
                "completed": True,
                "data": self.data,
            }


class DataCollectionService(BaseService):
    """Service for collecting user personal data"""

    def get_steps_info(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "cpf",
                "description": "Coleta e valida o CPF do usuário",
                "prompt": "Por favor, informe seu CPF:",
                "validation": "Deve conter 11 dígitos numéricos",
                "example": "12345678901",
                "required": True,
                "next_step": "email",
            },
            {
                "name": "email",
                "description": "Coleta e valida o e-mail do usuário",
                "prompt": "Agora informe seu e-mail:",
                "validation": "Deve ser um e-mail válido",
                "example": "example@gmail.com",
                "required": True,
                "next_step": "name",
            },
            {
                "name": "name",
                "description": "Coleta e valida o nome completo do usuário",
                "prompt": "Por fim, seu nome completo:",
                "validation": "Deve conter apenas letras e espaços, mínimo 2 caracteres",
                "example": "João da Silva",
                "required": True,
                "next_step": "end",
            },
        ]

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


# Service Registry
SERVICE_REGISTRY = {
    "data_collection": DataCollectionService,
}

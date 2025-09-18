from abc import ABC, abstractmethod
import re
from datetime import datetime
from typing import Dict, Any, Tuple, List


class BaseService(ABC):
    """Base class for all multi-step services"""

    def __init__(self, user_id: str):
        self.user_id = user_id
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

    @abstractmethod
    def get_completion_message(self) -> str:
        """Get message when service is completed"""
        pass

    def process_bulk(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Process bulk payload using existing step validation"""
        valid_data = {}
        field_errors = {}

        # Use existing step validation for each field
        for step in self.get_steps():
            if step in payload:
                is_valid, error_msg = self.execute_step(step, str(payload[step]))
                if is_valid:
                    valid_data[step] = str(payload[step]).strip()
                else:
                    field_errors[step] = error_msg

        # If no valid data, return error with schema
        if not valid_data:
            return {
                "status": "bulk_validation_error",
                "message": "Nenhum campo válido encontrado",
                "field_errors": field_errors,
                "schema": self.get_schema(),
            }

        # Store valid data
        self.data.update(valid_data)

        # If all steps completed, return success
        steps = self.get_steps()
        if all(step in self.data for step in steps):
            return {
                "status": "bulk_success",
                "completed": True,
                "data": self.data,
                "completion_message": self.get_completion_message(),
            }

        # Partial success - determine next step needed
        next_step = None
        for step in steps:
            if step not in self.data:
                next_step = step
                break

        return {
            "status": "partial_success",
            "next_step_info": self.get_next_step_info(next_step) if next_step else {},
            "field_errors": field_errors,
            "valid_fields": list(valid_data.keys()),
            "completed": False,
            "schema": self.get_schema(),
        }

    def get_schema(self) -> Dict[str, Any]:
        """Generate schema from steps_info"""
        steps_info = self.get_steps_info()
        properties = {}
        required = []

        for step_data in steps_info:
            properties[step_data["name"]] = {
                "type": "string",
                "description": step_data.get("description", ""),
                "example": step_data.get("example", ""),
            }
            if step_data.get("required", True):
                required.append(step_data["name"])

        return {"type": "object", "properties": properties, "required": required}

    def get_next_step_info(self, step: str) -> Dict[str, Any]:
        """Get complete info for next step"""
        steps_info = self.get_steps_info()
        for step_data in steps_info:
            if step_data["name"] == step:
                return step_data
        return {}

    def process_step(self, step: str, payload: str) -> Dict[str, Any]:
        """Process a step and return result"""
        # Validate input
        is_valid, error_msg = self.execute_step(step, payload)
        if not is_valid:
            return {
                "status": "error",
                "next_step_info": self.get_next_step_info(step),
                "completed": False,
                "schema": self.get_schema(),
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
                "next_step_info": self.get_next_step_info(step),
                "completed": False,
                "schema": self.get_schema(),
            }

        if current_idx < len(steps) - 1:
            next_step = steps[current_idx + 1]
            return {
                "status": "success",
                "next_step_info": self.get_next_step_info(next_step),
                "completed": False,
                "schema": self.get_schema(),
            }
        else:
            return {
                "status": "completed",
                "completed": True,
                "data": self.data,
                "completion_message": self.get_completion_message(),
            }


class DataCollectionService(BaseService):
    """Service for collecting user personal data"""

    def get_steps_info(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "cpf",
                "description": "Coleta e valida o CPF do usuário",
                "example": "12345678901",
                "required": True,
            },
            {
                "name": "email",
                "description": "Coleta e valida o e-mail do usuário",
                "example": "example@gmail.com",
                "required": True,
            },
            {
                "name": "name",
                "description": "Coleta e valida o nome completo do usuário",
                "example": "João da Silva",
                "required": True,
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

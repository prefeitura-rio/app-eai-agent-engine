import os
import json
from pathlib import Path
from src.services_v5.core.models import ServiceState

from typing import Any, Dict, Optional


class StateManager:
    """
    Gerenciador de estado responsável por salvar, carregar, atualizar e remover dados.
    Dados são armazenados na pasta data com estrutura user_id.json {service_name: {...}}
    """

    def __init__(self, data_dir: str = "src/services_v5/data"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(exist_ok=True)

    def _get_user_file_path(self, user_id: str) -> Path:
        """Retorna o caminho do arquivo JSON do usuário."""
        return self.data_dir / f"{user_id}.json"

    def _load_user_data(self, user_id: str) -> Dict[str, Any]:
        """Carrega todos os dados de um usuário."""
        file_path = self._get_user_file_path(user_id)
        if file_path.exists():
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def _save_user_data(self, user_id: str, data: Dict[str, Any]) -> None:
        """Salva todos os dados de um usuário."""
        file_path = self._get_user_file_path(user_id)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load_service_state(
        self, user_id: str, service_name: str
    ) -> Optional[ServiceState]:
        """Carrega o estado de um serviço específico."""
        user_data = self._load_user_data(user_id)
        service_data = user_data.get(service_name)

        if service_data:
            return ServiceState(
                user_id=user_id, service_name=service_name, **service_data
            )
        return None

    def save_service_state(self, state: ServiceState) -> None:
        """Salva o estado de um serviço."""
        user_data = self._load_user_data(state.user_id)

        # Atualiza apenas os dados do serviço específico
        user_data[state.service_name] = {"status": state.status, "data": state.data}

        self._save_user_data(state.user_id, user_data)

    def update_service_state(
        self, user_id: str, service_name: str, updates: Dict[str, Any]
    ) -> None:
        """Atualiza campos específicos do estado de um serviço."""
        state = self.load_service_state(user_id, service_name)

        if state is None:
            # Criar novo estado se não existir
            state = ServiceState(user_id=user_id, service_name=service_name)

        # Aplicar atualizações
        for key, value in updates.items():
            if hasattr(state, key):
                setattr(state, key, value)

        self.save_service_state(state)

    def remove_service_state(self, user_id: str, service_name: str) -> bool:
        """Remove o estado de um serviço específico."""
        user_data = self._load_user_data(user_id)

        if service_name in user_data:
            del user_data[service_name]
            self._save_user_data(user_id, user_data)
            return True
        return False

    def remove_user_data(self, user_id: str) -> bool:
        """Remove todos os dados de um usuário."""
        file_path = self._get_user_file_path(user_id)
        if file_path.exists():
            os.remove(file_path)
            return True
        return False

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

    def __init__(self, data_dir: str = "src/services_v5/data", user_id: str = "agent"):
        """
        Inicializa o StateManager.

        Args:
            data_dir: Diretório base para arquivos de estado
            user_id: ID do usuário
        """
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(exist_ok=True)
        self.user_id = user_id
        self.file_path = self.data_dir / f"{user_id}.json"

    def _get_user_file_path(self) -> Path:
        """Retorna o caminho do arquivo JSON do usuário."""
        return self.file_path

    def _load_user_data(self) -> Dict[str, Any]:
        """Carrega todos os dados do usuário."""
        if self.file_path.exists():
            with open(self.file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def _save_user_data(self, data: Dict[str, Any]) -> None:
        """Salva todos os dados do usuário."""
        with open(self.file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load_service_state(self, service_name: str) -> Optional[ServiceState]:
        """Carrega o estado de um serviço específico."""
        user_data = self._load_user_data()
        service_data = user_data.get(service_name)

        if service_data:
            return ServiceState(
                user_id=self.user_id, service_name=service_name, **service_data
            )
        return None

    def save_service_state(self, state: ServiceState) -> None:
        """Salva o estado de um serviço."""
        user_data = self._load_user_data()

        # Atualiza apenas os dados do serviço específico
        user_data[state.service_name] = {"status": state.status, "data": state.data}

        self._save_user_data(user_data)

    def update_service_state(self, service_name: str, updates: Dict[str, Any]) -> None:
        """Atualiza campos específicos do estado de um serviço."""
        state = self.load_service_state(service_name)

        if state is None:
            # Criar novo estado se não existir
            state = ServiceState(user_id=self.user_id, service_name=service_name)

        # Aplicar atualizações
        for key, value in updates.items():
            if hasattr(state, key):
                setattr(state, key, value)

        self.save_service_state(state)

    def remove_service_state(self, service_name: str) -> bool:
        """Remove o estado de um serviço específico."""
        user_data = self._load_user_data()

        if service_name in user_data:
            del user_data[service_name]
            self._save_user_data(user_data)
            return True
        return False

    def remove_user_data(self) -> bool:
        """Remove todos os dados do usuário."""
        if self.file_path.exists():
            os.remove(self.file_path)
            return True
        return False

import os
import json
from pathlib import Path
from enum import Enum
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from src.services.core.models import ServiceState, ServiceMetadata
from src.config.env import REDIS_URL

try:
    import redis
except ImportError:
    redis = None


class StateMode(Enum):
    """Modos de persistência disponíveis."""

    JSON = "json"
    REDIS = "redis"
    BOTH = "both"


class StorageBackend(ABC):
    """Interface abstrata para backends de persistência."""

    @abstractmethod
    def load_user_data(self, user_id: str) -> Dict[str, Any]:
        """Carrega todos os dados de um usuário."""
        pass

    @abstractmethod
    def save_user_data(self, user_id: str, data: Dict[str, Any]) -> None:
        """Salva todos os dados de um usuário."""
        pass

    @abstractmethod
    def remove_user_data(self, user_id: str) -> bool:
        """Remove todos os dados de um usuário."""
        pass

    @abstractmethod
    def health_check(self) -> bool:
        """Verifica se o backend está acessível."""
        pass


class JsonBackend(StorageBackend):
    """
    Backend de persistência usando arquivos JSON locais.
    Armazena em: {data_dir}/{user_id}.json
    """

    def __init__(self, data_dir: str = "src/services/data"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(exist_ok=True)

    def _get_file_path(self, user_id: str) -> Path:
        return self.data_dir / f"{user_id}.json"

    def load_user_data(self, user_id: str) -> Dict[str, Any]:
        file_path = self._get_file_path(user_id)
        if file_path.exists():
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def save_user_data(self, user_id: str, data: Dict[str, Any]) -> None:
        file_path = self._get_file_path(user_id)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def remove_user_data(self, user_id: str) -> bool:
        file_path = self._get_file_path(user_id)
        if file_path.exists():
            os.remove(file_path)
            return True
        return False

    def health_check(self) -> bool:
        try:
            return self.data_dir.exists() and os.access(self.data_dir, os.W_OK)
        except Exception:
            return False


class RedisBackend(StorageBackend):
    """
    Backend de persistência usando Redis.
    Suporta URLs no formato: redis://:password@host:port/db
    Chaves: user:{user_id}
    """

    def __init__(self, redis_url: str):
        """
        Inicializa backend Redis a partir de uma URL.

        Args:
            redis_url: URL no formato redis://:password@host:port/db
                      Exemplos:
                      - redis://localhost:6379/0
                      - redis://:mypassword@localhost:6379/0
                      - redis://host:6379

        Raises:
            ImportError: Se biblioteca redis não estiver instalada
            redis.ConnectionError: Se não conseguir conectar
        """
        if redis is None:
            raise ImportError(
                "Biblioteca 'redis' não instalada. Instale com: uv add redis"
            )

        # Usa from_url do redis que já faz todo o parsing
        self.client = redis.Redis.from_url(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
        )

        # Testa conexão
        if not self.health_check():
            raise redis.ConnectionError(f"Não foi possível conectar ao Redis")

    def _get_key(self, user_id: str) -> str:
        return user_id

    def load_user_data(self, user_id: str) -> Dict[str, Any]:
        key = self._get_key(user_id)
        data = self.client.get(key)  # type: ignore[arg-type]
        if data:
            return json.loads(data)  # type: ignore[arg-type]
        return {}

    def save_user_data(self, user_id: str, data: Dict[str, Any]) -> None:
        key = self._get_key(user_id)
        serialized = json.dumps(data, ensure_ascii=False)
        self.client.set(key, serialized)

    def remove_user_data(self, user_id: str) -> bool:
        key = self._get_key(user_id)
        deleted = self.client.delete(key)
        return deleted > 0  # type: ignore[operator]

    def health_check(self) -> bool:
        try:
            result = self.client.ping()  # type: ignore[misc]
            return bool(result)
        except Exception:
            return False


class CompositeBackend(StorageBackend):
    """
    Backend composto que usa múltiplos backends simultaneamente.

    Estratégia:
    - Leitura: Tenta Redis primeiro, fallback para JSON
    - Escrita: Salva em ambos
    - Remoção: Remove de ambos
    """

    def __init__(self, redis_backend: RedisBackend, json_backend: JsonBackend):
        self.redis = redis_backend
        self.json = json_backend

    def load_user_data(self, user_id: str) -> Dict[str, Any]:
        # Tenta Redis primeiro (mais rápido)
        try:
            if self.redis.health_check():
                data = self.redis.load_user_data(user_id)
                if data:
                    return data
        except Exception:
            pass

        # Fallback para JSON
        return self.json.load_user_data(user_id)

    def save_user_data(self, user_id: str, data: Dict[str, Any]) -> None:
        # Salva em ambos
        errors = []

        try:
            self.json.save_user_data(user_id, data)
        except Exception as e:
            errors.append(f"JSON: {e}")

        try:
            self.redis.save_user_data(user_id, data)
        except Exception as e:
            errors.append(f"Redis: {e}")

        # Se ambos falharam, levanta erro
        if len(errors) == 2:
            raise Exception(f"Falha ao salvar em ambos backends: {', '.join(errors)}")

    def remove_user_data(self, user_id: str) -> bool:
        json_removed = False
        redis_removed = False

        try:
            json_removed = self.json.remove_user_data(user_id)
        except Exception:
            pass

        try:
            redis_removed = self.redis.remove_user_data(user_id)
        except Exception:
            pass

        return json_removed or redis_removed

    def health_check(self) -> bool:
        # Pelo menos um deve estar saudável
        return self.json.health_check() or self.redis.health_check()


class StateManager:
    """
    Gerenciador de estado responsável por salvar, carregar, atualizar e remover dados.

    Suporta três modos de persistência:
    - JSON: Apenas arquivos locais (padrão)
    - REDIS: Apenas Redis
    - BOTH: Redis + JSON simultaneamente

    O modo é configurado no construtor via parâmetro backend_mode.
    """

    def __init__(
        self,
        user_id: str = "agent",
        data_dir: str = "src/services/data",
        backend_mode: StateMode = StateMode.JSON,
        redis_url: Optional[str] = None,
    ):
        """
        Inicializa o StateManager.

        Args:
            user_id: ID do usuário
            data_dir: Diretório para arquivos JSON (usado em JSON e BOTH)
            backend_mode: Modo de persistência (JSON, REDIS, BOTH)
            redis_url: URL Redis no formato redis://:password@host:port/db
                      Se None, usa REDIS_URL da env (apenas para REDIS/BOTH)

        Raises:
            ValueError: Se backend_mode for REDIS/BOTH e redis_url não fornecido
        """
        self.user_id = user_id
        self.backend_mode = backend_mode
        self.backend = self._create_backend(data_dir, backend_mode, redis_url)

    def _create_backend(
        self,
        data_dir: str,
        mode: StateMode,
        redis_url: Optional[str],
    ) -> StorageBackend:
        """Cria o backend apropriado baseado no modo."""

        if mode == StateMode.JSON:
            return JsonBackend(data_dir=data_dir)

        elif mode == StateMode.REDIS:
            url = redis_url or REDIS_URL
            if not url:
                raise ValueError(
                    "StateMode.REDIS requer redis_url ou REDIS_URL configurado"
                )
            return RedisBackend(redis_url=url)

        elif mode == StateMode.BOTH:
            url = redis_url or REDIS_URL
            if not url:
                raise ValueError(
                    "StateMode.BOTH requer redis_url ou REDIS_URL configurado"
                )
            json_backend = JsonBackend(data_dir=data_dir)
            redis_backend = RedisBackend(redis_url=url)
            return CompositeBackend(redis_backend, json_backend)

        else:
            raise ValueError(f"StateMode inválido: {mode}")

    def _load_user_data(self) -> Dict[str, Any]:
        """Carrega todos os dados do usuário usando o backend configurado."""
        return self.backend.load_user_data(self.user_id)

    def _save_user_data(self, data: Dict[str, Any]) -> None:
        """Salva todos os dados do usuário usando o backend configurado."""
        self.backend.save_user_data(self.user_id, data)

    def load_service_state(self, service_name: str) -> Optional[ServiceState]:
        """Carrega o estado de um serviço específico."""
        user_data = self._load_user_data()
        service_data = user_data.get(service_name)

        if service_data:
            # Compatibilidade: Se não tem metadata, cria um novo
            if "metadata" not in service_data:
                service_data["metadata"] = ServiceMetadata().model_dump()

            return ServiceState(
                user_id=self.user_id, service_name=service_name, **service_data
            )
        return None

    def save_service_state(self, state: ServiceState) -> None:
        """Salva o estado de um serviço."""
        # Auto-atualiza o timestamp de updated_at antes de salvar
        state.metadata.update_timestamp()

        user_data = self._load_user_data()

        # Atualiza apenas os dados do serviço específico
        user_data[state.service_name] = {
            "status": state.status,
            "data": state.data,
            "internal": state.internal,
            "metadata": state.metadata.model_dump(mode="json"),
        }

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
        """Remove todos os dados do usuário usando o backend configurado."""
        return self.backend.remove_user_data(self.user_id)

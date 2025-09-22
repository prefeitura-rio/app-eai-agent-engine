import json
import os
import uuid
from datetime import datetime
from typing import Any, Dict


class ServiceState:
    """
    Manages the state of a service execution for a specific user.

    Handles loading, saving, and accessing nested data using dot notation.
    The state is persisted as a JSON file in the `data` directory.
    """

    def __init__(self, user_id: str, data_dir: str = "src/services/data"):
        self.user_id = user_id
        self.data_dir = data_dir
        self.file_path = os.path.join(self.data_dir, f"{self.user_id}.json")
        self._state: Dict[str, Any] = self._load()

    def _load(self) -> Dict[str, Any]:
        """Loads the state from a JSON file if it exists."""
        if os.path.exists(self.file_path):
            with open(self.file_path, "r") as f:
                return json.load(f)
        return {}

    def save(self):
        """Saves the current state to its JSON file."""
        # Update all service states' updated_at timestamp
        now = datetime.now().isoformat()
        for service_state in self._state.values():
            if isinstance(service_state, dict) and "_metadata" in service_state:
                service_state["_metadata"]["updated_at"] = now
        
        os.makedirs(self.data_dir, exist_ok=True)
        with open(self.file_path, "w") as f:
            json.dump(self._state, f, indent=4, ensure_ascii=False)

    def get_service_state(self, service_name: str) -> Dict[str, Any]:
        """Returns the state for a specific service, initializing if not present."""
        service_state = self._state.setdefault(service_name, {})
        
        # Initialize metadata if this is a new service state
        if not service_state:
            now = datetime.now().isoformat()
            service_id = f"{self.user_id}_{str(uuid.uuid4())[:6].replace('-', '_')}"
            
            service_state["_metadata"] = {
                "id": service_id,
                "created_at": now,
                "updated_at": now
            }
        
        return service_state

    def get(self, key: str, service_state: Dict[str, Any]) -> Any:
        """
        Retrieves a value from the service state using dot notation.

        Args:
            key: The dot-separated key (e.g., 'user.address.zip_code').
            service_state: The specific service state dictionary to query.

        Returns:
            The value if found, otherwise None.
        """
        keys = key.split(".")
        value = service_state
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return None
        return value

    def set(self, key: str, value: Any, service_state: Dict[str, Any]):
        """
        Sets a value in the service state using dot notation, creating nested dicts as needed.
        """
        keys = key.split('.')
        current_level = service_state
        for k in keys[:-1]:
            # If the current level is not a dict, we need to replace it with a dict
            if not isinstance(current_level, dict):
                # This should not happen in normal usage, but let's handle it gracefully
                raise ValueError(f"Cannot navigate through non-dict value at key '{k}'")
            
            # If the key exists and is not a dict, replace it with a dict
            if k in current_level and not isinstance(current_level[k], dict):
                current_level[k] = {}
            
            current_level = current_level.setdefault(k, {})
        
        # Handle the case where the final key might represent a merge
        final_key = keys[-1]
        if (isinstance(current_level, dict) and 
            isinstance(current_level.get(final_key), dict) and 
            isinstance(value, dict)):
            current_level[final_key].update(value)
        else:
            if isinstance(current_level, dict):
                current_level[final_key] = value
            else:
                raise ValueError(f"Cannot set key '{final_key}' on non-dict value")

    def merge_data(self, data: Dict[str, Any], service_state: Dict[str, Any]):
        """
        Deeply merges a dictionary into the service state.
        """
        for key, value in data.items():
            if (
                key in service_state
                and isinstance(service_state[key], dict)
                and isinstance(value, dict)
            ):
                self._deep_merge(service_state[key], value)
            else:
                service_state[key] = value

    def _deep_merge(self, target: Dict, source: Dict):
        """Helper for recursively merging dictionaries."""
        for key, value in source.items():
            if (
                key in target
                and isinstance(target[key], dict)
                and isinstance(value, dict)
            ):
                self._deep_merge(target[key], value)
            else:
                target[key] = value

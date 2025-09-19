"""
Service state management module.
Handles persistence and loading of service states.
"""

import json
from pathlib import Path
from typing import Optional, Dict, Type
from datetime import datetime

from src.services.base_service import BaseService


# State management configuration
STATE_DIR = Path("service_states")
STATE_DIR.mkdir(exist_ok=True)


def save_service_state(service: BaseService, service_name: str, user_id: str) -> None:
    """
    Save service state to file.
    
    Args:
        service: Service instance to save
        service_name: Name of the service
        user_id: User identifier
    """
    state_file = STATE_DIR / f"{user_id}__{service_name}.json"
    state_data = {
        "service_class": service.__class__.__name__,
        "service_name": service_name,
        "user_id": user_id,
        "data": service.data,
        "created_at": service.created_at.isoformat(),
        "last_updated": datetime.now().isoformat(),
    }
    
    with open(state_file, "w") as f:
        json.dump(state_data, f, indent=2, ensure_ascii=False)


def load_service_state(service_name: str, user_id: str, service_registry: Dict[str, Type[BaseService]]) -> Optional[BaseService]:
    """
    Load service state from file.
    
    Args:
        service_name: Name of the service
        user_id: User identifier
        service_registry: Registry of available service classes
        
    Returns:
        Service instance with loaded state or None if not found
    """
    state_file = STATE_DIR / f"{user_id}__{service_name}.json"
    if not state_file.exists():
        return None

    try:
        with open(state_file, "r") as f:
            state_data = json.load(f)

        # Find service class by name
        service_class_name = state_data["service_class"]
        service_class = None
        
        for name, cls in service_registry.items():
            if cls.__name__ == service_class_name:
                service_class = cls
                break

        if not service_class:
            return None

        # Recreate service instance with loaded data
        service = service_class(user_id)
        service.data = state_data["data"]
        
        # Restore created_at if available
        if "created_at" in state_data:
            try:
                service.created_at = datetime.fromisoformat(state_data["created_at"])
            except (ValueError, TypeError):
                pass  # Keep current datetime if parsing fails
        
        return service

    except (json.JSONDecodeError, KeyError, TypeError):
        return None


def get_or_create_service(service_name: str, user_id: str, service_registry: Dict[str, Type[BaseService]]) -> Optional[BaseService]:
    """
    Get existing service or create new one.
    
    Args:
        service_name: Name of the service
        user_id: User identifier  
        service_registry: Registry of available service classes
        
    Returns:
        Service instance (loaded or new) or None if service not found
    """
    # Try to load existing state
    service = load_service_state(service_name, user_id, service_registry)
    if service:
        return service

    # Create new service
    service_class = service_registry.get(service_name)
    if service_class:
        return service_class(user_id)

    return None


def delete_service_state(service_name: str, user_id: str) -> bool:
    """
    Delete service state file.
    
    Args:
        service_name: Name of the service
        user_id: User identifier
        
    Returns:
        True if file was deleted, False if file didn't exist
    """
    state_file = STATE_DIR / f"{user_id}__{service_name}.json"
    if state_file.exists():
        state_file.unlink()
        return True
    return False


def list_user_services(user_id: str) -> Dict[str, Dict]:
    """
    List all services for a specific user.
    
    Args:
        user_id: User identifier
        
    Returns:
        Dict mapping service names to their metadata
    """
    user_services = {}
    prefix = f"{user_id}__"
    
    for state_file in STATE_DIR.glob(f"{prefix}*.json"):
        try:
            with open(state_file, "r") as f:
                state_data = json.load(f)
            
            service_name = state_data.get("service_name")
            if service_name:
                user_services[service_name] = {
                    "created_at": state_data.get("created_at"),
                    "last_updated": state_data.get("last_updated"),
                    "service_class": state_data.get("service_class"),
                    "data_keys": list(state_data.get("data", {}).keys())
                }
        except (json.JSONDecodeError, KeyError):
            continue
    
    return user_services


def cleanup_expired_states(max_age_days: int = 30) -> int:
    """
    Clean up expired service states.
    
    Args:
        max_age_days: Maximum age in days before considering a state expired
        
    Returns:
        Number of files cleaned up
    """
    from datetime import timedelta
    
    cutoff_date = datetime.now() - timedelta(days=max_age_days)
    cleaned_count = 0
    
    for state_file in STATE_DIR.glob("*.json"):
        try:
            # Check file modification time
            file_mtime = datetime.fromtimestamp(state_file.stat().st_mtime)
            
            if file_mtime < cutoff_date:
                state_file.unlink()
                cleaned_count += 1
                
        except (OSError, ValueError):
            continue
    
    return cleaned_count
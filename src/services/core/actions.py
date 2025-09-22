from typing import Callable, Dict

# Global registry for actions
_actions: Dict[str, Callable] = {}

def action(name: str) -> Callable:
    """
    A decorator to register a function as a service action.

    Args:
        name: The public name of the action, to be used in ServiceDefinitions.
    
    Example:
        @action("search_debts")
        def search_user_debts(state):
            # ... logic ...
            return ExecutionResult(...)
    """
    def decorator(func: Callable) -> Callable:
        if name in _actions:
            # In a real-world scenario, you might want to log a warning here.
            pass
        _actions[name] = func
        return func
    return decorator

def get_action(name: str) -> Callable:
    """
    Retrieves a registered action function by its name.

    Args:
        name: The name of the action to retrieve.

    Returns:
        The callable function associated with the name.

    Raises:
        KeyError: If no action with the given name is registered.
    """
    if name not in _actions:
        raise KeyError(f"Action '{name}' not found in registry. Available actions: {list(_actions.keys())}")
    return _actions[name]

def get_all_actions() -> Dict[str, Callable]:
    """Returns a copy of the actions registry."""
    return _actions.copy()

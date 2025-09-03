"""
User Identification Workflow - Collect and validate user information (CPF, email, name).

This workflow handles the step-by-step process of identifying a user:
1. Collect CPF
2. Validate CPF  
3. Collect email
4. Validate email
5. Check if email is registered (if yes, get name; if no, collect name)
6. Collect name (if needed)
7. Validate name (if collected)
8. Return user data

The user can exit at any point and return to the main agent.
"""

import re
from typing import Dict, Any, Optional
from dataclasses import dataclass
from langgraph.func import entrypoint, task
from langgraph.types import Command, interrupt
from langgraph.checkpoint.memory import InMemorySaver


@dataclass
class UserData:
    """Data structure for user information."""
    cpf: Optional[str] = None
    email: Optional[str] = None
    name: Optional[str] = None
    is_registered: bool = False
    exit_requested: bool = False


def validate_cpf(cpf: str) -> bool:
    """
    Validate CPF format and check digit.
    
    Args:
        cpf: CPF string to validate
        
    Returns:
        bool: True if CPF is valid, False otherwise
    """
    # Remove non-digits
    cpf = re.sub(r'\D', '', cpf)
    
    # Check if has 11 digits
    if len(cpf) != 11:
        return False
    
    # Check if all digits are the same (invalid CPFs)
    if cpf == cpf[0] * 11:
        return False
    
    # Validate check digits
    def calculate_digit(cpf_partial):
        total = 0
        for i, digit in enumerate(cpf_partial):
            total += int(digit) * (len(cpf_partial) + 1 - i)
        remainder = total % 11
        return '0' if remainder < 2 else str(11 - remainder)
    
    # Check first digit
    if cpf[9] != calculate_digit(cpf[:9]):
        return False
    
    # Check second digit
    if cpf[10] != calculate_digit(cpf[:10]):
        return False
    
    return True


def validate_email(email: str) -> bool:
    """
    Validate email format.
    
    Args:
        email: Email string to validate
        
    Returns:
        bool: True if email is valid, False otherwise
    """
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))


def validate_name(name: str) -> bool:
    """
    Validate name format - should have name and surname, both with more than 2 letters.
    
    Args:
        name: Full name string to validate
        
    Returns:
        bool: True if name is valid, False otherwise
    """
    name = name.strip()
    
    # Split into parts
    name_parts = name.split()
    
    # Should have at least 2 parts (name and surname)
    if len(name_parts) < 2:
        return False
    
    # Each part should have more than 2 letters
    for part in name_parts:
        if len(part) <= 2 or not part.isalpha():
            return False
    
    return True


def check_email_registered(email: str) -> Optional[str]:
    """
    Check if email is registered and return the associated name.
    
    Args:
        email: Email to check
        
    Returns:
        Optional[str]: User name if registered, None if not registered
    """
    # TODO: Implement actual database lookup
    # For now, simulate with some test data
    registered_users = {
        "joao.silva@email.com": "João Silva Santos",
        "maria.santos@email.com": "Maria Santos Oliveira",
        "pedro.oliveira@email.com": "Pedro Oliveira Costa"
    }
    
    return registered_users.get(email.lower())


def check_exit_request(user_input: str) -> bool:
    """
    Check if user wants to exit the identification process.
    
    Args:
        user_input: User's input string
        
    Returns:
        bool: True if user wants to exit, False otherwise
    """
    exit_keywords = [
        "sair", "cancelar", "voltar", "desistir", "parar", "exit", 
        "cancel", "back", "quit", "stop", "não quero", "nao quero"
    ]
    
    user_input_lower = user_input.lower().strip()
    return any(keyword in user_input_lower for keyword in exit_keywords)


@task
def collect_cpf(user_data: UserData) -> Dict[str, Any]:
    """
    Collect CPF from user.
    
    Args:
        user_data: Current user data
        
    Returns:
        Dict containing next step and user input
    """
    # Interrupt to ask for CPF
    user_input = interrupt(
        "Para continuar, preciso do seu CPF. Por favor, digite seu CPF (apenas números) ou 'sair' para cancelar:"
    )
    
    # Check if user wants to exit
    if check_exit_request(user_input):
        user_data.exit_requested = True
        return {"action": "exit", "user_data": user_data}
    
    # Store CPF (will be validated in next step)
    user_data.cpf = user_input.strip()
    return {"action": "validate_cpf", "user_data": user_data}


@task  
def validate_cpf_task(user_data: UserData) -> Dict[str, Any]:
    """
    Validate the collected CPF.
    
    Args:
        user_data: Current user data with CPF
        
    Returns:
        Dict containing validation result and next action
    """
    if not user_data.cpf or not validate_cpf(user_data.cpf):
        # Invalid CPF, ask again
        user_input = interrupt(
            "CPF inválido. Por favor, digite um CPF válido (11 dígitos) ou 'sair' para cancelar:"
        )
        
        if check_exit_request(user_input):
            user_data.exit_requested = True
            return {"action": "exit", "user_data": user_data}
        
        user_data.cpf = user_input.strip()
        return {"action": "validate_cpf", "user_data": user_data}
    
    # CPF is valid, proceed to email collection
    return {"action": "collect_email", "user_data": user_data}


@task
def collect_email(user_data: UserData) -> Dict[str, Any]:
    """
    Collect email from user.
    
    Args:
        user_data: Current user data
        
    Returns:
        Dict containing next step and user input
    """
    user_input = interrupt(
        "Agora preciso do seu e-mail. Por favor, digite seu e-mail ou 'sair' para cancelar:"
    )
    
    if check_exit_request(user_input):
        user_data.exit_requested = True
        return {"action": "exit", "user_data": user_data}
    
    user_data.email = user_input.strip()
    return {"action": "validate_email", "user_data": user_data}


@task
def validate_email_task(user_data: UserData) -> Dict[str, Any]:
    """
    Validate the collected email.
    
    Args:
        user_data: Current user data with email
        
    Returns:
        Dict containing validation result and next action
    """
    if not user_data.email or not validate_email(user_data.email):
        user_input = interrupt(
            "E-mail inválido. Por favor, digite um e-mail válido ou 'sair' para cancelar:"
        )
        
        if check_exit_request(user_input):
            user_data.exit_requested = True
            return {"action": "exit", "user_data": user_data}
        
        user_data.email = user_input.strip()
        return {"action": "validate_email", "user_data": user_data}
    
    # Email is valid, check if registered
    return {"action": "check_email_registered", "user_data": user_data}


@task
def check_email_registered_task(user_data: UserData) -> Dict[str, Any]:
    """
    Check if email is registered and get associated name.
    
    Args:
        user_data: Current user data with validated email
        
    Returns:
        Dict containing registration status and next action
    """
    registered_name = check_email_registered(user_data.email)
    
    if registered_name:
        # Email is registered, we have the name
        user_data.name = registered_name
        user_data.is_registered = True
        return {"action": "end_flow", "user_data": user_data}
    else:
        # Email not registered, need to collect name
        return {"action": "collect_name", "user_data": user_data}


@task
def collect_name(user_data: UserData) -> Dict[str, Any]:
    """
    Collect full name from user.
    
    Args:
        user_data: Current user data
        
    Returns:
        Dict containing next step and user input
    """
    user_input = interrupt(
        "Este e-mail não está cadastrado. Por favor, digite seu nome completo ou 'sair' para cancelar:"
    )
    
    if check_exit_request(user_input):
        user_data.exit_requested = True
        return {"action": "exit", "user_data": user_data}
    
    user_data.name = user_input.strip()
    return {"action": "validate_name", "user_data": user_data}


@task
def validate_name_task(user_data: UserData) -> Dict[str, Any]:
    """
    Validate the collected name.
    
    Args:
        user_data: Current user data with name
        
    Returns:
        Dict containing validation result and next action
    """
    if not user_data.name or not validate_name(user_data.name):
        user_input = interrupt(
            "Nome inválido. Por favor, digite seu nome completo (nome e sobrenome, cada um com mais de 2 letras) ou 'sair' para cancelar:"
        )
        
        if check_exit_request(user_input):
            user_data.exit_requested = True
            return {"action": "exit", "user_data": user_data}
        
        user_data.name = user_input.strip()
        return {"action": "validate_name", "user_data": user_data}
    
    # Name is valid, finish identification
    return {"action": "end_flow", "user_data": user_data}


@entrypoint(checkpointer=InMemorySaver())
def user_identification_workflow(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """
    Main user identification workflow.
    
    This workflow collects and validates user identification information:
    - CPF (Brazilian taxpayer ID)
    - Email address  
    - Full name (if email not registered)
    
    The workflow can be exited at any point by the user.
    
    Args:
        inputs: Dictionary with initial parameters (can be empty)
        
    Returns:
        Dict containing:
        - success: bool indicating if identification completed
        - user_data: UserData object with collected information
        - exit_reason: str explaining why workflow ended
    """
    # Initialize user data
    user_data = UserData()
    
    # Start workflow
    current_action = "collect_cpf"
    
    while current_action != "end_flow" and not user_data.exit_requested:
        if current_action == "collect_cpf":
            result = collect_cpf(user_data)
        elif current_action == "validate_cpf":
            result = validate_cpf_task(user_data)
        elif current_action == "collect_email":
            result = collect_email(user_data)
        elif current_action == "validate_email":
            result = validate_email_task(user_data)
        elif current_action == "check_email_registered":
            result = check_email_registered_task(user_data)
        elif current_action == "collect_name":
            result = collect_name(user_data)
        elif current_action == "validate_name":
            result = validate_name_task(user_data)
        else:
            # Unknown action, exit with error
            break
        
        # Update user data and next action
        user_data = result["user_data"]
        current_action = result["action"]
        
        # Handle exit requests
        if current_action == "exit" or user_data.exit_requested:
            return {
                "success": False,
                "user_data": {
                    "cpf": user_data.cpf,
                    "email": user_data.email,
                    "name": user_data.name,
                    "is_registered": user_data.is_registered
                },
                "exit_reason": "User requested to exit identification process"
            }
    
    # Workflow completed successfully
    return {
        "success": True,
        "user_data": {
            "cpf": user_data.cpf,
            "email": user_data.email,
            "name": user_data.name,
            "is_registered": user_data.is_registered
        },
        "exit_reason": "Identification completed successfully"
    }

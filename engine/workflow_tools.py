"""
Workflow tools for the main agent to call specialized workflows.
"""

from typing import Dict, Any
from langchain_core.tools import tool


@tool(description="Start user identification process to collect and validate CPF, email, and name. Use when user needs to be identified for a service.")
def start_user_identification(reason: str = "Para continuar com este serviço") -> Dict[str, Any]:
    """
    Start the user identification workflow.
    
    This tool initiates a step-by-step process to collect and validate:
    - CPF (Brazilian taxpayer ID)
    - Email address
    - Full name (if email not registered)
    
    The user can exit at any point during the process.
    
    Args:
        reason: Why the identification is needed (e.g., "Para gerar a segunda via do IPTU")
        
    Returns:
        Dict containing the workflow result and user data
    """
    try:
        # For now, return a structured response that tells the agent
        # what information needs to be collected
        return {
            "status": "workflow_started",
            "message": f"""Iniciando processo de identificação. {reason}

Para continuar, preciso coletar as seguintes informações:

1. **CPF**: Seu Cadastro de Pessoa Física (formato: xxx.xxx.xxx-xx)
2. **Email**: Seu endereço de email para contato
3. **Nome completo**: Caso o email não esteja cadastrado

Posso começar coletando seu CPF? Por favor, digite seu CPF:""",
            "next_step": "collect_cpf",
            "required_fields": ["cpf", "email", "name"],
            "reason": reason
        }
            
    except Exception as e:
        return {
            "status": "error",
            "message": f"Erro ao iniciar identificação: {str(e)}"
        }


@tool(description="Process user identification data collected through conversation. Use after collecting CPF, email, and/or name from user.")
def process_user_identification(cpf: str = "", email: str = "", name: str = "") -> Dict[str, Any]:
    """
    Process collected user identification data.
    
    Args:
        cpf: User's CPF (Brazilian taxpayer ID)
        email: User's email address
        name: User's full name
        
    Returns:
        Dict containing validation results and next steps
    """
    try:
        from engine.workflows.user_identification import validate_cpf, validate_email, validate_name
        
        result = {
            "status": "processing",
            "validation_results": {},
            "valid_data": {},
            "errors": [],
            "next_steps": []
        }
        
        # Validate CPF if provided
        if cpf:
            cpf_valid = validate_cpf(cpf)
            result["validation_results"]["cpf"] = cpf_valid
            if cpf_valid:
                # Format CPF properly
                cpf_clean = ''.join(filter(str.isdigit, cpf))
                formatted_cpf = f"{cpf_clean[:3]}.{cpf_clean[3:6]}.{cpf_clean[6:9]}-{cpf_clean[9:]}"
                result["valid_data"]["cpf"] = formatted_cpf
            else:
                result["errors"].append("CPF inválido. Por favor, forneça um CPF válido no formato xxx.xxx.xxx-xx")
        else:
            result["next_steps"].append("Colete o CPF do usuário")
        
        # Validate email if provided
        if email:
            email_valid = validate_email(email)
            result["validation_results"]["email"] = email_valid
            if email_valid:
                result["valid_data"]["email"] = email.lower()
            else:
                result["errors"].append("Email inválido. Por favor, forneça um email válido")
        else:
            result["next_steps"].append("Colete o email do usuário")
        
        # Validate name if provided
        if name:
            name_valid = validate_name(name)
            result["validation_results"]["name"] = name_valid
            if name_valid:
                result["valid_data"]["name"] = name.title()
            else:
                result["errors"].append("Nome inválido. Por favor, forneça nome e sobrenome")
        
        # Check if identification is complete
        if result["valid_data"].get("cpf") and result["valid_data"].get("email"):
            if result["valid_data"].get("name"):
                result["status"] = "complete"
                result["message"] = f"Identificação concluída com sucesso para {result['valid_data']['name']}"
            else:
                result["next_steps"].append("Colete o nome completo do usuário")
        
        return result
            
    except Exception as e:
        return {
            "status": "error",
            "message": f"Erro ao processar identificação: {str(e)}"
        }


def get_workflow_tools():
    """
    Get all workflow tools available for the main agent.
    
    Returns:
        List of workflow tools
    """
    return [start_user_identification, process_user_identification]

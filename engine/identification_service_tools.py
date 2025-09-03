"""
Service agent tools for the main agent to call the identification service agent.
"""

from typing import Dict, Any
from langchain_core.tools import tool
from engine.services.identification_agent import create_identification_agent


# Global identification agent instance
_identification_agent = None
_shared_checkpointer = None


def set_shared_checkpointer(checkpointer):
    """Set the shared checkpointer for all identification agents."""
    global _shared_checkpointer
    _shared_checkpointer = checkpointer


def get_identification_agent():
    """Get or create the identification agent instance with shared checkpointer."""
    global _identification_agent
    if _identification_agent is None:
        _identification_agent = create_identification_agent(checkpointer=_shared_checkpointer)
    return _identification_agent


@tool(description="Route user identification requests to the specialized identification service agent. Use when user needs conversational help with identification.")
def route_to_identification_agent(user_message: str) -> Dict[str, Any]:
    """
    Route user identification request to the specialized identification service agent.
    
    This tool provides conversational user identification assistance using a specialized agent
    that can handle complex scenarios, validation, and edge cases through natural dialogue.
    
    Args:
        user_message: The user's message about identification needs
        
    Returns:
        Dict containing the agent's response and current state
    """
    try:
        import re
        from engine.workflows.user_identification import validate_cpf, validate_email, validate_name
        
        user_message_lower = user_message.lower()
        
        # Extract potential data from user message
        extracted_data = {
            "cpf": None,
            "email": None, 
            "name": None
        }
        
        # Look for CPF (11 digits)
        cpf_pattern = r'\b\d{11}\b|\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b'
        cpf_match = re.search(cpf_pattern, user_message)
        if cpf_match:
            cpf_candidate = re.sub(r'\D', '', cpf_match.group())
            if len(cpf_candidate) == 11:
                extracted_data["cpf"] = cpf_candidate
        
        # Look for email
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        email_match = re.search(email_pattern, user_message)
        if email_match:
            extracted_data["email"] = email_match.group()
        
        # Look for name (after "me chamo", "meu nome", "sou", etc.)
        name_patterns = [
            r'(?:me chamo|meu nome (?:é|eh)|sou|nome:)\s+([A-Za-z\s]+?)(?:\s+(?:e|cpf|email|@)|$)',
            r'(?:chamo|nome)\s+([A-Za-z\s]+?)(?:\s+(?:e|cpf|email|@)|$)'
        ]
        
        for pattern in name_patterns:
            name_match = re.search(pattern, user_message, re.IGNORECASE)
            if name_match:
                potential_name = name_match.group(1).strip()
                # Filter out common non-name words
                if not any(word in potential_name.lower() for word in ['cpf', 'email', 'telefone', 'numero']):
                    extracted_data["name"] = potential_name
                    break
        
        # Check if this is the initial identification request
        if any(word in user_message_lower for word in ["identificar", "identifica", "cpf", "dados"]) and not any(extracted_data.values()):
            return {
                "status": "agent_response",
                "agent_type": "identification_agent",
                "response": """Olá! Sou o Agente de Identificação e vou te ajudar com o processo de identificação.

Para identificar você no sistema, preciso de algumas informações:

1. **CPF**: Seu Cadastro de Pessoa Física (formato: xxx.xxx.xxx-xx)
2. **Email**: Seu endereço de email para contato
3. **Nome completo**: Nome e sobrenome

Você pode me dar todas as informações de uma vez ou uma por vez. Vamos começar?""",
                "cpf": None,
                "email": None,
                "name": None,
                "is_complete": False,
                "current_step": "collect_all",
                "validation_errors": []
            }
        
        # Process extracted data
        validation_results = {}
        valid_data = {}
        errors = []
        
        # Validate CPF if extracted
        if extracted_data["cpf"]:
            cpf_valid = validate_cpf(extracted_data["cpf"])
            validation_results["cpf"] = cpf_valid
            if cpf_valid:
                formatted_cpf = f"{extracted_data['cpf'][:3]}.{extracted_data['cpf'][3:6]}.{extracted_data['cpf'][6:9]}-{extracted_data['cpf'][9:]}"
                valid_data["cpf"] = formatted_cpf
            else:
                errors.append(f"CPF {extracted_data['cpf']} é inválido")
        
        # Validate email if extracted
        if extracted_data["email"]:
            email_valid = validate_email(extracted_data["email"])
            validation_results["email"] = email_valid
            if email_valid:
                valid_data["email"] = extracted_data["email"].lower()
            else:
                errors.append(f"Email {extracted_data['email']} é inválido")
        
        # Validate name if extracted
        if extracted_data["name"]:
            name_valid = validate_name(extracted_data["name"])
            validation_results["name"] = name_valid
            if name_valid:
                valid_data["name"] = extracted_data["name"].title()
            else:
                errors.append(f"Nome '{extracted_data['name']}' precisa ter nome e sobrenome")
        
        # Generate response based on what was collected
        if errors:
            error_msg = "Encontrei alguns problemas:\n" + "\n".join(f"• {error}" for error in errors)
            missing = []
            if not valid_data.get("cpf"):
                missing.append("CPF válido")
            if not valid_data.get("email"):
                missing.append("email válido")
            if not valid_data.get("name"):
                missing.append("nome completo")
            
            if missing:
                error_msg += f"\n\nPor favor, forneça: {', '.join(missing)}"
            
            return {
                "status": "agent_response",
                "agent_type": "identification_agent",
                "response": error_msg,
                "cpf": valid_data.get("cpf"),
                "email": valid_data.get("email"),
                "name": valid_data.get("name"),
                "is_complete": False,
                "current_step": "collect_missing",
                "validation_errors": errors
            }
        
        # Check if we have all required data
        if valid_data.get("cpf") and valid_data.get("email") and valid_data.get("name"):
            return {
                "status": "agent_response",
                "agent_type": "identification_agent",
                "response": f"""✅ Identificação concluída com sucesso!

📋 **Dados coletados:**
• **CPF:** {valid_data['cpf']}
• **Email:** {valid_data['email']}
• **Nome:** {valid_data['name']}

Agora você está identificado no sistema e pode acessar os serviços municipais. Como posso ajudar?""",
                "cpf": valid_data["cpf"],
                "email": valid_data["email"],
                "name": valid_data["name"],
                "is_complete": True,
                "current_step": "complete",
                "validation_errors": []
            }
        
        # Partial data collected - ask for missing pieces
        collected = []
        missing = []
        
        if valid_data.get("cpf"):
            collected.append(f"CPF: {valid_data['cpf']}")
        else:
            missing.append("CPF")
            
        if valid_data.get("email"):
            collected.append(f"Email: {valid_data['email']}")
        else:
            missing.append("email")
            
        if valid_data.get("name"):
            collected.append(f"Nome: {valid_data['name']}")
        else:
            missing.append("nome completo")
        
        response = "Obrigado pelas informações!\n\n"
        if collected:
            response += "✅ **Dados coletados:**\n" + "\n".join(f"• {item}" for item in collected) + "\n\n"
        
        if missing:
            response += f"📝 **Ainda preciso de:** {', '.join(missing)}\n\nPor favor, forneça as informações que faltam."
        
        return {
            "status": "agent_response", 
            "agent_type": "identification_agent",
            "response": response,
            "cpf": valid_data.get("cpf"),
            "email": valid_data.get("email"),
            "name": valid_data.get("name"),
            "is_complete": False,
            "current_step": "collect_missing",
            "validation_errors": []
        }
        
    except Exception as e:
        return {
            "status": "error",
            "message": f"Erro ao processar identificação: {str(e)}"
        }


def get_identification_service_tools():
    """
    Get all identification service agent tools.
    
    Returns:
        List of identification service tools
    """
    return [route_to_identification_agent]

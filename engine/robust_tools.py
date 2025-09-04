"""
Tools robustas para identificação de usuários com validação completa.
"""

from langchain.tools import tool
from typing import Annotated, Dict, Any
import json
from engine.robust_validation import (
    validate_cpf_simple, 
    validate_email_simple, 
    check_user_in_database, 
    update_user_in_database,
    format_cpf
)


@tool
def validate_and_check_user_cpf(
    cpf: Annotated[str, "CPF do usuário (pode conter pontuação)"]
) -> str:
    """
    Valida o CPF e verifica se o usuário está cadastrado na base de dados.
    
    Retorna informações sobre a validação e se o usuário já existe.
    """
    # Limpa o CPF
    cpf_clean = ''.join(c for c in cpf if c.isdigit())
    
    # Valida o CPF
    if not validate_cpf_simple(cpf):
        return json.dumps({
            "valid": False,
            "error": "CPF inválido. Verifique os dígitos verificadores ou formato.",
            "user_found": False
        })
    
    # Verifica se usuário existe na base
    user_data = check_user_in_database(cpf_clean)
    
    if user_data["found"]:
        return json.dumps({
            "valid": True,
            "user_found": True,
            "nome": user_data["nome"],
            "email": user_data["email"],
            "cpf_formatado": format_cpf(cpf_clean),
            "message": f"Usuário encontrado: {user_data['nome']}"
        })
    else:
        return json.dumps({
            "valid": True,
            "user_found": False,
            "cpf_formatado": format_cpf(cpf_clean),
            "message": "CPF válido, mas usuário não cadastrado. Será necessário coletar nome e email."
        })


@tool
def validate_user_email(
    email: Annotated[str, "Email do usuário"]
) -> str:
    """
    Valida o formato do email fornecido pelo usuário.
    """
    if validate_email_simple(email):
        return json.dumps({
            "valid": True,
            "email": email,
            "message": "Email válido"
        })
    else:
        return json.dumps({
            "valid": False,
            "error": "Email inválido. Verifique o formato (exemplo: usuario@dominio.com)",
            "message": "Por favor, forneça um email válido"
        })


@tool
def confirm_existing_user_email(
    cpf: Annotated[str, "CPF do usuário"],
    email_confirmation: Annotated[str, "Confirmação do email (sim/não)"],
    new_email: Annotated[str, "Novo email se o usuário quiser alterar"] = None
) -> str:
    """
    Confirma se o email cadastrado está correto ou atualiza com novo email.
    """
    cpf_clean = ''.join(c for c in cpf if c.isdigit())
    user_data = check_user_in_database(cpf_clean)
    
    if not user_data["found"]:
        return json.dumps({
            "error": "Usuário não encontrado na base de dados"
        })
    
    if email_confirmation.lower() in ['sim', 's', 'yes', 'y']:
        return json.dumps({
            "confirmed": True,
            "email": user_data["email"],
            "message": f"Email confirmado: {user_data['email']}"
        })
    else:
        # Usuário quer trocar o email
        if new_email and validate_email_simple(new_email):
            update_user_in_database(cpf_clean, email=new_email)
            return json.dumps({
                "confirmed": True,
                "email": new_email,
                "updated": True,
                "message": f"Email atualizado para: {new_email}"
            })
        else:
            return json.dumps({
                "confirmed": False,
                "error": "Novo email inválido ou não fornecido",
                "message": "Por favor, forneça um email válido para atualização"
            })


@tool
def register_new_user(
    cpf: Annotated[str, "CPF do usuário"],
    nome: Annotated[str, "Nome completo do usuário"],
    email: Annotated[str, "Email do usuário"]
) -> str:
    """
    Registra um novo usuário na base de dados após validações.
    """
    cpf_clean = ''.join(c for c in cpf if c.isdigit())
    
    # Validações
    if not validate_cpf_simple(cpf):
        return json.dumps({
            "success": False,
            "error": "CPF inválido"
        })
    
    if not validate_email_simple(email):
        return json.dumps({
            "success": False,
            "error": "Email inválido"
        })
    
    if not nome or len(nome.strip()) < 2:
        return json.dumps({
            "success": False,
            "error": "Nome deve ter pelo menos 2 caracteres"
        })
    
    # Registra o usuário
    update_user_in_database(cpf_clean, nome=nome.strip(), email=email.strip())
    
    return json.dumps({
        "success": True,
        "cpf": format_cpf(cpf_clean),
        "nome": nome.strip(),
        "email": email.strip(),
        "message": f"Usuário {nome.strip()} registrado com sucesso!"
    })


@tool
def get_user_summary(
    cpf: Annotated[str, "CPF do usuário"]
) -> str:
    """
    Retorna um resumo completo dos dados do usuário.
    """
    cpf_clean = ''.join(c for c in cpf if c.isdigit())
    user_data = check_user_in_database(cpf_clean)
    
    if user_data["found"]:
        return json.dumps({
            "found": True,
            "cpf": format_cpf(cpf_clean),
            "nome": user_data["nome"],
            "email": user_data["email"],
            "message": f"Dados do usuário: {user_data['nome']} ({user_data['email']})"
        })
    else:
        return json.dumps({
            "found": False,
            "cpf": format_cpf(cpf_clean),
            "message": "Usuário não encontrado na base de dados"
        })


# Lista de todas as tools robustas para identificação
robust_identification_tools = [
    validate_and_check_user_cpf,
    validate_user_email,
    confirm_existing_user_email,
    register_new_user,
    get_user_summary
]

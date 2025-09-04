"""
Funções de validação robustas para CPF/CNPJ e email.
"""

import re
from itertools import cycle
from typing import Dict, Any


# Base de dados simulada de usuários
USER_DATABASE = {
    "11144477735": {
        "nome": "Bruno Silva Santos",
        "email": "bruno.silva@email.com"
    },
    "12345678901": {
        "nome": "Maria Oliveira Costa", 
        "email": "maria.oliveira@gmail.com"
    },
    "98765432100": {
        "nome": "João Santos Lima",
        "email": "joao.santos@hotmail.com"
    },
    "11122233344": {
        "nome": "Ana Paula Ferreira",
        "email": "ana.ferreira@yahoo.com"
    }
}


def validate_CPF(request_data: dict, parameters: dict, form_parameters_list: list = []) -> bool:
    """Efetua a validação do CPF, tanto formatação quanto dígito verificadores.

    Parâmetros:
        cpf (str): CPF a ser validado

    Retorno:
        bool:
            - Falso, quando o CPF não possuir o formato 999.999.999-99;
            - Falso, quando o CPF não possuir 11 caracteres numéricos;
            - Falso, quando os dígitos verificadores forem inválidos;
            - Verdadeiro, caso contrário.

    Exemplos:

    >>> validate_CPF({'id': '123'}, {'usuario_cpf': '529.982.247-25'})
    True
    >>> validate_CPF({'id': '123'}, {'usuario_cpf': '52998224725'})
    False
    >>> validate_CPF({'id': '123'}, {'usuario_cpf': '111.111.111-11'})
    False
    """
    cpf = parameters.get("usuario_cpf") or parameters.get("cpf_cnpj")
    numbers = [int(digit) for digit in cpf if digit.isdigit()]

    if len(numbers) != 11 or len(set(numbers)) == 1:
        return False

    if not validate_CPF2(numbers):
        return False

    if parameters.get("usuario_cpf"):
        parameters["usuario_cpf"] = "".join([str(item) for item in numbers])

    return True


def validate_CPF2(numbers):
    # Validação do primeiro dígito verificador:
    sum_of_products = sum(a * b for a, b in zip(numbers[:9], range(10, 1, -1)))
    expected_digit = (sum_of_products * 10) % 11 % 10
    if numbers[9] != expected_digit:
        return False

    # Validação do segundo dígito verificador:
    sum_of_products = sum(a * b for a, b in zip(numbers[:10], range(11, 1, -1)))
    expected_digit = (sum_of_products * 10) % 11 % 10
    if numbers[10] != expected_digit:
        return False

    return True


def validate_CNPJ(cnpj: str) -> bool:
    LENGTH_CNPJ = 14
    if len(cnpj) != LENGTH_CNPJ:
        return False

    if cnpj in (c * LENGTH_CNPJ for c in "1234567890"):
        return False

    cnpj_r = cnpj[::-1]
    for i in range(2, 0, -1):
        cnpj_enum = zip(cycle(range(2, 10)), cnpj_r[i:])
        dv = sum(map(lambda x: int(x[1]) * x[0], cnpj_enum)) * 10 % 11
        if cnpj_r[(i - 1) : i] != str(dv % 10):  # noqa
            return False

    return True


def validate_cpf_cnpj(request_data: dict, parameters: dict, form_parameters_list: list = []) -> bool:
    """Efetua a validação de CPF ou CNPJ."""
    
    # Obtém apenas os números do documento, ignorando pontuações
    documento = parameters.get("usuario_cpf") or parameters.get("cpf_cnpj")
    numbers = [int(digit) for digit in documento if digit.isdigit()]
    
    # Verifica se o documento possui 11 ou 14 números
    if len(numbers) not in [11, 14] or len(set(numbers)) == 1:
        return False

    if len(numbers) == 11:  # CPF
        print(f"[LOG] É um CPF: {''.join(map(str, numbers))}")
        return validate_CPF(request_data, parameters)

    elif len(numbers) == 14:  # CNPJ
        print(f"[LOG] É um CNPJ: {''.join(map(str, numbers))}")
        return validate_CNPJ("".join(map(str, numbers)))

    return False


def validate_email(request_data: dict, parameters: dict, form_parameters_list: list = []) -> bool:
    """
    Valida se a escrita do email está correta ou não,
    i.e., se está conforme o padrão dos nomes de email e
    do domínio.
    Retorna, True: se estiver ok! E False: se não.

    Ex: validate_email({"id": "123"}, {"usuario_email": "email@dominio.com"})
    """
    email = parameters.get("usuario_email") or parameters.get("email")
    if not email:
        return False
        
    regex = r"^[\w\.-]+@[\w\.-]+\.\w+$"
    return re.match(regex, email) is not None


def check_user_in_database(cpf: str) -> Dict[str, Any]:
    """
    Verifica se o usuário está cadastrado na base de dados.
    
    Args:
        cpf: CPF limpo (apenas números)
        
    Returns:
        dict: Dados do usuário se encontrado, dict vazio caso contrário
    """
    # Remove formatação do CPF
    cpf_clean = ''.join(c for c in cpf if c.isdigit())
    
    if cpf_clean in USER_DATABASE:
        return {
            "found": True,
            "nome": USER_DATABASE[cpf_clean]["nome"],
            "email": USER_DATABASE[cpf_clean]["email"]
        }
    
    return {"found": False}


def update_user_in_database(cpf: str, nome: str = None, email: str = None):
    """
    Atualiza ou cria usuário na base de dados.
    
    Args:
        cpf: CPF limpo (apenas números)
        nome: Nome do usuário
        email: Email do usuário
    """
    cpf_clean = ''.join(c for c in cpf if c.isdigit())
    
    if cpf_clean not in USER_DATABASE:
        USER_DATABASE[cpf_clean] = {}
    
    if nome:
        USER_DATABASE[cpf_clean]["nome"] = nome
    if email:
        USER_DATABASE[cpf_clean]["email"] = email
    
    print(f"[LOG] Usuário atualizado na base: CPF {cpf_clean}")


# Funções auxiliares para uso direto (sem dict de parâmetros)
def validate_cpf_simple(cpf: str) -> bool:
    """Validação simples de CPF"""
    return validate_CPF({}, {"usuario_cpf": cpf})


def validate_email_simple(email: str) -> bool:
    """Validação simples de email"""
    return validate_email({}, {"usuario_email": email})


def format_cpf(cpf: str) -> str:
    """Formata CPF no padrão xxx.xxx.xxx-xx"""
    numbers = ''.join(c for c in cpf if c.isdigit())
    if len(numbers) == 11:
        return f"{numbers[:3]}.{numbers[3:6]}.{numbers[6:9]}-{numbers[9:]}"
    return cpf

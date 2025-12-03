# from src.tools import mcp_tools

# for tool in mcp_tools:
#     print("tool_name: ", tool.name)
#     print("tool_description: ", tool.description)
#     print("\n\n")


import random
import string
import json


def gerar_conversa_aleatoria(num_mensagens: int, tamanho_content: int) -> list:
    """
    Gera uma lista de dicionários simulando uma conversa com conteúdo e papéis aleatórios.

    Args:
        num_mensagens (int): O número total de mensagens a serem geradas na conversa.
        tamanho_content (int): O comprimento da string de conteúdo aleatório para cada mensagem.

    Returns:
        list: Uma lista de dicionários, onde cada dicionário representa uma mensagem.
    """
    conversa = []
    papeis_possiveis = ["human", "ai"]

    # Define os caracteres que podem ser usados no conteúdo (letras + dígitos + espaços)
    caracteres_aleatorios = (
        string.ascii_letters + string.digits + " " * 10
    )  # Adiciona mais espaços para parecer mais "natural"

    for _ in range(num_mensagens):
        # Escolhe um papel aleatório da lista de papéis possíveis
        papel_aleatorio = random.choice(papeis_possiveis)

        # Gera o conteúdo aleatório com o tamanho especificado
        conteudo_aleatorio = "".join(
            random.choice(caracteres_aleatorios) for _ in range(tamanho_content)
        )

        # Cria o dicionário da mensagem e adiciona à lista da conversa
        mensagem = {"content": conteudo_aleatorio, "role": papel_aleatorio}
        conversa.append(mensagem)

    return conversa


# --- Como Usar ---

# 1. Defina os parâmetros desejados
QUANTIDADE_DE_MENSAGENS = 1000
TAMANHO_DO_CONTENT = 800  # Define que cada mensagem terá 80 caracteres

# 2. Chame a função para gerar a lista de mensagens
lista_de_mensagens = gerar_conversa_aleatoria(
    num_mensagens=QUANTIDADE_DE_MENSAGENS, tamanho_content=TAMANHO_DO_CONTENT
)

# 3. Imprima o resultado de forma legível (usando o módulo json para formatação)
# O 'indent=2' formata o JSON para que seja fácil de ler
print(json.dumps(lista_de_mensagens, indent=2))

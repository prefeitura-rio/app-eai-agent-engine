import json
import time
from src.services.tool import multi_step_service, save_single_workflow_graph


def main():
    """
    Main function to run the test flow.
    """

    user_id = f"asdasdasdsad"  # Novo usuário para cada teste
    service_name = "iptu_ano_vigente"
    save_single_workflow_graph(service_name=service_name)
    # Teste com payload separado para verificar se funciona agora
    steps = [
        # Passo 1: Criar conta
        # {},
        {
            "inscricao_imobiliaria": "01234567890123",
        },
        # {
        #     "tipo_cobranca": "cota_unica",
        # },
        # {"formato_pagamento": "codigo_barras"},
        # # Passo 2: Escolher ação e valor ao mesmo tempo
        # {"mesma_guia": True},
        # # Passo 3: Verificar saldo
        # {"ask_action": "balance"},
    ]

    for i, payload in enumerate(steps, 1):
        print(f"\n=== PASSO {i} ===")
        print(f"Payload: {payload}")
        response = multi_step_service.invoke(
            {
                "service_name": service_name,
                "user_id": user_id,
                "payload": payload,
            }
        )
        print("Response:")
        print(json.dumps(response, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

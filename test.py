import json
import time
from src.services.tool import multi_step_service, save_single_workflow_graph


def main():
    """
    Main function to test IPTU workflow with real API integration.
    """

    user_id = f"test_user_iptu_{int(time.time())}"  # Unique user for each test
    service_name = "iptu_ano_vigente"

    print("=" * 80)
    print("TESTING IPTU WORKFLOW WITH REAL API INTEGRATION")
    print("=" * 80)

    # Save workflow graph for visualization
    # print("\n📊 Saving workflow graph...")
    # save_single_workflow_graph(service_name=service_name)
    # print("✅ Graph saved!")

    # Test steps with real inscricao that works in production API
    # Note: API accepts short inscricoes like "18", but Pydantic model requires 14-16 digits
    # So we pad with zeros: "18" -> "00000000000018"
    steps = [
        # Step 1: Provide inscricao (padded to 14 digits minimum)
        {
            "inscricao_imobiliaria": "00000018",  # "18" padded to 14 digits
        },
        {
            "ano_exercicio": 2025,
        },
        # # Step 2: Choose which guia to pay (IPTU or Taxa de Lixo)
        {
            "guia_escolhida": "00",
        },
        # # Step 4: Choose cotas to pay (for parcelamento)
        {
            "cotas_escolhidas": ["01", "02", "03"],
        },
        # # Step 5: Choose payment format (darf or codigo_barras)
        {
            "pagar_darf_separado": False,
        },
        # # Step 6: Do you want to generate more guides for the same property?
        {
            "confirmacao": True,
        },
        # # Step 7: Do you want to generate guides for another property?
        # {
        #     "outro_imovel": False,
        # },
    ]

    for i, payload in enumerate(steps, 1):
        print(f"\n{'='*80}")
        print(f"STEP {i}/{len(steps)}")
        print(f"{'='*80}")
        print(f"📤 Payload: {json.dumps(payload, indent=2, ensure_ascii=False)}")

        response = multi_step_service.invoke(
            {
                "service_name": service_name,
                "user_id": user_id,
                "payload": payload,
            }
        )

        print(f"\n📥 Response:")
        print(json.dumps(response, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    # Run main test with full workflow
    main()

import json
import time
from src.services.tool import multi_step_service, save_single_workflow_graph


def main():
    """
    Main function to test IPTU workflow with real API integration.
    """

    user_id = f"test_user_iptu_{int(time.time())}"  # Unique user for each test
    service_name = "iptu_ano_vigente"
    
    print("="*80)
    print("TESTING IPTU WORKFLOW WITH REAL API INTEGRATION")
    print("="*80)
    
    # Save workflow graph for visualization
    print("\n📊 Saving workflow graph...")
    save_single_workflow_graph(service_name=service_name)
    print("✅ Graph saved!")
    
    # Test steps with real inscricao that works in production API
    # Note: API accepts short inscricoes like "18", but Pydantic model requires 14-16 digits
    # So we pad with zeros: "18" -> "00000000000018"
    steps = [
        # Step 1: Provide inscricao (padded to 14 digits minimum)
        {
            "inscricao_imobiliaria": "00000000000018",  # "18" padded to 14 digits
        },
        # Step 2: Choose which guia to pay (IPTU or Taxa de Lixo)
        {
            "guia_escolhida": "IPTU",
        },
        # Step 3: Choose payment type (cota_unica or cota_parcelada)
        {
            "tipo_cobranca": "cota_parcelada",
        },
        # Step 4: Choose cotas to pay (for parcelamento)
        {
            "cotas_escolhidas": ["1ª Cota", "2ª Cota"],
        },
        # Step 5: Choose payment format (darf or codigo_barras)
        {
            "formato_pagamento": "codigo_barras",
        },
        # Step 6: Do you want to generate more guides for the same property?
        {
            "mesma_guia": False,
        },
        # Step 7: Do you want to generate guides for another property?
        {
            "outro_imovel": False,
        },
    ]

    for i, payload in enumerate(steps, 1):
        print(f"\n{'='*80}")
        print(f"STEP {i}/{len(steps)}")
        print(f"{'='*80}")
        print(f"📤 Payload: {json.dumps(payload, indent=2, ensure_ascii=False)}")
        
        try:
            response = multi_step_service.invoke(
                {
                    "service_name": service_name,
                    "user_id": user_id,
                    "payload": payload,
                }
            )
            
            print(f"\n📥 Response:")
            print(json.dumps(response, indent=2, ensure_ascii=False))
            
            # Check for errors
            if response.get("error"):
                print(f"\n❌ ERROR: {response.get('error')}")
                print("Stopping test execution.")
                break
                
            # Small delay between steps to see the flow clearly
            time.sleep(0.5)
            
        except Exception as e:
            print(f"\n❌ EXCEPTION: {str(e)}")
            import traceback
            traceback.print_exc()
            break
    
    print(f"\n{'='*80}")
    print("TEST COMPLETED")
    print(f"{'='*80}")


def test_cota_unica():
    """
    Test workflow with cota única (single payment with discount).
    """
    user_id = f"test_user_cota_unica_{int(time.time())}"
    service_name = "iptu_ano_vigente"
    
    print("\n" + "="*80)
    print("TESTING COTA ÚNICA FLOW")
    print("="*80)
    
    steps = [
        {"inscricao_imobiliaria": "00000000000018"},  # Padded to 14 digits
        {"guia_escolhida": "IPTU"},
        {"tipo_cobranca": "cota_unica"},
        {"formato_pagamento": "darf"},
        {"mesma_guia": False},
        {"outro_imovel": False},
    ]
    
    for i, payload in enumerate(steps, 1):
        print(f"\n--- Step {i}: {list(payload.keys())[0]} ---")
        try:
            response = multi_step_service.invoke({
                "service_name": service_name,
                "user_id": user_id,
                "payload": payload,
            })
            
            # Show only the description (main message to user)
            if response.get("description"):
                print(f"🤖 Agent: {response['description'][:200]}...")
            
            if response.get("error"):
                print(f"❌ Error: {response['error']}")
                break
                
        except Exception as e:
            print(f"❌ Exception: {str(e)}")
            break
    
    print("\n✅ Cota única flow completed")


def test_invalid_inscricao():
    """
    Test workflow with invalid inscricao (should be rejected).
    """
    user_id = f"test_user_invalid_{int(time.time())}"
    service_name = "iptu_ano_vigente"
    
    print("\n" + "="*80)
    print("TESTING INVALID INSCRICAO (Should be rejected)")
    print("="*80)
    
    # Too long inscricao (should fail validation)
    payload = {"inscricao_imobiliaria": "01234567890123456"}
    
    print(f"\n📤 Payload: {payload}")
    
    try:
        response = multi_step_service.invoke({
            "service_name": service_name,
            "user_id": user_id,
            "payload": payload,
        })
        
        print(f"\n📥 Response:")
        print(json.dumps(response, indent=2, ensure_ascii=False))
        
        if "não encontrada" in response.get("description", "").lower() or \
           response.get("error_message"):
            print("\n✅ Correctly rejected invalid inscricao")
        else:
            print("\n⚠️ Invalid inscricao was not rejected")
            
    except Exception as e:
        print(f"\n❌ Exception: {str(e)}")


if __name__ == "__main__":
    # Run main test with full workflow
    main()
    
    # Test cota única flow (shorter)
    test_cota_unica()
    
    # Test invalid inscricao
    test_invalid_inscricao()

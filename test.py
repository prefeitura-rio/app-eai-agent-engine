from src.tools import multi_step_service
from src.services import SERVICE_REGISTRY, BaseService


def test_data_collection_service():
    """Test complete data collection service flow"""
    print("=== Testando Data Collection Service ===\n")

    # Step 1: Start service
    print("1. Iniciando serviço...")
    result = multi_step_service.invoke(
        {"service_name": "data_collection", "step": "start"}
    )
    print(f"Result: {result}")

    if result["status"] != "started":
        print("❌ Erro ao iniciar serviço")
        return

    session_id = result["session_id"]
    print(f"✅ Serviço iniciado. Session ID: {session_id}")
    print(f"Steps info: {result['steps_info']}")
    print(f"Mensagem: {result['message']}")
    print()

    # Step 2: Provide CPF
    print("2. Fornecendo CPF...")
    result = multi_step_service.invoke(
        {"service_name": "data_collection", "step": "cpf", "payload": "12345678901"}
    )
    print(f"Result: {result}")

    if result["status"] != "success":
        print("❌ Erro na validação do CPF")
        return

    print(f"✅ CPF validado. Próximo step: {result['next_step']}")
    print(f"Mensagem: {result['message']}")
    print()

    # Step 3: Provide email
    print("3. Fornecendo email...")
    result = multi_step_service.invoke(
        {
            "service_name": "data_collection",
            "step": "email",
            "payload": "test@example.com",
        }
    )
    print(f"Result: {result}")

    if result["status"] != "success":
        print("❌ Erro na validação do email")
        return

    print(f"✅ Email validado. Próximo step: {result['next_step']}")
    print(f"Mensagem: {result['message']}")
    print()

    # Step 4: Provide name (final step)
    print("4. Fornecendo nome...")
    result = multi_step_service.invoke(
        {"service_name": "data_collection", "step": "name", "payload": "João da Silva"}
    )
    print(f"Result: {result}")

    if result["status"] != "completed":
        print("❌ Erro na validação do nome ou serviço não foi completado")
        return

    print(f"✅ Serviço completado!")
    print(f"Mensagem: {result['message']}")
    print(f"Dados coletados: {result['data']}")
    print()


def test_error_cases():
    """Test error handling"""
    print("=== Testando casos de erro ===\n")

    # Test invalid CPF
    print("1. Testando CPF inválido...")
    multi_step_service.invoke(
        {"service_name": "data_collection", "step": "start"}
    )  # Start new session
    result = multi_step_service.invoke(
        {"service_name": "data_collection", "step": "cpf", "payload": "123"}
    )  # Invalid CPF
    print(f"Result: {result}")

    if result["status"] == "error":
        print(f"✅ Erro capturado corretamente: {result['message']}")
    else:
        print("❌ Erro não foi capturado")
    print()

    # Test invalid email
    print("2. Testando email inválido...")
    multi_step_service.invoke(
        {"service_name": "data_collection", "step": "start"}
    )  # Start new session
    multi_step_service.invoke(
        {"service_name": "data_collection", "step": "cpf", "payload": "12345678901"}
    )  # Valid CPF first
    result = multi_step_service.invoke(
        {"service_name": "data_collection", "step": "email", "payload": "invalid-email"}
    )
    print(f"Result: {result}")

    if result["status"] == "error":
        print(f"✅ Erro capturado corretamente: {result['message']}")
    else:
        print("❌ Erro não foi capturado")
    print()


def test_service_registry():
    """Test service registry"""
    print("=== Testando Service Registry ===\n")

    print("Serviços disponíveis:")
    for name, cls in SERVICE_REGISTRY.items():
        print(f"- {name}: {cls.__doc__}")

        # Create temp instance to show steps
        instance = cls("test")
        steps_info = instance.get_steps_info()
        print(f"  Steps: {[step['name'] for step in steps_info]}")
    print()


if __name__ == "__main__":
    # Run all tests
    test_service_registry()
    test_data_collection_service()
    test_error_cases()

    print("=== Teste completo finalizado ===")

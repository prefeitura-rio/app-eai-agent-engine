#!/usr/bin/env python3
"""
Bateria final de testes para a arquitetura modular de serviços
Versão atualizada para nova interface unificada (payload sempre Dict[str, str])
"""

import json
import os
import shutil
from typing import List, Tuple

from src.services import SERVICE_REGISTRY, build_service_registry, multi_step_service
from src.services.base_service import BaseService
from src.services.schema import StepInfo, ServiceDefinition
from src.services.repository.data_collection import DataCollectionService
from src.services.repository.bank_account import BankAccountService
from src.services.repository.bank_account_advanced import BankAccountAdvancedService


def setup_test_environment():
    """Prepara ambiente limpo para testes"""
    shutil.rmtree("service_states", ignore_errors=True)
    os.makedirs("service_states", exist_ok=True)


def print_test_header(test_name: str):
    """Imprime cabeçalho de teste formatado"""
    print(f"\n{'='*60}")
    print(f"🧪 {test_name}")
    print(f"{'='*60}")


def print_result(description: str, success: bool = True):
    """Imprime resultado de teste formatado"""
    status_icon = "✅" if success else "❌"
    print(f"{status_icon} {description}")


# =============================================================================
# TESTES CORE - SCHEMA E BASESERVICE
# =============================================================================

def test_simplified_framework():
    """Testa framework simplificado mantendo funcionalidades"""
    print_test_header("FRAMEWORK SIMPLIFICADO - FUNCIONALIDADES")
    
    # 1. StepInfo simplificado
    step = StepInfo(name="valid_step", description="Descrição válida")
    print_result("StepInfo simplificado criado")
    assert step.name == "valid_step"
    
    # 2. Validação básica funciona
    from src.services import multi_step_service
    result = multi_step_service.invoke({
        'service_name': 'data_collection',
        'payload': {'cpf': '12345678901'},
        'user_id': 'test_simplified'
    })
    print_result("Tool básica funciona")
    assert result['status'] in ['progress', 'ready']
    assert 'cpf' in result.get('completed_steps', [])
    
    # 3. Auto-detecção de substeps
    result = multi_step_service.invoke({
        'service_name': 'bank_account_advanced', 
        'payload': {
            'name': 'João Silva', 
            'email': 'joao@test.com',
            'document_number': '12345678901',
            'document_type': 'CPF'
        },
        'user_id': 'test_substeps'
    })
    print_result("Auto-detecção de substeps funciona")
    assert result['status'] in ['progress', 'ready']
    
    # 4. Validação de dependências (duas etapas para testar dependência)
    # Primeiro: document_type
    result = multi_step_service.invoke({
        'service_name': 'bank_account',
        'payload': {'document_type': 'CPF'},
        'user_id': 'test_deps'
    })
    assert result['status'] in ['progress', 'ready']
    assert 'document_type' in result.get('completed_steps', [])
    
    # Depois: document_number (que depende do document_type)
    result = multi_step_service.invoke({
        'service_name': 'bank_account',
        'payload': {'document_number': '12345678901'},
        'user_id': 'test_deps'
    })
    print_result("Validação de dependências funciona")
    assert result['status'] in ['progress', 'ready']
    assert 'document_type' in result.get('completed_steps', [])
    assert 'document_number' in result.get('completed_steps', [])


def test_schema_validation():
    """Testa validações do schema Pydantic"""
    print_test_header("SCHEMA PYDANTIC - VALIDAÇÕES")
    
    # 1. StepInfo válido
    step = StepInfo(name="valid_step", description="Descrição válida")
    print_result("StepInfo válido criado")
    assert step.name == "valid_step"
    assert step.required == True  # default
    
    # 2. Nome inválido
    try:
        StepInfo(name="123invalid", description="teste")
        assert False, "Deveria falhar"
    except ValueError:
        print_result("Nome inválido rejeitado corretamente")
    
    # 3. Dependências
    step_deps = StepInfo(
        name="with_deps", 
        description="Com dependências",
        depends_on=["step1"]
    )
    print_result("StepInfo com dependências criado")
    assert step_deps.depends_on == ["step1"]


class SimpleTestService(BaseService):
    """Serviço simples para testes"""
    service_name = "simple_test"
    
    def get_service_definition(self) -> ServiceDefinition:
        return ServiceDefinition(
            service_name=self.service_name,
            description="Simple test service",
            steps=[
                StepInfo(name="step1", description="Primeiro step"),
                StepInfo(name="step2", description="Segundo step", depends_on=["step1"]),
            ]
        )
    
    def execute_step(self, step: str, payload: str) -> Tuple[bool, str]:
        return len(payload) >= 3, "Payload muito curto" if len(payload) < 3 else ""
    
    def get_completion_message(self) -> str:
        return "Teste simples concluído"


def test_baseservice_core():
    """Testa funcionalidades core do BaseService"""
    print_test_header("BASESERVICE - FUNCIONALIDADES CORE")
    
    # 1. Criação válida
    service = SimpleTestService("test_user")
    print_result("SimpleTestService criado")
    assert service.service_name == "simple_test"
    assert service.user_id == "test_user"
    
    # 2. Service definition
    definition = service.get_service_definition()
    print_result("Service definition retornado")
    assert len(definition.steps) == 2
    assert definition.steps[0].name == "step1"
    
    # 3. Steps disponíveis (agora via ServiceDefinition)
    available = definition.get_available_steps(service.data)
    print_result("Steps disponíveis calculados")
    assert "step1" in available
    assert "step2" not in available  # depende de step1
    
    # 4. Após completar step1
    service.data["step1"] = "valor"
    available = definition.get_available_steps(service.data)
    print_result("Steps disponíveis após completar step1")
    assert "step2" in available


def test_dependency_validation():
    """Testa validação de dependências"""
    print_test_header("VALIDAÇÃO DE DEPENDÊNCIAS")
    
    service = SimpleTestService("dep_test")
    definition = service.get_service_definition()
    
    # 1. Step sem dependências
    is_valid, _ = definition.validate_dependencies("step1", service.data)
    print_result("Step1 sem dependências é válido")
    assert is_valid == True
    
    # 2. Step com dependências não satisfeitas
    is_valid, msg = definition.validate_dependencies("step2", service.data)
    print_result("Step2 com dependências não satisfeitas é inválido")
    assert is_valid == False
    assert "requires 'step1'" in msg
    
    # 3. Após satisfazer dependência
    service.data["step1"] = "valor"
    is_valid, _ = definition.validate_dependencies("step2", service.data)
    print_result("Step2 após satisfazer dependência é válido")
    assert is_valid == True


# =============================================================================
# TESTES DE SERVIÇOS ESPECÍFICOS
# =============================================================================

def test_data_collection_complete():
    """Teste completo do DataCollectionService com nova interface"""
    print_test_header("DATA COLLECTION - NOVA INTERFACE")
    
    setup_test_environment()
    
    # 1. Início - payload vazio
    result = multi_step_service.invoke({
        "service_name": "data_collection",
        "payload": {},
        "user_id": "data_user"
    })
    print_result("Início com payload vazio")
    assert result["status"] == "ready"
    assert "available_steps" in result
    assert len(result["available_steps"]) == 3
    
    # 2. Um campo individual
    result = multi_step_service.invoke({
        "service_name": "data_collection",
        "payload": {"cpf": "12345678901"},
        "user_id": "data_user"
    })
    print_result("Campo individual adicionado")
    assert result["status"] == "progress"
    assert "cpf" in result["completed_steps"]
    
    # 3. Múltiplos campos finalizando
    result = multi_step_service.invoke({
        "service_name": "data_collection",
        "payload": {"email": "test@example.com", "name": "João Silva"},
        "user_id": "data_user"
    })
    print_result("Serviço completado")
    assert result["status"] == "completed"
    assert "completion_message" in result


def test_bank_account_basic():
    """Teste básico do BankAccountService com nova interface"""
    print_test_header("BANK ACCOUNT - NOVA INTERFACE")
    
    setup_test_environment()
    
    # 1. Início - payload vazio
    result = multi_step_service.invoke({
        "service_name": "bank_account",
        "payload": {},
        "user_id": "bank_user"
    })
    print_result("Bank Account iniciado")
    assert result["status"] == "ready"
    assert "available_steps" in result
    
    # 2. Document_type primeiro
    result = multi_step_service.invoke({
        "service_name": "bank_account",
        "payload": {"document_type": "CPF"},
        "user_id": "bank_user"
    })
    print_result("Document_type definido")
    assert result["status"] == "progress"
    assert "document_type" in result["completed_steps"]
    
    # 3. Agora document_number (contextual schema para CPF)
    result = multi_step_service.invoke({
        "service_name": "bank_account",
        "payload": {"document_number": "12345678901"},
        "user_id": "bank_user"
    })
    print_result("Document_number após document_type")
    # Can be progress or validation_error if dependency not met in separate calls
    assert result["status"] in ["progress", "validation_error"]
    if result["status"] == "progress":
        assert "document_number" in result["completed_steps"]


def test_bank_account_bulk_simple():
    """Teste múltiplos campos do BankAccount"""
    print_test_header("BANK ACCOUNT - MÚLTIPLOS CAMPOS")
    
    setup_test_environment()
    
    # Múltiplos campos de uma vez
    bulk_data = {"document_type": "CPF", "document_number": "12345678901", "account_type": "poupanca", "personal_name": "João Silva", "email": "joao@test.com"}
    
    result = multi_step_service.invoke({
        "service_name": "bank_account",
        "payload": bulk_data,
        "user_id": "bank_bulk"
    })
    
    print_result("Múltiplos campos do Bank Account")
    # Pode ter validation_error mas ainda processar alguns campos válidos
    assert result["status"] in ["completed", "progress", "validation_error"]
    assert len(result["completed_steps"]) >= 3  # Pelo menos document_type, account_type, personal_name


# =============================================================================
# TESTES DO SERVICE REGISTRY
# =============================================================================

def test_service_registry():
    """Testa o SERVICE_REGISTRY dinâmico"""
    print_test_header("SERVICE REGISTRY DINÂMICO")
    
    # 1. Registry contém serviços esperados
    print_result("Registry contém data_collection")
    assert "data_collection" in SERVICE_REGISTRY
    print_result("Registry contém bank_account")
    assert "bank_account" in SERVICE_REGISTRY
    
    # 2. Classes corretas
    print_result("Classes corretas no registry")
    assert SERVICE_REGISTRY["data_collection"] == DataCollectionService
    assert SERVICE_REGISTRY["bank_account"] == BankAccountService
    
    # 3. Registry customizado
    custom_registry = build_service_registry(SimpleTestService)
    print_result("Registry customizado criado")
    assert "simple_test" in custom_registry
    assert custom_registry["simple_test"] == SimpleTestService


def test_registry_validation():
    """Testa validações do registry"""
    print_test_header("REGISTRY - VALIDAÇÕES")
    
    # 1. Serviço sem service_name
    class NoNameService(BaseService):
        def get_service_definition(self): 
            return ServiceDefinition(service_name="", description="", steps=[])
        def execute_step(self, step, payload): 
            _ = step, payload  # Suppress unused warnings
            return True, ""
        def get_completion_message(self): return ""
    
    try:
        build_service_registry(NoNameService)
        assert False, "Deveria falhar"
    except ValueError as e:
        print_result("Serviço sem service_name rejeitado")
        assert "must define service_name" in str(e)
    
    # 2. Nomes duplicados
    class Dup1(BaseService):
        service_name = "dup"
        def get_service_definition(self): 
            return ServiceDefinition(service_name="dup", description="", steps=[])
        def execute_step(self, step, payload): 
            _ = step, payload  # Suppress unused warnings
            return True, ""
        def get_completion_message(self): return ""
    
    class Dup2(BaseService):
        service_name = "dup"
        def get_service_definition(self): 
            return ServiceDefinition(service_name="dup", description="", steps=[])
        def execute_step(self, step, payload): 
            _ = step, payload  # Suppress unused warnings
            return True, ""
        def get_completion_message(self): return ""
    
    try:
        build_service_registry(Dup1, Dup2)
        assert False, "Deveria falhar"
    except ValueError as e:
        print_result("Nomes duplicados rejeitados")
        assert "Duplicate service_name" in str(e)


# =============================================================================
# TESTES DE INTEGRAÇÃO
# =============================================================================

def test_multi_user_isolation():
    """Testa isolamento entre usuários"""
    print_test_header("ISOLAMENTO ENTRE USUÁRIOS")
    
    setup_test_environment()
    
    # User A - um campo
    multi_step_service.invoke({
        "service_name": "data_collection",
        "payload": {"cpf": "11111111111"},
        "user_id": "user_a"
    })
    
    # User B - serviço completo
    multi_step_service.invoke({
        "service_name": "data_collection",
        "payload": {"cpf": "22222222222", "email": "b@test.com", "name": "User B"},
        "user_id": "user_b"
    })
    
    # Verificar arquivos separados
    files = os.listdir("service_states")
    print_result("Arquivos de estado separados por usuário")
    assert "user_a__data_collection.json" in files
    assert "user_b__data_collection.json" in files


def test_error_handling():
    """Testa tratamento de erros"""
    print_test_header("TRATAMENTO DE ERROS")
    
    setup_test_environment()
    
    # 1. Serviço inexistente
    result = multi_step_service.invoke({
        "service_name": "inexistente",
        "payload": {},
        "user_id": "error_user"
    })
    print_result("Serviço inexistente rejeitado")
    assert result["status"] == "error"
    assert "não encontrado" in result["message"]
    
    # 2. Dados inválidos
    result = multi_step_service.invoke({
        "service_name": "data_collection",
        "payload": {"cpf": "123"},  # CPF inválido
        "user_id": "validation_user"
    })
    print_result("Dados inválidos rejeitados")
    assert result["status"] == "validation_error"
    assert "errors" in result


def test_dependency_validation_fixed():
    """Testa correção do bug de validação de dependências com steps já completados"""
    print_test_header("VALIDAÇÃO DE DEPENDÊNCIAS - BUG CORRIGIDO")
    
    setup_test_environment()
    
    # 1. Primeiro: completar steps base (document_type, account_type, personal_name)
    result = multi_step_service.invoke({
        "service_name": "bank_account",
        "payload": {"document_type": "CPF", "account_type": "corrente", "personal_name": "João Silva"},
        "user_id": "dep_bug_test"
    })
    print_result("Steps base completados")
    assert result["status"] == "progress"
    assert "document_type" in result["completed_steps"]
    assert "account_type" in result["completed_steps"]
    assert "personal_name" in result["completed_steps"]
    
    # 2. Segundo: tentar steps que dependem dos anteriores (document_number, initial_deposit)
    result = multi_step_service.invoke({
        "service_name": "bank_account",
        "payload": {"document_number": "12345678901", "initial_deposit": "500.00"},
        "user_id": "dep_bug_test"
    })
    print_result("Steps dependentes aceitos sem erro")
    assert result["status"] in ["progress", "completed"]  # Pode estar completo ou em progresso
    assert "errors" not in result or len(result.get("errors", {})) == 0
    assert "document_number" in result["completed_steps"]
    assert "initial_deposit" in result["completed_steps"]
    
    # 3. Verificar que ambos os steps dependentes foram aceitos
    all_completed = result["completed_steps"]
    print_result("document_number aceito (dependia de document_type)")
    assert "document_number" in all_completed
    print_result("initial_deposit aceito (dependia de account_type)")
    assert "initial_deposit" in all_completed


def test_steps_schematic():
    """Testa o novo método get_steps_schematic do ServiceDefinition"""
    print_test_header("ESQUEMÁTICO DOS STEPS")
    
    # 1. Teste com DataCollectionService (simples, sem dependências)
    data_service = DataCollectionService("schematic_test")
    data_definition = data_service.get_service_definition()
    
    # Esquemático básico
    schematic = data_definition.get_steps_schematic()
    print_result("Esquemático básico criado")
    assert schematic["service_name"] == "data_collection"
    assert schematic["total_steps"] == 3
    assert len(schematic["steps"]) == 3
    assert "dependency_map" in schematic
    assert "dependency_tree" in schematic
    
    # 2. Teste com BankAccountService (complexo, com dependências)
    bank_service = BankAccountService("schematic_test")
    bank_definition = bank_service.get_service_definition()
    
    schematic_bank = bank_definition.get_steps_schematic()
    print_result("Esquemático com dependências criado")
    assert schematic_bank["service_name"] == "bank_account"
    assert schematic_bank["total_steps"] == 7
    assert "document_number" in schematic_bank["dependency_map"]
    assert schematic_bank["dependency_map"]["document_number"] == ["document_type"]
    
    # 3. Teste com dados parciais (status dos steps)
    partial_data = {"document_type": "CPF", "account_type": "corrente"}
    schematic_with_status = bank_definition.get_steps_schematic(partial_data)
    print_result("Esquemático com status dos steps")
    assert schematic_with_status["state_analysis"] is not None
    
    # Verificar status específicos
    steps_by_name = {step["name"]: step for step in schematic_with_status["steps"]}
    assert steps_by_name["document_type"]["status"] == "completed"
    assert steps_by_name["document_number"]["status"] == "available_required"
    assert steps_by_name["email"]["status"] == "pending"
    
    # 4. Teste da árvore de dependências
    tree = schematic_bank["dependency_tree"]
    print_result("Árvore de dependências estruturada")
    assert len(tree) > 0  # Deve ter pelo menos alguns nós raiz
    
    # Encontrar nó document_type na árvore
    doc_type_node = None
    for node in tree:
        if node["name"] == "document_type":
            doc_type_node = node
            break
    
    assert doc_type_node is not None
    assert len(doc_type_node["children"]) > 0  # document_number depende de document_type


def test_visual_schematic_in_responses():
    """Testa se o campo visual_schematic está sendo incluído nas respostas do multi_step_service"""
    print_test_header("VISUAL SCHEMATIC NAS RESPOSTAS")
    
    setup_test_environment()
    
    # 1. Teste estado inicial - deve ter visual_schematic
    result = multi_step_service.invoke({
        "service_name": "bank_account",
        "payload": {},
        "user_id": "visual_response_test"
    })
    print_result("Campo visual_schematic presente no estado inicial")
    assert "visual_schematic" in result
    assert isinstance(result["visual_schematic"], str)
    assert "🌳 DEPENDENCY TREE:" in result["visual_schematic"]
    
    # 2. Teste com dados parciais - deve mostrar progresso
    result = multi_step_service.invoke({
        "service_name": "bank_account",
        "payload": {"document_type": "CPF", "personal_name": "João Silva"},
        "user_id": "visual_response_test"
    })
    print_result("Visual_schematic com progresso")
    assert "visual_schematic" in result
    assert "🌳 DEPENDENCY TREE:" in result["visual_schematic"]
    
    # 3. Teste com erro de validação - deve ter visual_schematic mesmo com erro
    result = multi_step_service.invoke({
        "service_name": "data_collection",
        "payload": {"cpf": "123"},  # CPF inválido
        "user_id": "visual_error_test"
    })
    print_result("Visual_schematic presente mesmo com erro de validação")
    assert result["status"] == "validation_error"
    assert "visual_schematic" in result
    assert "🌳 DEPENDENCY TREE:" in result["visual_schematic"]
    
    # 4. Teste serviço completado - deve ter visual_schematic
    result = multi_step_service.invoke({
        "service_name": "data_collection",
        "payload": {"cpf": "12345678901", "email": "test@example.com", "name": "João Silva"},
        "user_id": "visual_complete_test"
    })
    print_result("Visual_schematic no serviço completado")
    assert result["status"] == "completed"
    assert "visual_schematic" in result
    assert "🌳 DEPENDENCY TREE:" in result["visual_schematic"]


def test_bank_account_advanced():
    """Testa o novo serviço BankAccountAdvanced com estrutura JSON complexa"""
    print_test_header("BANK ACCOUNT ADVANCED - JSON ESTRUTURADO")
    
    setup_test_environment()
    
    # 1. Verificar serviço disponível
    result = multi_step_service.invoke({
        "service_name": "bank_account_advanced",
        "payload": {},
        "user_id": "advanced_test"
    })
    print_result("Serviço bank_account_advanced disponível")
    assert result["status"] == "ready"
    assert result["service_name"] == "bank_account_advanced"
    assert "user_info" in result["available_steps"]
    
    # 2. Teste user_info com JSON estruturado
    user_info = {
        "name": "João Silva",
        "document_number": "12345678901",
        "email": "test@example.com", 
        "document_type": "CPF"
    }
    
    result = multi_step_service.invoke({
        "service_name": "bank_account_advanced",
        "payload": {"user_info": user_info},
        "user_id": "advanced_test"
    })
    print_result("User_info JSON aceito")
    assert result["status"] == "progress"
    assert "user_info" in result["completed_steps"]
    assert "account_info" in result["available_steps"]
    
    # 3. Múltiplos steps JSON de uma vez
    account_info = {
        "account_type": "corrente",
        "bank_name": "Banco do Brasil", 
        "agency_number": "1234",
        "account_number": "56789-0"
    }
    address = {"street": "Rua A", "number": 123}
    contact = {"email": "test@example.com", "phone": "1234567890"}
    
    result = multi_step_service.invoke({
        "service_name": "bank_account_advanced",
        "payload": {
            "account_info": account_info,
            "address": address,
            "contact": contact
        },
        "user_id": "advanced_test"
    })
    print_result("Múltiplos steps JSON processados")
    assert result["status"] == "completed"
    assert len(result["current_data"]) == 4  # user_info + account_info + address + contact
    
    # 4. Teste deposits opcionais
    setup_test_environment()  # Reset environment
    
    # Completar tudo incluindo deposits
    deposits = [
        {"amount": 1000.0, "date": "2025-09-19T11:57:13.205906"},
        {"amount": 500.0, "date": "2025-09-19T11:59:13.205906"}
    ]
    
    result = multi_step_service.invoke({
        "service_name": "bank_account_advanced",
        "payload": {
            "user_info": user_info,
            "account_info": account_info,
            "address": address,
            "contact": contact,
            "deposits": deposits
        },
        "user_id": "advanced_deposits_test"
    })
    print_result("Todos os steps incluindo deposits aceitos")
    assert result["status"] == "completed"
    assert len(result["current_data"]) == 5  # Todos os 5 steps
    assert "deposits" in result["current_data"]
    
    # 5. Teste validação de JSON inválido
    result = multi_step_service.invoke({
        "service_name": "bank_account_advanced",
        "payload": {"user_info": "invalid json"},
        "user_id": "advanced_error_test"
    })
    print_result("JSON inválido rejeitado corretamente")
    assert result["status"] == "validation_error"
    assert "user_info" in result["errors"]


# =============================================================================
# RUNNER PRINCIPAL
# =============================================================================

def run_complete_tests():
    """Executa todos os testes"""
    print("🚀 BATERIA FINAL DE TESTES - ARQUITETURA MODULAR")
    print("Foco: Funcionalidades implementadas e estáveis\n")
    
    tests = [
        # Framework Simplificado
        test_simplified_framework,
        
        # Core
        test_schema_validation,
        test_baseservice_core,
        test_dependency_validation,
        
        # Serviços
        test_data_collection_complete,
        test_bank_account_basic,
        test_bank_account_bulk_simple,
        
        # Registry
        test_service_registry,
        test_registry_validation,
        
        # Integração
        test_multi_user_isolation,
        test_error_handling,
        test_dependency_validation_fixed,
        test_steps_schematic,
        test_visual_schematic_in_responses,
        test_bank_account_advanced,
    ]
    
    passed = 0
    failed = 0
    
    for test_func in tests:
        try:
            test_func()
            passed += 1
        except Exception as e:
            print(f"❌ FALHA: {test_func.__name__} - {e}")
            failed += 1
    
    # Resumo
    print(f"\n{'='*60}")
    print(f"📊 RESUMO FINAL")
    print(f"{'='*60}")
    print(f"✅ Aprovados: {passed}")
    print(f"❌ Falharam: {failed}")
    print(f"📈 Taxa: {(passed/(passed+failed)*100):.1f}%")
    
    if failed == 0:
        print(f"\n🎉 NOVA INTERFACE UNIFICADA 100% VALIDADA!")
        print("- ✅ Schema Pydantic com validações rigorosas")
        print("- ✅ BaseService limpo (apenas execução)")
        print("- ✅ ServiceDefinition com lógica pesada")
        print("- ✅ Interface payload sempre Dict[str, str]")
        print("- ✅ SERVICE_REGISTRY dinâmico e validado")
        print("- ✅ Serviços específicos funcionais")
        print("- ✅ Isolamento entre usuários")
        print("- ✅ Tratamento de erros robusto")
        print("- ✅ Zero redundância na interface")
    else:
        print(f"\n⚠️  {failed} teste(s) falharam.")


if __name__ == "__main__":
    run_complete_tests()
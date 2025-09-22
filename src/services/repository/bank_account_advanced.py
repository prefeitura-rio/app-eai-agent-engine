"""
Serviço avançado de conta bancária com estrutura de dados complexa e aninhada.
Demonstra capacidades de processamento de JSON estruturado e dependências avançadas.
"""

import json
from typing import Tuple, Dict, Any, List
from datetime import datetime

from src.services.base_service import BaseService
from src.services.schema import ServiceDefinition, StepInfo


class BankAccountAdvancedService(BaseService):
    """
    Serviço avançado para criação de conta bancária com dados estruturados.

    Estrutura final de dados:
    {
        "user_info": {
            "name": str,
            "document_number": str,
            "email": str,
            "document_type": str
        },
        "account_info": {
            "account_type": str,
            "bank_name": str,
            "agency_number": str,
            "account_number": str
        },
        "address": {
            "street": str,
            "number": int
        },
        "contact": {
            "email": str,
            "phone": str
        },
        "deposits": [
            {
                "amount": float,
                "date": str (ISO format)
            }
        ]
    }
    """

    service_name = "bank_account_advanced"

    def get_service_definition(self) -> ServiceDefinition:
        return ServiceDefinition(
            service_name=self.service_name,
            description="Hybrid bank account service with substeps for user_info and append-mode for deposits",
            steps=[
                # User Info - Step with infinite nested substeps
                StepInfo(
                    name="user_info",
                    description="Informações completas do usuário com nesting infinito",
                    payload_example={
                        "name": "João Silva",
                        "document": {
                            "number": "12345678901",
                            "type": "CPF"
                        },
                        "contact": {
                            "email": "test@example.com",
                            "phone": "11999999999"
                        },
                        "address": {
                            "street": "Rua das Flores",
                            "number": 123,
                            "district": "Centro",
                            "coordinates": {
                                "latitude": -23.5505,
                                "longitude": -46.6333,
                                "precision": {
                                    "level": "high",
                                    "meters": 5
                                }
                            }
                        }
                    },
                    required=True,
                    substeps=[
                        StepInfo(
                            name="name",
                            description="Nome completo do usuário",
                            payload_example={"name": "João Silva"},
                            required=True,
                        ),
                        StepInfo(
                            name="document",
                            description="Informações do documento",
                            payload_example={
                                "document": {
                                    "number": "12345678901",
                                    "type": "CPF"
                                }
                            },
                            required=True,
                            substeps=[
                                StepInfo(
                                    name="number",
                                    description="Número do documento",
                                    payload_example={"number": "12345678901"},
                                    required=True,
                                ),
                                StepInfo(
                                    name="type",
                                    description="Tipo do documento (CPF/CNPJ)",
                                    payload_example={"type": "CPF"},
                                    required=True,
                                ),
                            ],
                        ),
                        StepInfo(
                            name="contact",
                            description="Informações de contato",
                            payload_example={
                                "contact": {
                                    "email": "test@example.com",
                                    "phone": "11999999999"
                                }
                            },
                            required=True,
                            substeps=[
                                StepInfo(
                                    name="email",
                                    description="E-mail principal",
                                    payload_example={"email": "test@example.com"},
                                    required=True,
                                ),
                                StepInfo(
                                    name="phone",
                                    description="Telefone principal",
                                    payload_example={"phone": "11999999999"},
                                    required=False,
                                ),
                            ],
                        ),
                        StepInfo(
                            name="address",
                            description="Endereço completo com coordenadas",
                            payload_example={
                                "address": {
                                    "street": "Rua das Flores",
                                    "number": 123,
                                    "district": "Centro",
                                    "coordinates": {
                                        "latitude": -23.5505,
                                        "longitude": -46.6333,
                                        "precision": {
                                            "level": "high",
                                            "meters": 5
                                        }
                                    }
                                }
                            },
                            required=True,
                            substeps=[
                                StepInfo(
                                    name="street",
                                    description="Nome da rua",
                                    payload_example={"street": "Rua das Flores"},
                                    required=True,
                                ),
                                StepInfo(
                                    name="number",
                                    description="Número da residência",
                                    payload_example={"number": 123},
                                    required=True,
                                ),
                                StepInfo(
                                    name="district",
                                    description="Bairro",
                                    payload_example={"district": "Centro"},
                                    required=False,
                                ),
                                StepInfo(
                                    name="coordinates",
                                    description="Coordenadas geográficas com precisão",
                                    payload_example={
                                        "coordinates": {
                                            "latitude": -23.5505,
                                            "longitude": -46.6333,
                                            "precision": {
                                                "level": "high",
                                                "meters": 5
                                            }
                                        }
                                    },
                                    required=False,
                                    substeps=[
                                        StepInfo(
                                            name="latitude",
                                            description="Latitude (decimal)",
                                            payload_example={"latitude": -23.5505},
                                            required=True,
                                        ),
                                        StepInfo(
                                            name="longitude",
                                            description="Longitude (decimal)",
                                            payload_example={"longitude": -46.6333},
                                            required=True,
                                        ),
                                        StepInfo(
                                            name="precision",
                                            description="Informações de precisão da coordenada",
                                            payload_example={
                                                "precision": {
                                                    "level": "high",
                                                    "meters": 5
                                                }
                                            },
                                            required=False,
                                            substeps=[
                                                StepInfo(
                                                    name="level",
                                                    description="Nível de precisão (low/medium/high)",
                                                    payload_example={"level": "high"},
                                                    required=True,
                                                ),
                                                StepInfo(
                                                    name="meters",
                                                    description="Precisão em metros",
                                                    payload_example={"meters": 5},
                                                    required=False,
                                                ),
                                            ],
                                        ),
                                    ],
                                ),
                            ],
                        ),
                    ],
                ),
                # Account Info Group (mantém JSON simples)
                StepInfo(
                    name="account_info",
                    description="Informações da conta bancária em formato JSON",
                    payload_example={
                        "account_info": {
                            "account_type": "corrente",
                            "bank_name": "Banco do Brasil",
                            "agency_number": "1234",
                            "account_number": "56789-0",
                        }
                    },
                    required=True,
                    depends_on=["user_info"],
                ),
                # Deposits - Array step (append mode automático)
                StepInfo(
                    name="deposits",
                    description="Depósito individual ou lista de depósitos (modo append automático)",
                    payload_example={
                        "deposits": [
                            {"amount": 1000.0, "date": "2025-09-19T11:57:13.205906"}
                        ]
                    },
                    required=False,
                    depends_on=["account_info"],
                ),
            ],
        )

    def execute_step(self, step: str, payload: str) -> Tuple[bool, str]:
        """
        Valida e processa cada step com detecção automática baseada no payload_example.
        Suporta substeps infinitos com dot notation.
        """
        payload = payload.strip()

        # Primeiro verificar se é um step principal válido
        definition = self.get_service_definition()
        step_info = definition.get_step_info(step)

        # Se é um step principal válido, processar como tal
        if step_info:
            # Detectar tipo baseado no payload_example
            if step_info.payload_example:
                # Verificar o tipo do payload_example como um todo
                if isinstance(step_info.payload_example, dict):
                    # Verificar se é um dict com array como valor principal
                    values = list(step_info.payload_example.values())
                    if len(values) == 1 and isinstance(values[0], list):
                        # Modo append automático para listas de objetos
                        return self._handle_array_step(step, payload)
                    else:
                        # JSON como dicionário
                        return self._handle_dict_step(step, payload)
                elif isinstance(step_info.payload_example, list):
                    # Lista direta
                    return self._handle_array_step(step, payload)
                else:
                    # String simples
                    return self._handle_string_step(step, payload)
            else:
                # Default para string se não tem payload_example
                return self._handle_string_step(step, payload)
                
        # Se não é step principal, pode ser substep com dot notation
        else:
            return self._handle_nested_substep(step, payload)
            
        return False, f"Step '{step}' não reconhecido"

    def _handle_array_step(self, step: str, payload: str) -> Tuple[bool, str]:
        """
        Manipula steps com array (detectado pelo payload_example) com append automático.
        Se o step já existe, faz append. Caso contrário, inicializa a lista.
        """
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            return False, f"{step} deve ser um JSON válido"

        # Inicializar array se não existir
        if step not in self.data:
            self.data[step] = []

        # Se recebeu um array, validar cada item e fazer extend
        if isinstance(data, list):
            for i, item in enumerate(data):
                if step == "deposits":
                    is_valid, error_msg = self._validate_single_deposit(item, i)
                    if not is_valid:
                        return False, error_msg

            # Se todas as validações passaram, adicionar todos ao array
            self.data[step].extend(data)
            return True, ""

        # Se recebeu um objeto único, validar e fazer append
        elif isinstance(data, dict):
            if step == "deposits":
                is_valid, error_msg = self._validate_single_deposit(
                    data, len(self.data[step]) + 1
                )
                if not is_valid:
                    return False, error_msg

            self.data[step].append(data)
            return True, ""

        else:
            return False, f"{step} deve ser um objeto JSON ou array de objetos"

    def _handle_nested_substep(self, substep_key: str, payload: str) -> Tuple[bool, str]:
        """
        Manipula substeps individuais (ex: user_info_name, user_info_email).
        Acumula os dados e monta o JSON final quando todos estão completos.
        """
        # Separar step principal e substep - precisa encontrar o step principal correto
        definition = self.get_service_definition()

        # Tentar encontrar qual step principal possui substeps que correspondem
        main_step = None
        substep_name = None

        # Primeiro, verificar formato antigo: user_info_name
        for step_info in definition.steps:
            if step_info.substeps and substep_key.startswith(step_info.name + "_"):
                main_step = step_info.name
                substep_name = substep_key[
                    len(step_info.name) + 1 :
                ]  # Remove "step_name_"
                break

        # Se não encontrou, verificar se é um substep direto (formato novo)
        if not main_step:
            for step_info in definition.steps:
                if step_info.substeps:
                    # Verificar se substep_key é um substep direto deste step
                    substep_found = step_info.find_step_by_path(substep_key)
                    if substep_found:
                        main_step = step_info.name
                        substep_name = substep_key
                        break

        if not main_step or not substep_name:
            return False, f"Substep '{substep_key}' não encontrado em nenhum step principal"

        # Verificar se o step principal existe e tem substeps
        definition = self.get_service_definition()
        step_info = definition.get_step_info(main_step)
        if not step_info or not step_info.substeps:
            return False, f"Step '{main_step}' não tem substeps"

        # Verificar se o substep existe (suporta dot notation)
        if "." in substep_name:
            # Dot notation - usar find_step_by_path
            substep_info = step_info.find_step_by_path(substep_name)
        else:
            # Substep direto
            substep_info = None
            for sub in step_info.substeps:
                if sub.name == substep_name:
                    substep_info = sub
                    break

        if not substep_info:
            return False, f"Substep '{substep_name}' não encontrado em '{main_step}'"

        # Validar o valor do substep
        if not payload or not payload.strip():
            return False, f"{substep_name} não pode estar vazio"

        # Validações específicas para cada substep
        is_valid, error_msg = self._validate_substep_value(
            main_step, substep_name, payload.strip()
        )
        if not is_valid:
            return False, error_msg

        # Inicializar estrutura de dados temporária para substeps
        temp_key = f"__{main_step}_substeps"
        if temp_key not in self.data:
            self.data[temp_key] = {}

        # Salvar o substep usando dot notation se necessário
        self.data[temp_key][substep_name] = payload.strip()

        # Verificar se todos os substeps obrigatórios estão completos
        required_paths = self._get_all_required_paths(step_info)
        completed_paths = set(self.data[temp_key].keys())

        if all(req_path in completed_paths for req_path in required_paths):
            # Todos obrigatórios completos - montar estrutura nested final
            nested_data = self._build_nested_structure(self.data[temp_key], step_info)

            # Validar estrutura final se necessário
            if main_step == "user_info":
                json_str = json.dumps(nested_data, ensure_ascii=False)
                is_valid, error_msg = self._validate_user_info(json_str)
                if not is_valid:
                    return False, error_msg

            # Salvar estrutura final e limpar temporários
            self.data[main_step] = nested_data
            del self.data[temp_key]

        return True, ""

    def _get_all_required_paths(self, step_info: StepInfo, prefix: str = "") -> List[str]:
        """Obter todos os paths obrigatórios recursivamente (apenas leaf nodes)"""
        required_paths = []

        if step_info.substeps:
            for substep in step_info.substeps:
                current_path = f"{prefix}.{substep.name}" if prefix else substep.name

                if substep.required:
                    # Se tem substeps, não adicionar este path, apenas os leaf nodes
                    if substep.substeps:
                        # Recursivamente para sub-substeps
                        required_paths.extend(
                            self._get_all_required_paths(substep, current_path)
                        )
                    else:
                        # É um leaf node - adicionar
                        required_paths.append(current_path)

        return required_paths

    def _build_nested_structure(self, flat_data: Dict[str, str], step_info: StepInfo) -> Dict[str, Any]:
        """Constrói estrutura nested a partir de dados flat com dot notation"""
        result = {}

        for path, value in flat_data.items():
            parts = path.split(".")
            current = result

            # Navegar até o nível correto
            for part in parts[:-1]:
                if part not in current:
                    current[part] = {}
                current = current[part]

            # Definir valor final, convertendo tipo se necessário
            final_value = self._convert_value_type(value, path, step_info)
            current[parts[-1]] = final_value

        return result

    def _convert_value_type(self, value: str, path: str, step_info: StepInfo) -> Any:
        """Converte valor baseado no payload_example do substep"""
        # Encontrar o substep correspondente ao path para verificar o tipo esperado
        substep_info = step_info.find_step_by_path(path)

        if substep_info and substep_info.payload_example:
            example_value = list(substep_info.payload_example.values())[0]

            # Tentar converter para o tipo do exemplo
            if isinstance(example_value, int):
                try:
                    return int(value)
                except ValueError:
                    pass
            elif isinstance(example_value, float):
                try:
                    return float(value)
                except ValueError:
                    pass
            elif isinstance(example_value, bool):
                return value.lower() in ('true', '1', 'yes', 'on')

        # Default para string
        return value

    def _validate_substep_value(
        self, main_step: str, substep_name: str, value: str
    ) -> Tuple[bool, str]:
        """Valida valores específicos de substeps"""
        if main_step == "user_info":
            if substep_name == "name":
                if len(value) < 2:
                    return False, "Nome deve ter pelo menos 2 caracteres"

            elif substep_name == "document_number":
                doc_clean = value.replace(".", "").replace("-", "").replace("/", "")
                if not doc_clean.isdigit() or len(doc_clean) not in [11, 14]:
                    return (
                        False,
                        "Documento deve ter 11 dígitos (CPF) ou 14 dígitos (CNPJ)",
                    )

            elif substep_name == "email":
                if "@" not in value or "." not in value:
                    return False, "Email deve ter formato válido"

            elif substep_name == "document_type":
                if value.upper() not in ["CPF", "CNPJ"]:
                    return False, "Tipo de documento deve ser 'CPF' ou 'CNPJ'"

        return True, ""

    def _is_partial_substeps(self, step: str, data: Dict[str, Any]) -> bool:
        """Detecta se os dados são substeps parciais ou dados completos"""
        definition = self.get_service_definition()
        step_info = definition.get_step_info(step)

        if not step_info or not step_info.substeps:
            return False

        # Obter nomes dos substeps
        substep_names = {substep.name for substep in step_info.substeps}
        data_keys = set(data.keys())

        # Se todas as chaves são substeps válidos mas não são todos os obrigatórios,
        # então é um conjunto parcial
        if data_keys.issubset(substep_names):
            required_substeps = {
                substep.name for substep in step_info.substeps if substep.required
            }
            # É parcial se não tem todos os obrigatórios
            return not required_substeps.issubset(data_keys)

        return False

    def _handle_partial_substeps(
        self, step: str, data: Dict[str, Any]
    ) -> Tuple[bool, str]:
        """Manipula substeps parciais - acumula dados e valida individualmente"""
        # Inicializar step se não existir
        if step not in self.data:
            self.data[step] = {}

        # Validar cada substep individualmente
        for substep_name, substep_value in data.items():
            is_valid, error_msg = self._validate_substep_value(
                step, substep_name, str(substep_value)
            )
            if not is_valid:
                return False, error_msg

            # Salvar substep se válido
            self.data[step][substep_name] = substep_value

        return True, ""

    def _handle_dict_step(self, step: str, payload: str) -> Tuple[bool, str]:
        """
        Manipula steps com dict (detectado pelo payload_example) - valida JSON e salva como dicionário.
        Detecta automaticamente se são substeps parciais ou JSON completo.
        """
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            return False, f"{step} deve ser um JSON válido"

        if not isinstance(data, dict):
            return False, f"{step} deve ser um objeto JSON"

        # Detectar se é um conjunto parcial de substeps ou dados completos
        if step == "user_info" and self._is_partial_substeps(step, data):
            # É um conjunto parcial de substeps - acumular
            return self._handle_partial_substeps(step, data)

        # Validação específica baseada no step (dados completos)
        if step == "user_info":
            is_valid, error_msg = self._validate_user_info(payload)
        elif step == "account_info":
            is_valid, error_msg = self._validate_account_info(payload)
        elif step == "address":
            is_valid, error_msg = self._validate_address(payload)
        elif step == "contact":
            is_valid, error_msg = self._validate_contact(payload)
        else:
            # Validação genérica para outros steps dict
            is_valid, error_msg = True, ""

        if is_valid:
            self.data[step] = data

        return is_valid, error_msg

    def _handle_string_step(self, step: str, payload: str) -> Tuple[bool, str]:
        """
        Manipula steps com string (detectado pelo payload_example) - salva como string.
        """
        if not payload or not payload.strip():
            return False, f"{step} não pode estar vazio"

        # Validação específica pode ser adicionada aqui baseada no step
        self.data[step] = payload.strip()
        return True, ""

    def _validate_single_deposit(
        self, deposit: Dict[str, Any], index: int
    ) -> Tuple[bool, str]:
        """Valida um único depósito"""
        if not isinstance(deposit, dict):
            return False, f"Depósito {index} deve ser um objeto JSON"

        if "amount" not in deposit:
            return False, f"Campo 'amount' obrigatório no depósito {index}"

        # amount pode ser float ou string numérica
        try:
            amount = float(deposit["amount"])
            if amount <= 0:
                return False, f"Amount no depósito {index} deve ser positivo"
        except (ValueError, TypeError):
            return False, f"Amount no depósito {index} deve ser numérico"

        if "date" not in deposit:
            return False, f"Campo 'date' obrigatório no depósito {index}"

        # Validar formato de data ISO
        try:
            datetime.fromisoformat(deposit["date"].replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            return (
                False,
                f"Date no depósito {index} deve estar em formato ISO (YYYY-MM-DDTHH:MM:SS)",
            )

        return True, ""

    def _validate_user_info(self, payload: str) -> Tuple[bool, str]:
        """Valida estrutura user_info com suporte a nested structure"""
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            return False, "user_info deve ser um JSON válido"

        # Verificar se tem estrutura nested ou flat
        if "document" in data and isinstance(data["document"], dict):
            # Nova estrutura nested
            return self._validate_nested_user_info(data)
        else:
            # Estrutura flat (backward compatibility)
            return self._validate_flat_user_info(data)

    def _validate_flat_user_info(self, data: Dict[str, Any]) -> Tuple[bool, str]:
        """Valida estrutura user_info flat (compatibilidade)"""
        required_fields = ["name", "document_number", "email", "document_type"]
        for field in required_fields:
            if field not in data:
                return False, f"Campo obrigatório '{field}' ausente em user_info"
            if not isinstance(data[field], str) or not data[field].strip():
                return False, f"Campo '{field}' deve ser uma string não vazia"

        # Validações específicas
        if data["document_type"] not in ["CPF", "CNPJ"]:
            return False, "document_type deve ser 'CPF' ou 'CNPJ'"

        # Validar CPF/CNPJ
        doc_num = (
            data["document_number"].replace(".", "").replace("-", "").replace("/", "")
        )
        if data["document_type"] == "CPF" and len(doc_num) != 11:
            return False, "CPF deve ter 11 dígitos"
        elif data["document_type"] == "CNPJ" and len(doc_num) != 14:
            return False, "CNPJ deve ter 14 dígitos"

        # Validar email básico
        if "@" not in data["email"] or "." not in data["email"]:
            return False, "Email deve ter formato válido"

        return True, ""

    def _validate_nested_user_info(self, data: Dict[str, Any]) -> Tuple[bool, str]:
        """Valida estrutura user_info nested"""
        # Validar name
        if "name" not in data or not isinstance(data["name"], str) or not data["name"].strip():
            return False, "Campo obrigatório 'name' ausente ou inválido em user_info"

        # Validar document structure
        if "document" not in data or not isinstance(data["document"], dict):
            return False, "Campo obrigatório 'document' ausente em user_info"
        
        document = data["document"]
        if "number" not in document or not isinstance(document["number"], str) or not document["number"].strip():
            return False, "Campo obrigatório 'document.number' ausente ou inválido"
        
        if "type" not in document or not isinstance(document["type"], str) or not document["type"].strip():
            return False, "Campo obrigatório 'document.type' ausente ou inválido"

        if document["type"] not in ["CPF", "CNPJ"]:
            return False, "document.type deve ser 'CPF' ou 'CNPJ'"

        # Validar CPF/CNPJ
        doc_num = document["number"].replace(".", "").replace("-", "").replace("/", "")
        if document["type"] == "CPF" and len(doc_num) != 11:
            return False, "CPF deve ter 11 dígitos"
        elif document["type"] == "CNPJ" and len(doc_num) != 14:
            return False, "CNPJ deve ter 14 dígitos"

        # Validar contact structure  
        if "contact" not in data or not isinstance(data["contact"], dict):
            return False, "Campo obrigatório 'contact' ausente em user_info"
        
        contact = data["contact"]
        if "email" not in contact or not isinstance(contact["email"], str) or not contact["email"].strip():
            return False, "Campo obrigatório 'contact.email' ausente ou inválido"

        # Validar email básico
        if "@" not in contact["email"] or "." not in contact["email"]:
            return False, "Email deve ter formato válido"

        # Validar address structure
        if "address" not in data or not isinstance(data["address"], dict):
            return False, "Campo obrigatório 'address' ausente em user_info"
        
        address = data["address"]
        if "street" not in address or not isinstance(address["street"], str) or not address["street"].strip():
            return False, "Campo obrigatório 'address.street' ausente ou inválido"
        
        if "number" not in address:
            return False, "Campo obrigatório 'address.number' ausente"

        return True, ""

    def _validate_account_info(self, payload: str) -> Tuple[bool, str]:
        """Valida estrutura account_info"""
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            return False, "account_info deve ser um JSON válido"

        required_fields = [
            "account_type",
            "bank_name",
            "agency_number",
            "account_number",
        ]
        for field in required_fields:
            if field not in data:
                return False, f"Campo obrigatório '{field}' ausente em account_info"
            if not isinstance(data[field], str) or not data[field].strip():
                return False, f"Campo '{field}' deve ser uma string não vazia"

        # Validações específicas
        if data["account_type"] not in ["corrente", "poupança", "investimento"]:
            return (
                False,
                "account_type deve ser 'corrente', 'poupança' ou 'investimento'",
            )

        # Validar números da agência e conta
        if not data["agency_number"].isdigit():
            return False, "agency_number deve conter apenas números"

        account_clean = data["account_number"].replace("-", "")
        if not account_clean.isdigit():
            return False, "account_number deve conter apenas números e hífen"

        return True, ""

    def _validate_address(self, payload: str) -> Tuple[bool, str]:
        """Valida estrutura address"""
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            return False, "address deve ser um JSON válido"
        if (
            "street" not in data
            or not isinstance(data["street"], str)
            or not data["street"].strip()
        ):
            return False, "Campo 'street' obrigatório e deve ser string não vazia"

        if "number" not in data:
            return False, "Campo 'number' obrigatório"
        data["number"] = int(data["number"])
        # number pode ser int ou string numérica
        if isinstance(data["number"], str):
            if not data["number"].isdigit():
                return False, "Campo 'number' deve ser numérico"
        elif not isinstance(data["number"], int):
            return False, "Campo 'number' deve ser número inteiro"

        return True, ""

    def _validate_contact(self, payload: str) -> Tuple[bool, str]:
        """Valida estrutura contact"""
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            return False, "contact deve ser um JSON válido"

        required_fields = ["email", "phone"]
        for field in required_fields:
            if field not in data:
                return False, f"Campo obrigatório '{field}' ausente em contact"
            if not isinstance(data[field], str) or not data[field].strip():
                return False, f"Campo '{field}' deve ser uma string não vazia"

        # Validar email
        if "@" not in data["email"] or "." not in data["email"]:
            return False, "Email deve ter formato válido"

        # Validar telefone (apenas dígitos)
        phone_clean = (
            data["phone"]
            .replace("(", "")
            .replace(")", "")
            .replace("-", "")
            .replace(" ", "")
        )
        if not phone_clean.isdigit():
            return False, "Phone deve conter apenas números"

        if len(phone_clean) < 10 or len(phone_clean) > 11:
            return False, "Phone deve ter 10 ou 11 dígitos"

        return True, ""

    def get_completion_message(self) -> str:
        """Mensagem de conclusão do serviço"""
        return f"🎉 Conta bancária avançada criada com sucesso! Dados estruturados processados para usuário {self.user_id}."

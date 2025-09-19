import re
import json
from typing import Dict, Any, List, Optional, Tuple, Literal
from pydantic import BaseModel, Field, field_validator, computed_field


class ConditionalDependency(BaseModel):
    """Model for conditional dependencies between steps"""

    if_condition: Dict[str, Any] = Field(..., description="Condition that must be met")
    then_required: List[str] = Field(
        default_factory=list, description="Steps required if condition is met"
    )
    else_required: List[str] = Field(
        default_factory=list, description="Steps required if condition is not met"
    )


class StepInfo(BaseModel):
    """Pydantic model for step information with dependencies"""

    name: str = Field(..., description="Unique step name", min_length=1)
    description: str = Field(..., description="Step description", min_length=1)
    example: Optional[str] = Field(None, description="Example input")
    required: bool = Field(True, description="Whether this step is required")

    # Dependency system (all optional)
    depends_on: List[str] = Field(
        default_factory=list, description="Steps that must be completed before this one"
    )
    conflicts_with: List[str] = Field(
        default_factory=list, description="Steps that cannot coexist with this one"
    )
    conditional: Optional[ConditionalDependency] = Field(
        default=None, description="Conditional dependency rules"
    )

    # New features for advanced steps
    substeps: Optional[List["StepInfo"]] = Field(
        default=None, description="Substeps that compose this step (StepInfo instances)"
    )
    data_type: Literal["str", "dict", "list", "list_dict"] = Field(
        default="str",
        description="Expected data type: str, dict, list, list_dict",
    )
    validation_depends_on: List[str] = Field(
        default_factory=list, description="Steps whose data is needed for validation"
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", v):
            raise ValueError("Step name must be a valid identifier")
        return v

    @field_validator("depends_on", "conflicts_with", "validation_depends_on")
    @classmethod
    def validate_step_lists(cls, v: List[str]) -> List[str]:
        for step in v:
            if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", step):
                raise ValueError(f"Invalid step name: {step}")
        return v

    @field_validator("data_type")
    @classmethod
    def validate_data_type(cls, v: str) -> str:
        valid_types = ["str", "dict", "list", "list_dict"]
        if v not in valid_types:
            raise ValueError(f"data_type must be one of {valid_types}")
        return v


class ServiceDefinition(BaseModel):
    """
    Single source of truth for service configuration.
    Eliminates redundancy between schema, steps_info, and available_steps.
    """

    service_name: str = Field(..., description="Name of the service")
    description: str = Field(..., description="Service description")
    steps: List[StepInfo] = Field(..., description="Complete step definitions")

    @computed_field
    @property
    def json_schema(self) -> Dict[str, Any]:
        """Auto-generated JSON schema from steps"""
        properties = {}
        required = []

        for step in self.steps:
            properties[step.name] = {"type": "string", "description": step.description}
            if step.example:
                properties[step.name]["example"] = step.example

            if step.required:
                required.append(step.name)

        return {"type": "object", "properties": properties, "required": required}

    @computed_field
    @property
    def step_names(self) -> List[str]:
        """List of all step names"""
        return [step.name for step in self.steps]

    def get_available_steps(self, completed_data: Dict[str, Any]) -> List[str]:
        """Calculate available steps based on current state and dependencies"""
        # Para steps com substeps, verificar se todos os substeps obrigatórios estão completos
        truly_completed_steps = set()
        for step_name, step_data in completed_data.items():
            step_info = self.get_step_info(step_name)
            if step_info and step_info.substeps:
                # Verificar se todos os substeps obrigatórios estão presentes
                if isinstance(step_data, dict):
                    required_substeps = [sub.name for sub in step_info.substeps if sub.required]
                    if all(sub in step_data for sub in required_substeps):
                        truly_completed_steps.add(step_name)
                    # Se não tem todos os substeps obrigatórios, o step ainda está disponível
                else:
                    # Se não é dict, algo está errado - considerar não completo
                    pass
            else:
                # Step sem substeps - considerar completo normalmente
                truly_completed_steps.add(step_name)
        
        available = []

        for step in self.steps:
            # Check if already completed (considerando substeps)
            if step.name in truly_completed_steps:
                continue

            # Check basic dependencies
            if step.depends_on and not all(
                dep in truly_completed_steps for dep in step.depends_on
            ):
                continue

            # Check conflicts
            if step.conflicts_with and any(
                conflict in truly_completed_steps for conflict in step.conflicts_with
            ):
                continue

            # Check conditional dependencies
            if step.conditional:
                condition_met = self._evaluate_condition(
                    step.conditional.if_condition, completed_data
                )
                required_deps = (
                    step.conditional.then_required
                    if condition_met
                    else step.conditional.else_required
                )

                if required_deps and not all(
                    dep in truly_completed_steps for dep in required_deps
                ):
                    continue

            available.append(step.name)

        return available

    def _evaluate_condition(
        self, condition: Dict[str, Any], data: Dict[str, Any]
    ) -> bool:
        """Evaluate a condition against current data"""
        for field, expected_value in condition.items():
            if field not in data or data[field] != expected_value:
                return False
        return True

    def get_step_info(self, step_name: str) -> Optional[StepInfo]:
        """Get specific step information by name"""
        for step in self.steps:
            if step.name == step_name:
                return step
        return None

    def get_steps_schematic(
        self, completed_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Retorna um esquemático visual dos steps do serviço com dependências e status.

        Args:
            completed_data: Dados já completados para mostrar status atual (opcional)

        Returns:
            Dict com informações estruturadas dos steps incluindo:
            - Lista de steps com suas propriedades
            - Mapa de dependências
            - Status atual se completed_data fornecido
            - Visualização em árvore das dependências
        """
        completed_data = completed_data or {}

        # Informações básicas de cada step
        steps_info = []
        for step in self.steps:
            step_data = {
                "name": step.name,
                "description": step.description,
                "required": step.required,
                "depends_on": step.depends_on,
                "conflicts_with": step.conflicts_with,
                "example": getattr(step, "example", None),
            }

            # Adicionar status se completed_data fornecido
            if completed_data is not None:
                if step.name in completed_data:
                    step_data["status"] = "completed"
                    step_data["value"] = completed_data[step.name]
                else:
                    available_steps = self.get_available_steps(completed_data)
                    if step.name in available_steps:
                        if step.required or self._is_conditionally_required(
                            step, completed_data
                        ):
                            step_data["status"] = "available_required"
                        else:
                            step_data["status"] = "available_optional"
                    else:
                        step_data["status"] = "pending"

            # Informações condicionais
            if step.conditional:
                step_data["conditional"] = {
                    "if_condition": step.conditional.if_condition,
                    "then_required": step.conditional.then_required,
                    "else_required": step.conditional.else_required,
                }

                # Se temos dados, avaliar a condição atual
                if completed_data:
                    condition_met = self._evaluate_condition(
                        step.conditional.if_condition, completed_data
                    )
                    step_data["conditional"]["current_condition_met"] = condition_met
                    step_data["conditional"]["current_required_deps"] = (
                        step.conditional.then_required
                        if condition_met
                        else step.conditional.else_required
                    )

            steps_info.append(step_data)

        # Mapa de dependências (quem depende de quem)
        dependency_map = {}
        for step in self.steps:
            if step.depends_on:
                dependency_map[step.name] = step.depends_on

        # Mapa reverso (quem é dependência de quem)
        reverse_dependency_map = {}
        for step in self.steps:
            reverse_dependency_map[step.name] = []

        for step_name, deps in dependency_map.items():
            for dep in deps:
                if dep in reverse_dependency_map:
                    reverse_dependency_map[dep].append(step_name)

        # Análise de estado se dados fornecidos
        state_analysis = None
        if completed_data:
            state_analysis = self.get_state_analysis(completed_data)

        # Árvore de dependências visual
        dependency_tree = self._build_dependency_tree()

        return {
            "service_name": self.service_name,
            "description": self.description,
            "total_steps": len(self.steps),
            "steps": steps_info,
            "dependency_map": dependency_map,
            "reverse_dependency_map": reverse_dependency_map,
            "dependency_tree": dependency_tree,
            "state_analysis": state_analysis,
        }

    def _build_dependency_tree(self) -> List[Dict[str, Any]]:
        """Constrói árvore visual de dependências"""
        # Encontrar steps raiz (sem dependências)
        root_steps = [step for step in self.steps if not step.depends_on]

        def build_node(step: StepInfo, visited: Optional[set] = None) -> Dict[str, Any]:
            if visited is None:
                visited = set()

            if step.name in visited:
                return {"name": step.name, "circular": True}

            visited.add(step.name)

            # Encontrar steps que dependem deste
            children = []
            for other_step in self.steps:
                if step.name in other_step.depends_on:
                    children.append(build_node(other_step, visited.copy()))

            node = {
                "name": step.name,
                "description": step.description,
                "required": step.required,
                "children": children,
            }

            if step.conditional:
                node["conditional"] = True

            return node

        return [build_node(step) for step in root_steps]

    def get_visual_schematic(
        self, completed_data: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Retorna representação visual em texto dos steps e dependências.
        Formato amigável para leitura humana.
        """
        completed_data = completed_data or {}
        schematic = self.get_steps_schematic(completed_data)

        lines = []
        lines.append(f"📋 {schematic['service_name'].upper()}")
        lines.append(f"   {schematic['description']}")
        lines.append(f"   Total: {schematic['total_steps']} steps")
        lines.append("")

        # Status legend se temos dados
        if completed_data:
            lines.append("🎯 STATUS:")
            analysis = schematic["state_analysis"]
            if analysis:
                lines.append(f"   ✅ Completed: {len(analysis['completed_steps'])}")
                lines.append(f"   🟡 Available: {len(analysis['available_steps'])}")
                lines.append(f"   ⏳ Pending: {len(analysis['pending_steps'])}")
                lines.append(
                    f"   📊 Progress: {analysis['progress']['percentage']:.1f}%"
                )
            lines.append("")

        # Dependency tree visual
        lines.append("🌳 DEPENDENCY TREE:")
        tree = schematic["dependency_tree"]
        for root in tree:
            lines.extend(self._render_tree_node(root, completed_data))
        lines.append("")

        # Steps summary com status
        lines.append("📝 STEPS SUMMARY:")
        steps_by_status = {}
        for step in schematic["steps"]:
            status = step.get("status", "unknown")
            if status not in steps_by_status:
                steps_by_status[status] = []
            steps_by_status[status].append(step)

        status_icons = {
            "completed": "✅",
            "available_required": "🔴",
            "available_optional": "🟡",
            "pending": "⏳",
            "unknown": "❓",
        }

        for status, steps in steps_by_status.items():
            if steps:
                icon = status_icons.get(status, "❓")
                status_name = status.replace("_", " ").title()
                lines.append(f"   {icon} {status_name}:")
                for step in steps:
                    value_info = (
                        f" = {step.get('value', '')}" if step.get("value") else ""
                    )
                    conditional_info = (
                        " (conditional)" if step.get("conditional") else ""
                    )
                    
                    # Verificar se tem substeps para mostrar detalhes
                    step_info = self.get_step_info(step['name'])
                    substeps_info = ""
                    if step_info and step_info.substeps and step.get('value'):
                        # Mostrar status dos substeps
                        step_data = step.get('value', {})
                        if isinstance(step_data, dict):
                            required_substeps = [sub.name for sub in step_info.substeps if sub.required]
                            completed_substeps = [sub for sub in required_substeps if sub in step_data]
                            missing_substeps = [sub for sub in required_substeps if sub not in step_data]
                            
                            if missing_substeps:
                                substeps_info = f" (faltam: {', '.join(missing_substeps)})"
                            elif completed_substeps:
                                substeps_info = f" (substeps: {', '.join(completed_substeps)})"
                    
                    lines.append(
                        f"      • {step['name']}{value_info} - {step['description']}{conditional_info}{substeps_info}"
                    )
                lines.append("")

        return "\n".join(lines)

    def _render_tree_node(
        self,
        node: Dict[str, Any],
        completed_data: Dict[str, Any],
        prefix: str = "",
        is_last: bool = True,
    ) -> List[str]:
        """Renderiza um nó da árvore com formatação ASCII"""
        lines = []

        # Determinar ícone baseado no status
        node_name = node["name"]
        if node_name in completed_data:
            icon = "✅"
            status = f" = {completed_data[node_name]}"
        elif node.get("required", False):
            icon = "🔴"
            status = " (required)"
        else:
            icon = "🟡" if not node.get("conditional") else "🔄"
            status = " (optional)" + (" conditional" if node.get("conditional") else "")

        # Conectores da árvore
        connector = "└── " if is_last else "├── "

        # Linha do nó atual
        lines.append(f"{prefix}{connector}{icon} {node_name}{status}")

        # Obter filhos primeiro
        children = node.get("children", [])

        # Renderizar substeps se existirem (antes dos filhos normais)
        substep_lines = []
        if node_name in completed_data:
            step_info = self.get_step_info(node_name)
            if step_info and step_info.substeps:
                step_data = completed_data[node_name]
                if isinstance(step_data, dict):
                    # Novo prefixo para substeps
                    substep_prefix = prefix + ("    " if is_last else "│   ")
                    
                    required_substeps = [s for s in step_info.substeps if s.required]
                    
                    for i, substep in enumerate(required_substeps):
                        substep_name = substep.name
                        if substep_name in step_data:
                            substep_icon = "✅"
                            substep_status = f" = {step_data[substep_name]}"
                        else:
                            substep_icon = "🔴"
                            substep_status = " (required)"
                        
                        # Determinar se é o último item considerando filhos normais
                        is_last_substep = (i == len(required_substeps) - 1) and not children
                        substep_connector = "└── " if is_last_substep else "├── "
                        
                        substep_lines.append(f"{substep_prefix}{substep_connector}{substep_icon} {substep_name}{substep_status}")

        # Adicionar substeps às linhas
        lines.extend(substep_lines)

        # Renderizar filhos
        
        if children:
            # Novo prefixo para filhos
            child_prefix = prefix + ("    " if is_last else "│   ")

            for i, child in enumerate(children):
                is_last_child = i == len(children) - 1
                lines.extend(
                    self._render_tree_node(
                        child, completed_data, child_prefix, is_last_child
                    )
                )

        return lines

    def get_state_analysis(self, completed_data: Dict[str, Any]) -> Dict[str, Any]:
        """Análise completa do estado atual do serviço"""
        all_steps = {step.name: step for step in self.steps}
        completed_steps = list(completed_data.keys())
        available_steps = self.get_available_steps(completed_data)

        # Classificar steps disponíveis
        required_available = []
        optional_available = []
        for step_name in available_steps:
            step = all_steps[step_name]
            if step.required or self._is_conditionally_required(step, completed_data):
                required_available.append(step_name)
            else:
                optional_available.append(step_name)

        # Steps ainda pendentes (não disponíveis por dependências)
        pending_steps = []
        for step in self.steps:
            if step.name not in completed_steps and step.name not in available_steps:
                pending_steps.append(step.name)

        total_steps = len(self.steps)
        completed_count = len(completed_steps)

        return {
            "completed_steps": completed_steps,
            "available_steps": available_steps,
            "required_steps": required_available,
            "optional_steps": optional_available,
            "pending_steps": pending_steps,
            "progress": {
                "completed": completed_count,
                "available": len(available_steps),
                "pending": len(pending_steps),
                "total": total_steps,
                "percentage": (
                    round((completed_count / total_steps) * 100, 1)
                    if total_steps > 0
                    else 0
                ),
                "completion_estimate": self._estimate_completion(
                    completed_count, total_steps
                ),
            },
        }

    def get_contextual_schema(self, completed_data: Dict[str, Any]) -> Dict[str, Any]:
        """Schema dinâmico baseado no estado atual - apenas steps principais com substeps estruturados"""
        available_steps = self.get_available_steps(completed_data)
        schema = {"type": "object", "properties": {}, "required": []}

        for step_name in available_steps:
            step_info = self.get_step_info(step_name)
            if step_info:
                # Criar schema para o step principal
                step_schema = {
                    "type": "string", 
                    "description": step_info.description,
                    "data_type": step_info.data_type
                }
                
                if step_info.example:
                    step_schema["example"] = step_info.example

                # Se tem substeps, adicionar informações dos substeps e instruções de formato
                if step_info.substeps:
                    # Substeps é um campo especial - não vai para type: string
                    substeps_info = [
                        {
                            "step": substep.name,
                            "type": "string",
                            "description": substep.description,
                            "example": substep.example,
                            "data_type": substep.data_type,
                            "required": substep.required
                        }
                        for substep in step_info.substeps
                    ]
                    step_schema["substeps"] = substeps_info
                    
                    # Gerar instruções de formato dinamicamente
                    step_schema["format_instructions"] = self._generate_format_instructions(step_info)

                # Add to required array if this step is required
                if step_info.required or self._is_conditionally_required(
                    step_info, completed_data
                ):
                    schema["required"].append(step_name)

                schema["properties"][step_name] = step_schema

        return schema

    def _generate_format_instructions(self, step_info: StepInfo) -> str:
        """Gera instruções de formato dinamicamente baseado nos substeps"""
        if not step_info.substeps:
            return ""
        
        # Gerar exemplo de payload estruturado
        example_payload = {}
        for substep in step_info.substeps:
            if substep.example:
                example_payload[substep.name] = substep.example
            else:
                example_payload[substep.name] = f"<{substep.name}>"
        
        # Formato para individual substeps
        individual_examples = []
        for substep in step_info.substeps:
            example_val = substep.example or f"<{substep.name}>"
            individual_examples.append(f'{{"{substep.name}": "{example_val}"}}')
        
        instructions = f"""
FORMATOS ACEITOS:

1. Individual substeps (detectados automaticamente):
   {' ou '.join(individual_examples)}

2. JSON completo:
   {{"{step_info.name}": {json.dumps(example_payload, ensure_ascii=False)}}}

3. Múltiplos substeps:
   {json.dumps(example_payload, ensure_ascii=False)}
"""
        return instructions.strip()

    def _detect_substep_parent(self, field_name: str) -> Optional[str]:
        """Detecta qual step principal contém o substep especificado"""
        for step_info in self.steps:
            if step_info.substeps:
                for substep in step_info.substeps:
                    if substep.name == field_name:
                        return step_info.name
        return None

    def get_state_summary(self, completed_data: Dict[str, Any]) -> str:
        """Resumo em linguagem natural do estado atual"""
        analysis = self.get_state_analysis(completed_data)

        if not completed_data:
            return f"Iniciando {self.service_name}. Escolha os primeiros campos disponíveis."

        completed_desc = ", ".join(analysis["completed_steps"])
        required_desc = ", ".join(analysis["required_steps"])

        summary = f"Concluído: {completed_desc}. "
        if required_desc:
            summary += f"Próximos obrigatórios: {required_desc}. "
        if analysis["optional_steps"]:
            summary += f"Opcionais disponíveis: {len(analysis['optional_steps'])}. "

        return summary

    def get_next_action_suggestion(self, completed_data: Dict[str, Any]) -> str:
        """Sugestão específica do que fazer a seguir"""
        analysis = self.get_state_analysis(completed_data)

        if analysis["required_steps"]:
            if len(analysis["required_steps"]) == 1:
                step_name = analysis["required_steps"][0]
                step_info = self.get_step_info(step_name)
                if step_info:
                    base_desc = step_info.description.lower()
                    example_part = (
                        f" (ex: {step_info.example})" if step_info.example else ""
                    )
                    return f"Forneça {base_desc}{example_part}"
                else:
                    return f"Forneça {step_name}"
            else:
                return f"Forneça qualquer um dos campos obrigatórios: {', '.join(analysis['required_steps'])}"
        elif analysis["optional_steps"]:
            return f"Todos campos obrigatórios concluídos. Opcionalmente: {', '.join(analysis['optional_steps'])}"
        else:
            return "Pronto para finalizar o serviço."

    def _is_conditionally_required(
        self, step: StepInfo, completed_data: Dict[str, Any]
    ) -> bool:
        """Verifica se um step se tornou obrigatório baseado em condições"""
        if not step.conditional:
            return False

        # Para initial_deposit: se account_type = "corrente", então é obrigatório
        condition_met = self._evaluate_condition(
            step.conditional.if_condition, completed_data
        )

        # Se a condição é atendida e o step está na lista then_required, é obrigatório
        # Ou se a condição não é atendida e está na lista else_required, é obrigatório
        required_steps = (
            step.conditional.then_required
            if condition_met
            else step.conditional.else_required
        )
        is_in_required_list = step.name in required_steps

        # Para steps como initial_deposit, se a condição é "account_type: corrente"
        # e está atendida, o step se torna obrigatório mesmo se não estiver na lista
        if step.name == "initial_deposit" and condition_met:
            return True

        return is_in_required_list

    def _estimate_completion(self, completed: int, total: int) -> str:
        """Estimativa de conclusão baseada no progresso"""
        if total == 0:
            return "Concluído"

        remaining = total - completed
        if remaining == 0:
            return "Concluído"
        elif remaining == 1:
            return "1 campo restante"
        elif remaining <= 3:
            return f"{remaining} campos restantes"
        else:
            return f"{remaining} campos restantes"

    def _get_step_contextual_schema(
        self, step_name: str, completed_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Schema específico baseado no contexto atual - pode ser sobrescrito pelos services"""
        # Implementação base - services podem sobrescrever para contexto específico
        # Suprime warnings sobre parâmetros não usados
        _ = step_name, completed_data
        return {}

    def validate_dependencies(
        self, step_name: str, completed_data: Dict[str, Any]
    ) -> Tuple[bool, str]:
        """Validate if step dependencies are satisfied"""
        step_info = self.get_step_info(step_name)
        if not step_info:
            return False, f"Step '{step_name}' not found"

        # Check direct dependencies
        for dep in step_info.depends_on:
            if dep not in completed_data:
                return (
                    False,
                    f"Step '{step_name}' requires '{dep}' to be completed first",
                )

        # Check conflicts
        for conflict in step_info.conflicts_with:
            if conflict in completed_data:
                return (
                    False,
                    f"Step '{step_name}' conflicts with already completed step '{conflict}'",
                )

        # Check conditional dependencies
        if step_info.conditional:
            condition_met = self._evaluate_condition(
                step_info.conditional.if_condition, completed_data
            )
            required_steps = (
                step_info.conditional.then_required
                if condition_met
                else step_info.conditional.else_required
            )

            for req_step in required_steps:
                if req_step not in completed_data:
                    return (
                        False,
                        f"Step '{step_name}' requires '{req_step}' based on current conditions",
                    )

        return True, ""

    def get_next_required_step(self, completed_data: Dict[str, Any]) -> Optional[str]:
        """Get the next required step based on dependencies"""
        available = self.get_available_steps(completed_data)

        # Filter for required steps only
        for step in self.steps:
            if step.name in available and (
                step.required or self._is_conditionally_required(step, completed_data)
            ):
                return step.name

        # If no required steps, return first available
        return available[0] if available else None

    def get_processing_order(self, steps: List[str]) -> List[str]:
        """Get processing order based on dependencies (topological sort)"""
        # Simple implementation - can be enhanced with proper topological sort
        ordered = []
        remaining = list(steps)

        while remaining:
            # Find steps with no unmet dependencies in remaining list
            ready = []
            for step in remaining:
                step_info = self.get_step_info(step)
                if step_info:
                    deps_in_remaining = [
                        dep for dep in step_info.depends_on if dep in remaining
                    ]
                    if not deps_in_remaining:
                        ready.append(step)

            if not ready:
                # Circular dependency or missing dependency - add remaining in original order
                ordered.extend(remaining)
                break

            # Add ready steps and remove from remaining
            ordered.extend(ready)
            for step in ready:
                remaining.remove(step)

        return ordered

    def validate_dependencies_with_temp_data(
        self, step_name: str, temp_data: Dict[str, Any]
    ) -> Tuple[bool, str]:
        """Validate dependencies using temporary data state"""
        step_info = self.get_step_info(step_name)
        if not step_info:
            return False, f"Step '{step_name}' not found"

        # Check direct dependencies
        for dep in step_info.depends_on:
            if dep not in temp_data:
                return (
                    False,
                    f"Step '{step_name}' requires '{dep}' to be completed first",
                )

        # Check conflicts
        for conflict in step_info.conflicts_with:
            if conflict in temp_data:
                return False, f"Step '{step_name}' conflicts with step '{conflict}'"

        return True, ""

    def process_bulk_data(
        self, payload: Dict[str, Any], service_executor
    ) -> Tuple[Dict[str, Any], Dict[str, str], Dict[str, str]]:
        """Process bulk payload with dependency validation - returns (valid_data, field_errors, dependency_errors)"""
        valid_data = {}
        field_errors = {}
        dependency_errors = {}

        # First pass: validate individual steps without dependencies
        # Process both main steps and substeps
        all_possible_steps = set(self.step_names)
        
        # Add substep names to the processing list (com prefixo)
        for step_info in self.steps:
            if step_info.substeps:
                for substep in step_info.substeps:
                    substep_key = f"{step_info.name}_{substep.name}"
                    all_possible_steps.add(substep_key)
        
        # Detectar substeps sem prefixo automaticamente
        payload_to_process = {}
        for field_name, field_value in payload.items():
            if field_name in all_possible_steps:
                # Campo já mapeado (main step ou substep com prefixo)
                payload_to_process[field_name] = field_value
            else:
                # Tentar detectar se é um substep sem prefixo
                detected_substep = self._detect_substep_parent(field_name)
                if detected_substep:
                    # Converter para formato com prefixo
                    prefixed_key = f"{detected_substep}_{field_name}"
                    payload_to_process[prefixed_key] = field_value
                    all_possible_steps.add(prefixed_key)
                else:
                    # Campo não reconhecido - manter original para gerar erro apropriado
                    payload_to_process[field_name] = field_value
        
        for step_name in all_possible_steps:
            if step_name in payload_to_process:
                # Para objetos complexos, usar json.dumps; para strings simples, usar como está
                value = payload_to_process[step_name]
                if isinstance(value, (dict, list)):
                    payload_str = json.dumps(value, ensure_ascii=False)
                else:
                    payload_str = str(value)
                
                is_valid, error_msg = service_executor.execute_step(step_name, payload_str)
                if is_valid:
                    # Substeps não devem ser salvos em valid_data, apenas processados
                    # (eles são gerenciados internamente pelo service)
                    if "_" in step_name and step_name not in self.step_names:
                        # É um substep - não salvar em valid_data
                        pass
                    else:
                        # É um step principal - salvar normalmente
                        if (
                            hasattr(service_executor, "data")
                            and step_name in service_executor.data
                        ):
                            valid_data[step_name] = service_executor.data[step_name]
                        else:
                            valid_data[step_name] = str(payload_to_process[step_name]).strip()
                else:
                    field_errors[step_name] = error_msg

        # Second pass: validate dependencies with combined data (existing + new)
        # Only validate dependencies for main steps, not substeps
        main_steps_to_validate = [step for step in valid_data.keys() if step in self.step_names]
        
        # Get existing service data
        existing_data = getattr(service_executor, "data", {})
        temp_data = dict(existing_data)  # Start with existing data
        processing_order = self.get_processing_order(main_steps_to_validate)

        for step in processing_order:
            if step in valid_data:
                # Add new step to combined data
                temp_data[step] = valid_data[step]
                # Validate dependencies with combined state (existing + new)
                is_dep_valid, dep_error = self.validate_dependencies_with_temp_data(
                    step, temp_data
                )
                if not is_dep_valid:
                    dependency_errors[step] = dep_error
                    # Remove from valid data if dependencies fail
                    valid_data.pop(step, None)
                    temp_data.pop(step, None)  # Remove from temp as well

        return valid_data, field_errors, dependency_errors

    def is_service_completed(self, completed_data: Dict[str, Any]) -> bool:
        """Check if all required steps are completed"""
        required_steps = [
            step.name
            for step in self.steps
            if step.required or self._is_conditionally_required(step, completed_data)
        ]
        return all(step in completed_data for step in required_steps)

    def to_dict(
        self,
        include_state: bool = False,
        completed_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Convert to dictionary with optional state information"""
        result = {
            "service_name": self.service_name,
            "description": self.description,
            "steps": [step.model_dump() for step in self.steps],
            "schema": self.json_schema,
        }

        if include_state and completed_data is not None:
            result["available_steps"] = self.get_available_steps(completed_data)

        return result

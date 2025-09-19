from typing import Dict, Any, List, Optional
from src.services.schema.step_info import StepInfo
from src.services.schema.dependency_engine import DependencyEngine


class VisualizationEngine:
    """Engine for generating visual representations of service state and structure"""

    def __init__(self, service_name: str, description: str, steps: List[StepInfo]):
        self.service_name = service_name
        self.description = description
        self.steps = steps
        self.dependency_engine = DependencyEngine(steps)

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
                    available_steps = self.dependency_engine.get_available_steps(completed_data)
                    if step.name in available_steps:
                        if step.required or self.dependency_engine._is_conditionally_required(
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
                    condition_met = self.dependency_engine._evaluate_condition(
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
        dependency_tree = self.dependency_engine._build_dependency_tree()

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
                    step_info = self.dependency_engine.get_step_info(step['name'])
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

        # Renderizar substeps se existirem (sempre, mesmo sem dados)
        substep_lines = []
        step_info = self.dependency_engine.get_step_info(node_name)
        if step_info and step_info.substeps:
            # Novo prefixo para substeps
            substep_prefix = prefix + ("    " if is_last else "│   ")
            
            # Mostrar todos os substeps, não apenas os obrigatórios
            for i, substep in enumerate(step_info.substeps):
                substep_name = substep.name
                
                # Verificar se há dados completados para este step e substep
                if node_name in completed_data and isinstance(completed_data[node_name], dict):
                    step_data = completed_data[node_name]
                    if substep_name in step_data:
                        substep_icon = "✅"
                        substep_status = f" = {step_data[substep_name]}"
                    else:
                        substep_icon = "🔴" if substep.required else "🟡"
                        substep_status = " (required)" if substep.required else " (optional)"
                else:
                    # Não há dados - mostrar status baseado em required
                    substep_icon = "🔴" if substep.required else "🟡"
                    substep_status = " (required)" if substep.required else " (optional)"
                
                # Determinar se é o último item considerando filhos normais
                is_last_substep = (i == len(step_info.substeps) - 1) and not children
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
        available_steps = self.dependency_engine.get_available_steps(completed_data)

        # Classificar steps disponíveis
        required_available = []
        optional_available = []
        for step_name in available_steps:
            step = all_steps[step_name]
            if step.required or self.dependency_engine._is_conditionally_required(step, completed_data):
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
                step_info = self.dependency_engine.get_step_info(step_name)
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
from typing import Dict, Any, List, Optional, Tuple
from src.services.schema.step_info import StepInfo


class DependencyEngine:
    """Engine for managing and validating step dependencies"""

    def __init__(self, steps: List[StepInfo]):
        self.steps = steps
        self._steps_by_name = {step.name: step for step in steps}

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

    def is_service_completed(self, completed_data: Dict[str, Any]) -> bool:
        """Check if all required steps are completed"""
        required_steps = [
            step.name
            for step in self.steps
            if step.required or self._is_conditionally_required(step, completed_data)
        ]
        return all(step in completed_data for step in required_steps)

    def get_step_info(self, step_name: str) -> Optional[StepInfo]:
        """Get specific step information by name"""
        return self._steps_by_name.get(step_name)

    def _evaluate_condition(
        self, condition: Dict[str, Any], data: Dict[str, Any]
    ) -> bool:
        """Evaluate a condition against current data"""
        for field, expected_value in condition.items():
            if field not in data or data[field] != expected_value:
                return False
        return True

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
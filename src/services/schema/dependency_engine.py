from typing import Dict, Any, List, Optional, Tuple
from src.services.schema.step_info import StepInfo


class DependencyEngine:
    """Simplified dependency management"""

    def __init__(self, steps: List[StepInfo]):
        self.steps = steps
        self._steps_by_name = {step.name: step for step in steps}

    def get_available_steps(self, completed_data: Dict[str, Any]) -> List[str]:
        """Get steps available for completion"""
        available = []
        completed_set = set(completed_data.keys())
        
        for step in self.steps:
            if step.name in completed_set:
                continue
                
            # Check dependencies
            if not all(dep in completed_set for dep in step.depends_on):
                continue
                
            # Check conflicts
            if any(conflict in completed_set for conflict in step.conflicts_with):
                continue
                
            # Check conditional dependencies
            if step.conditional and not self._check_conditional(step, completed_data):
                continue
                
            available.append(step.name)
        
        return available

    def validate_dependencies_with_temp_data(
        self, step_name: str, temp_data: Dict[str, Any]
    ) -> Tuple[bool, str]:
        """Validate dependencies using temporary data"""
        step = self._steps_by_name.get(step_name)
        if not step:
            return False, f"Step '{step_name}' not found"

        # Check dependencies
        for dep in step.depends_on:
            if dep not in temp_data:
                return False, f"'{step_name}' requires '{dep}'"
                
        # Check conflicts
        for conflict in step.conflicts_with:
            if conflict in temp_data:
                return False, f"'{step_name}' conflicts with '{conflict}'"

        return True, ""

    def get_processing_order(self, steps: List[str]) -> List[str]:
        """Simple topological sort"""
        ordered = []
        remaining = list(steps)
        
        while remaining:
            ready = [
                step for step in remaining 
                if not any(dep in remaining for dep in self._steps_by_name.get(step, StepInfo(name="", description="", example=None, required=True, conditional=None, substeps=None)).depends_on)
            ]
            
            if not ready:
                ordered.extend(remaining)  # Circular dependency - add all
                break
                
            ordered.extend(ready)
            for step in ready:
                remaining.remove(step)
        
        return ordered

    def is_service_completed(self, completed_data: Dict[str, Any]) -> bool:
        """Check if all required steps are done"""
        return all(
            step.name in completed_data 
            for step in self.steps 
            if step.required or self._is_conditionally_required(step, completed_data)
        )

    def get_step_info(self, step_name: str) -> Optional[StepInfo]:
        """Get step info by name"""
        return self._steps_by_name.get(step_name)

    def _check_conditional(self, step: StepInfo, completed_data: Dict[str, Any]) -> bool:
        """Check if conditional dependencies are satisfied"""
        if not step.conditional:
            return True
            
        condition_met = self._evaluate_condition(step.conditional.if_condition, completed_data)
        required_deps = step.conditional.then_required if condition_met else step.conditional.else_required
        
        return all(dep in completed_data for dep in required_deps)

    def validate_dependencies(self, step_name: str, completed_data: Dict[str, Any]) -> Tuple[bool, str]:
        """Validate if step dependencies are satisfied"""
        return self.validate_dependencies_with_temp_data(step_name, completed_data)

    def _evaluate_condition(self, condition: Dict[str, Any], data: Dict[str, Any]) -> bool:
        """Simple condition evaluation"""
        return all(data.get(field) == expected for field, expected in condition.items())

    def _is_conditionally_required(self, step: StepInfo, completed_data: Dict[str, Any]) -> bool:
        """Check if step becomes required due to conditions"""
        if not step.conditional:
            return False
            
        condition_met = self._evaluate_condition(step.conditional.if_condition, completed_data)
        
        # Special case for initial_deposit
        if step.name == "initial_deposit" and condition_met:
            return True
            
        required_steps = step.conditional.then_required if condition_met else step.conditional.else_required
        return step.name in required_steps

    def _build_dependency_tree(self) -> List[Dict[str, Any]]:
        """Build dependency tree for visualization"""
        root_steps = [step for step in self.steps if not step.depends_on]
        
        def build_node(step: StepInfo, visited: Optional[set] = None) -> Dict[str, Any]:
            if visited is None:
                visited = set()
                
            if step.name in visited:
                return {"name": step.name, "circular": True}
                
            visited.add(step.name)
            
            # Find children that depend on this step
            children = []
            for other_step in self.steps:
                if step.name in other_step.depends_on:
                    children.append(build_node(other_step, visited.copy()))
            
            return {
                "name": step.name,
                "description": step.description,
                "required": step.required,
                "children": children,
                "conditional": step.conditional is not None
            }
        
        return [build_node(step) for step in root_steps]
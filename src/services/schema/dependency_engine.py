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
        
        for step in self.steps:
            if self._is_step_completed(step, completed_data):
                continue
                
            # Check dependencies
            if not all(
                dep_step and self._is_step_completed(dep_step, completed_data) 
                for dep in step.depends_on 
                if (dep_step := self.get_step_info(dep))
            ):
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
                

        return True, ""

    def get_processing_order(self, steps: List[str]) -> List[str]:
        """Simple topological sort"""
        ordered = []
        remaining = list(steps)
        
        while remaining:
            ready = [step for step in remaining 
                    if all(dep not in remaining for dep in self._steps_by_name.get(step, self.steps[0]).depends_on)]
            
            if not ready:
                ordered.extend(remaining)
                break
                
            ordered.extend(ready)
            for step in ready:
                remaining.remove(step)
        
        return ordered

    def is_service_completed(self, completed_data: Dict[str, Any]) -> bool:
        """Check if service is complete"""
        return all(self._is_step_completed(step, completed_data) for step in self.steps 
                  if step.required)

    def get_step_info(self, step_name: str) -> Optional[StepInfo]:
        """Get step info by name"""
        return self._steps_by_name.get(step_name)

    def validate_dependencies(self, step_name: str, completed_data: Dict[str, Any]) -> Tuple[bool, str]:
        """Validate dependencies (alias for temp data method)"""
        return self.validate_dependencies_with_temp_data(step_name, completed_data)


    def _build_dependency_tree(self) -> List[Dict[str, Any]]:
        """Build dependency tree"""
        root_steps = [step for step in self.steps if not step.depends_on]
        
        def build_node(step: StepInfo, visited: Optional[set] = None) -> Dict[str, Any]:
            visited = visited or set()
            if step.name in visited:
                return {"name": step.name, "circular": True}
            
            visited.add(step.name)
            children = [build_node(other_step, visited.copy()) 
                       for other_step in self.steps 
                       if step.name in other_step.depends_on]
            
            return {
                "name": step.name,
                "description": step.description,
                "required": step.required,
                "children": children
            }
        
        return [build_node(step) for step in root_steps]

    def _is_step_completed(self, step: StepInfo, completed_data: Dict[str, Any]) -> bool:
        """Check if a step is truly completed (including substeps validation)"""
        if not step:
            return False
            
        step_name = step.name
        
        # Step must exist in data
        if step_name not in completed_data:
            return False
        
        # If step has substeps, check if all required substeps are present
        if step.substeps:
            step_data = completed_data[step_name]
            if not isinstance(step_data, dict):
                return False
                
            required_substeps = {substep.name for substep in step.substeps if substep.required}
            present_substeps = set(step_data.keys())
            
            # All required substeps must be present
            return required_substeps.issubset(present_substeps)
        
        # For steps without substeps, just check if present
        return True
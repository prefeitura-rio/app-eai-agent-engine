from typing import Dict, Any, List, Optional
from src.services.schema.step_info import StepInfo
from src.services.schema.dependency_engine import DependencyEngine


class VisualizationEngine:
    """Simplified engine for essential visual representations"""

    def __init__(self, service_name: str, description: str, steps: List[StepInfo]):
        self.service_name = service_name
        self.description = description
        self.steps = steps
        self.dependency_engine = DependencyEngine(steps)

    def get_steps_schematic(self, completed_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Minimal schematic with only essential info"""
        completed_data = completed_data or {}
        
        # Simple step info
        steps_info = []
        for step in self.steps:
            step_data = {"name": step.name, "description": step.description}
            if step.name in completed_data:
                step_data["status"] = "completed"
                step_data["value"] = completed_data[step.name]
            elif step.name in self.dependency_engine.get_available_steps(completed_data):
                step_data["status"] = "available_required" if step.required else "available_optional"
            else:
                step_data["status"] = "pending"
            steps_info.append(step_data)
        
        # Simple dependency map
        dependency_map = {s.name: s.depends_on for s in self.steps if s.depends_on}
        
        return {
            "service_name": self.service_name,
            "total_steps": len(self.steps),
            "steps": steps_info,
            "dependency_map": dependency_map,
            "dependency_tree": self.dependency_engine._build_dependency_tree(),
            "state_analysis": self.get_state_analysis(completed_data) if completed_data else None,
        }

    def get_visual_schematic(self, completed_data: Optional[Dict[str, Any]] = None) -> str:
        """Simple dependency tree visualization"""
        completed_data = completed_data or {}
        
        lines = ["🌳 DEPENDENCY TREE:"]
        
        # Simple tree rendering
        tree = self.dependency_engine._build_dependency_tree()
        for root in tree:
            lines.extend(self._render_tree_node(root, completed_data))
        
        return "\n".join(lines)

    def _render_tree_node(
        self, node: Dict[str, Any], completed_data: Dict[str, Any], 
        prefix: str = "", is_last: bool = True
    ) -> List[str]:
        """Simple ASCII tree node rendering"""
        lines = []
        node_name = node["name"]
        
        # Status icon and info
        if node_name in completed_data:
            icon, status = "✅", f" = {completed_data[node_name]}"
        elif node.get("required", False):
            icon, status = "🔴", " (required)"
        else:
            icon, status = "🟡", " (optional)"
        
        # Tree connector
        connector = "└── " if is_last else "├── "
        lines.append(f"{prefix}{connector}{icon} {node_name}{status}")
        
        # Show substeps if any
        step_info = self.dependency_engine.get_step_info(node_name)
        if step_info and step_info.substeps:
            substep_prefix = prefix + ("    " if is_last else "│   ")
            children = node.get("children", [])
            
            for i, substep in enumerate(step_info.substeps):
                # Check if completed
                if (node_name in completed_data and 
                    isinstance(completed_data[node_name], dict) and 
                    substep.name in completed_data[node_name]):
                    sub_icon = "✅"
                    sub_status = f" = {completed_data[node_name][substep.name]}"
                else:
                    sub_icon = "🔴" if substep.required else "🟡"
                    sub_status = " (required)" if substep.required else " (optional)"
                
                is_last_sub = (i == len(step_info.substeps) - 1) and not children
                sub_connector = "└── " if is_last_sub else "├── "
                lines.append(f"{substep_prefix}{sub_connector}{sub_icon} {substep.name}{sub_status}")
        
        # Render children
        children = node.get("children", [])
        if children:
            child_prefix = prefix + ("    " if is_last else "│   ")
            for i, child in enumerate(children):
                is_last_child = i == len(children) - 1
                lines.extend(self._render_tree_node(child, completed_data, child_prefix, is_last_child))
        
        return lines

    def get_state_analysis(self, completed_data: Dict[str, Any]) -> Dict[str, Any]:
        """Simple state analysis"""
        completed_steps = [step.name for step in self.steps 
                          if self.dependency_engine._is_step_completed(step, completed_data)]
        available_steps = self.dependency_engine.get_available_steps(completed_data)
        
        # Classify available steps
        required_steps = []
        optional_steps = []
        for step_name in available_steps:
            step = next((s for s in self.steps if s.name == step_name), None)
            if step and step.required:
                required_steps.append(step_name)
            else:
                optional_steps.append(step_name)
        
        # Pending steps
        pending_steps = [s.name for s in self.steps 
                        if s.name not in completed_steps and s.name not in available_steps]
        
        return {
            "completed_steps": completed_steps,
            "available_steps": available_steps,
            "required_steps": required_steps,
            "optional_steps": optional_steps,
            "pending_steps": pending_steps,
            "progress": {
                "completed": len(completed_steps),
                "total": len(self.steps),
                "percentage": round((len(completed_steps) / len(self.steps)) * 100, 1) if self.steps else 0,
            },
        }

    def get_state_summary(self, completed_data: Dict[str, Any]) -> str:
        """Simple state summary"""
        analysis = self.get_state_analysis(completed_data)
        
        if not completed_data:
            return f"Iniciando {self.service_name}"
        
        summary = f"Concluído: {', '.join(analysis['completed_steps'])}"
        if analysis["required_steps"]:
            summary += f". Próximos: {', '.join(analysis['required_steps'])}"
        
        return summary

    def get_next_action_suggestion(self, completed_data: Dict[str, Any]) -> str:
        """Next action suggestion"""
        analysis = self.get_state_analysis(completed_data)
        
        if analysis["required_steps"]:
            return f"Forneça: {', '.join(analysis['required_steps'])}"
        elif analysis["optional_steps"]:
            return f"Opcionalmente: {', '.join(analysis['optional_steps'])}"
        else:
            return "Pronto para finalizar"
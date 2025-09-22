import re
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, field_validator



class StepInfo(BaseModel):
    """Step definition with infinite nested substeps support"""

    # Core fields
    name: str = Field(..., description="Step name")
    description: str = Field(..., description="Step description")
    payload_example: Optional[Dict[str, Any]] = Field(
        None, description="Example payload for this step"
    )
    required: bool = Field(True, description="Required step")

    # Dependencies (simplified)
    depends_on: List[str] = Field(default_factory=list, description="Prerequisites")

    # Infinite nested substeps support
    substeps: Optional[List["StepInfo"]] = Field(None, description="Nested sub-steps with infinite depth")

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", v):
            raise ValueError("Invalid step name")
        return v

    @field_validator("depends_on")
    @classmethod
    def validate_depends_on(cls, v: List[str]) -> List[str]:
        for step in v:
            if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", step):
                raise ValueError(f"Invalid step name: {step}")
        return v

    def get_all_step_paths(self, prefix: str = "") -> List[str]:
        """
        Get all possible step paths including nested substeps using dot notation.
        
        Examples:
        - user_info
        - user_info.name
        - user_info.address.street
        - user_info.address.coordinates.lat
        """
        paths = []
        current_path = f"{prefix}.{self.name}" if prefix else self.name
        paths.append(current_path)
        
        if self.substeps:
            for substep in self.substeps:
                paths.extend(substep.get_all_step_paths(current_path))
        
        return paths

    def find_step_by_path(self, path: str) -> Optional["StepInfo"]:
        """
        Find a step by dot notation path.
        
        Examples:
        - find_step_by_path("user_info") -> returns user_info step
        - find_step_by_path("name") -> returns name substep (if called on user_info)
        - find_step_by_path("user_info.name") -> returns name substep of user_info
        - find_step_by_path("address.street") -> returns street substep of address
        """
        parts = path.split(".")
        
        # If first part matches this step's name, continue with remaining path
        if parts[0] == self.name:
            if len(parts) == 1:
                return self
            
            if not self.substeps:
                return None
            
            remaining_path = ".".join(parts[1:])
            for substep in self.substeps:
                if substep.name == parts[1]:
                    return substep.find_step_by_path(remaining_path)
            
            return None
        
        # If first part doesn't match, check if it's a direct substep
        if self.substeps:
            for substep in self.substeps:
                if substep.name == parts[0]:
                    if len(parts) == 1:
                        return substep
                    else:
                        # Continue with remaining path
                        remaining_path = ".".join(parts[1:])
                        return substep.find_step_by_path(remaining_path)
        
        return None

    def get_nested_data_structure(self, data: Dict[str, Any], prefix: str = "") -> Dict[str, Any]:
        """
        Convert flat dot notation data to nested JSON structure.
        
        Example:
        Input: {"user_info.name": "John", "user_info.address.street": "Main St"}
        Output: {"user_info": {"name": "John", "address": {"street": "Main St"}}}
        """
        current_path = f"{prefix}.{self.name}" if prefix else self.name
        result = {}
        
        # Check if we have direct data for this step
        if current_path in data:
            result[self.name] = data[current_path]
            return result
        
        # Check if we have substep data
        if self.substeps:
            substep_data = {}
            for substep in self.substeps:
                nested = substep.get_nested_data_structure(data, current_path)
                if nested:
                    substep_data.update(nested)
            
            if substep_data:
                result[self.name] = substep_data
        
        return result

    def validate_nested_structure(self, data: Dict[str, Any]) -> List[str]:
        """
        Validate that all required nested substeps are present in data.
        Returns list of missing required step paths.
        """
        missing = []
        
        if self.required and self.name not in data:
            missing.append(self.name)
            return missing  # If main step is missing, don't check substeps
        
        if self.substeps and self.name in data and isinstance(data[self.name], dict):
            for substep in self.substeps:
                substep_missing = substep.validate_nested_structure(data[self.name])
                missing.extend([f"{self.name}.{path}" for path in substep_missing])
        
        return missing

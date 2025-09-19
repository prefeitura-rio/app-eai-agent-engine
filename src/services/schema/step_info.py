import re
from typing import List, Optional, Literal, Dict, Any
from pydantic import BaseModel, Field, field_validator



class StepInfo(BaseModel):
    """Simplified step definition with smart defaults"""

    # Core fields
    name: str = Field(..., description="Step name")
    description: str = Field(..., description="Step description")
    payload_example: Optional[Dict[str, Any]] = Field(
        None, description="Example payload for this step"
    )
    required: bool = Field(True, description="Required step")

    # Smart type system (simplified)
    data_type: Literal["str", "dict", "list_dict"] = Field(
        default="str", description="Data type"
    )

    # Dependencies (simplified)
    depends_on: List[str] = Field(default_factory=list, description="Prerequisites")

    # Substeps (simplified - just names)
    substeps: Optional[List["StepInfo"]] = Field(None, description="Sub-fields")

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

import re
from typing import List, Optional, Literal
from pydantic import BaseModel, Field, field_validator


class ConditionalDependency(BaseModel):
    """Model for conditional dependencies between steps"""

    if_condition: dict = Field(..., description="Condition that must be met")
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
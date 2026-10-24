import re
from typing import Optional, Literal
from pydantic import BaseModel, Field, field_validator

SANDBOX_NAME_REGEX = re.compile(r"^sbx-[a-z0-9]{8,}$")
VALID_STATES = {"created", "ready", "running", "succeeded", "failed", "deleted"}
VALID_EXECUTION_TARGET = "celesto_sandbox"

class RunCreate(BaseModel):
    run_id: str = Field(..., min_length=1, description="Unique identifier for the run")
    sandbox_name: str = Field(..., description="Sandbox identifier matching sbx- plus 8+ lowercase alnum chars")
    problem_id: str = Field(..., min_length=1, description="Identifier of the problem or assignment")
    state: Literal["created", "ready", "running", "succeeded", "failed", "deleted"] = Field(
        ..., description="Current state of the sandbox run"
    )
    execution_target: Literal["celesto_sandbox"] = Field(
        ..., description="Must be exactly celesto_sandbox"
    )
    metadata: Optional[dict] = Field(default_factory=dict)

    @field_validator("sandbox_name")
    @classmethod
    def validate_sandbox_name(cls, v: str) -> str:
        if not SANDBOX_NAME_REGEX.match(v):
            raise ValueError(f"sandbox_name '{v}' must match regex '^sbx-[a-z0-9]{{8,}}$'")
        return v

    @field_validator("execution_target")
    @classmethod
    def validate_execution_target(cls, v: str) -> str:
        if v != VALID_EXECUTION_TARGET:
            raise ValueError(f"execution_target must be '{VALID_EXECUTION_TARGET}', got '{v}'")
        return v


class RunResponse(BaseModel):
    run_id: str
    sandbox_name: str
    problem_id: str
    state: str
    execution_target: str
    created_at: Optional[str] = None
    metadata: Optional[dict] = None

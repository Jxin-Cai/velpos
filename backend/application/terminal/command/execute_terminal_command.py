from pydantic import BaseModel, ConfigDict, Field


class ExecuteTerminalCommand(BaseModel):
    model_config = ConfigDict(frozen=True)

    command: str = Field(..., min_length=1)
    timeout: int = Field(default=30, ge=1, le=300)
    cwd: str | None = Field(default=None)

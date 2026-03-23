from pydantic import BaseModel, ConfigDict, Field


class UnbindImCommand(BaseModel):
    model_config = ConfigDict(frozen=True)

    session_id: str = Field(min_length=1)

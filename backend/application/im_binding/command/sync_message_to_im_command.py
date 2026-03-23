from pydantic import BaseModel, ConfigDict, Field


class SyncMessageToImCommand(BaseModel):
    model_config = ConfigDict(frozen=True)

    session_id: str = Field(min_length=1)
    message: str = Field(min_length=1)
    skills: list[str] = Field(default_factory=list)

from pydantic import BaseModel, ConfigDict, Field


class RunQueryCommand(BaseModel):
    model_config = ConfigDict(frozen=True)

    session_id: str = Field(..., min_length=1)
    prompt: str = Field(..., min_length=1)
    image_paths: list[str] = Field(default_factory=list)

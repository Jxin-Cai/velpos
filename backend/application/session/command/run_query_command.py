from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RunQueryCommand(BaseModel):
    model_config = ConfigDict(frozen=True)

    session_id: str = Field(..., min_length=1)
    prompt: str = ""
    client_message_id: str = Field(default="", max_length=64)
    image_paths: list[str] = Field(default_factory=list)
    attachments: list[dict[str, Any]] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_query_content(self) -> "RunQueryCommand":
        if not self.prompt and not self.image_paths and not self.attachments:
            raise ValueError("prompt or attachment is required")
        return self

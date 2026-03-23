import os

from pydantic import BaseModel, ConfigDict


class CreateSessionCommand(BaseModel):
    model_config = ConfigDict(frozen=True)

    model: str = os.getenv("DEFAULT_MODEL", "claude-opus-4-6")
    project_id: str = ""
    project_dir: str = ""
    name: str = ""

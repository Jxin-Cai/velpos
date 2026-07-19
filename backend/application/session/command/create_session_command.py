import os

from pydantic import BaseModel, ConfigDict


class CreateSessionCommand(BaseModel):
    model_config = ConfigDict(frozen=True)

    model: str = os.getenv("DEFAULT_MODEL", "default")
    project_id: str = ""
    project_dir: str = ""
    name: str = ""
    card_execution_id: str | None = None
    agent_slot_id: str | None = None

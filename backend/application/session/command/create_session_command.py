from pydantic import BaseModel, ConfigDict


class CreateSessionCommand(BaseModel):
    model_config = ConfigDict(frozen=True)

    model: str
    project_id: str = ""
    project_dir: str = ""
    name: str = ""
    user_id: int = 1
    card_execution_id: str | None = None
    agent_slot_id: str | None = None

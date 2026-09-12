from pydantic import BaseModel, ConfigDict


class CreateSessionCommand(BaseModel):
    model_config = ConfigDict(frozen=True)

    model: str
    project_id: str = ""
    project_dir: str = ""
    name: str = ""
    user_id: int = 1

from pydantic import BaseModel, ConfigDict


class CreateProjectCommand(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    github_url: str = ""

from pydantic import BaseModel, ConfigDict


class ReorderProjectsCommand(BaseModel):
    model_config = ConfigDict(frozen=True)

    ordered_ids: list[str]

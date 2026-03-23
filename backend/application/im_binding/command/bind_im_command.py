from pydantic import BaseModel, ConfigDict, Field


class BindImCommand(BaseModel):
    model_config = ConfigDict(frozen=True)

    session_id: str = Field(min_length=1)
    admin_user_id: str = Field(min_length=1)

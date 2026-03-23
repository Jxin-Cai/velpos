from pydantic import BaseModel, ConfigDict, Field


class CompleteBindingCommand(BaseModel):
    model_config = ConfigDict(frozen=True)

    session_id: str = Field(min_length=1)
    friend_user_id: str = Field(min_length=1)

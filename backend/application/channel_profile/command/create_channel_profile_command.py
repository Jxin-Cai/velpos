from pydantic import BaseModel, ConfigDict, Field


class CreateChannelProfileCommand(BaseModel):
    model_config = ConfigDict(frozen=True, populate_by_name=True)

    name: str = Field(..., min_length=1)
    host: str = Field(default="")
    api_key: str = Field(default="")
    auth_env_name: str = Field(default="ANTHROPIC_API_KEY")
    channel_model_config: dict[str, str] = Field(
        default_factory=dict,
        validation_alias="model_config",
        serialization_alias="model_config",
    )

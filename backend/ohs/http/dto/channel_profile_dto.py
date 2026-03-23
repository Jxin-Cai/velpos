from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_serializer

from domain.channel_profile.model.channel_profile import ChannelProfile
from ohs.assembler.channel_profile_assembler import ChannelProfileAssembler


class CreateChannelProfileRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(
        ...,
        min_length=1,
        description="Channel profile name",
    )
    host: str = Field(default="", description="ANTHROPIC_BASE_URL")
    api_key: str = Field(default="", description="API authentication key")
    auth_env_name: str = Field(default="ANTHROPIC_API_KEY", description="Auth environment variable name")
    channel_model_config: dict[str, str] = Field(
        default_factory=dict,
        validation_alias="model_config",
        description="Model environment variable mapping",
    )


class UpdateChannelProfileRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(
        ...,
        min_length=1,
        description="Channel profile name",
    )
    host: str = Field(default="", description="ANTHROPIC_BASE_URL")
    api_key: str = Field(default="", description="API authentication key")
    auth_env_name: str = Field(default="ANTHROPIC_API_KEY", description="Auth environment variable name")
    channel_model_config: dict[str, str] = Field(
        default_factory=dict,
        validation_alias="model_config",
        description="Model environment variable mapping",
    )


class ChannelProfileResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    profile_id: str
    name: str
    host: str
    api_key: str
    auth_env_name: str = "ANTHROPIC_API_KEY"
    channel_model_config: dict[str, str] = Field(
        default_factory=dict,
        validation_alias="model_config",
    )
    is_active: bool
    created_time: str
    updated_time: str

    @model_serializer(mode="wrap")
    def _serialize(self, handler) -> dict:
        data = handler(self)
        data["model_config"] = data.pop("channel_model_config")
        return data

    @classmethod
    def from_domain(cls, profile: ChannelProfile) -> ChannelProfileResponse:
        data = ChannelProfileAssembler.to_dict(profile)
        return cls(
            profile_id=data["profile_id"],
            name=data["name"],
            host=data["host"],
            api_key=data["api_key"],
            auth_env_name=data["auth_env_name"],
            channel_model_config=data["model_config"],
            is_active=data["is_active"],
            created_time=data["created_time"],
            updated_time=data["updated_time"],
        )


class ChannelProfileListResponse(BaseModel):
    profiles: list[ChannelProfileResponse]

    @classmethod
    def from_domain_list(
        cls, profiles: list[ChannelProfile]
    ) -> ChannelProfileListResponse:
        return cls(
            profiles=[ChannelProfileResponse.from_domain(p) for p in profiles],
        )

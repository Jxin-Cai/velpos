from __future__ import annotations

from application.channel_profile.command.create_channel_profile_command import (
    CreateChannelProfileCommand,
)
from application.channel_profile.command.update_channel_profile_command import (
    UpdateChannelProfileCommand,
)
from domain.channel_profile.acl.settings_file_gateway import SettingsFileGateway
from domain.channel_profile.model.channel_profile import ChannelProfile
from domain.channel_profile.repository.channel_profile_repository import (
    ChannelProfileRepository,
)
from domain.session.acl.claude_agent_gateway import ClaudeAgentGateway
from domain.shared.business_exception import BusinessException


class ChannelProfileApplicationService:

    _CHANNEL_ENV_KEYS = [
        "ANTHROPIC_MODEL",
        "ANTHROPIC_BASE_URL",
        "ANTHROPIC_AUTH_TOKEN",
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_DEFAULT_SONNET_MODEL",
        "ANTHROPIC_DEFAULT_SONNET_MODEL_NAME",
        "ANTHROPIC_DEFAULT_OPUS_MODEL",
        "ANTHROPIC_DEFAULT_OPUS_MODEL_NAME",
        "ANTHROPIC_DEFAULT_FABLE_MODEL",
        "ANTHROPIC_DEFAULT_FABLE_MODEL_NAME",
        "ANTHROPIC_DEFAULT_HAIKU_MODEL",
        "ANTHROPIC_DEFAULT_HAIKU_MODEL_NAME",
        "CLAUDE_CODE_SUBAGENT_MODEL",
        "ANTHROPIC_REASONING_MODEL",
    ]

    def __init__(
        self,
        profile_repository: ChannelProfileRepository,
        settings_file_gateway: SettingsFileGateway,
        claude_agent_gateway: ClaudeAgentGateway,
    ) -> None:
        self._profile_repository = profile_repository
        self._settings_file_gateway = settings_file_gateway
        self._claude_agent_gateway = claude_agent_gateway

    async def create_profile(
        self, command: CreateChannelProfileCommand
    ) -> ChannelProfile:
        """Create a new channel profile.

        Creates a ChannelProfile aggregate root via factory method and persists it.
        """
        profile = ChannelProfile.create(
            name=command.name,
            host=command.host,
            api_key=command.api_key,
            auth_env_name=command.auth_env_name,
            model_config=command.channel_model_config,
        )
        await self._profile_repository.save(profile)
        return profile

    async def update_profile(
        self, profile_id: str, command: UpdateChannelProfileCommand
    ) -> ChannelProfile:
        """Update an existing channel profile.

        Loads the aggregate, applies business updates, persists, and if the
        profile is currently active, syncs env vars to settings.json.
        """
        profile = await self._profile_repository.find_by_id(profile_id)
        if profile is None:
            raise BusinessException("Channel profile not found")

        profile.update_config(
            name=command.name,
            host=command.host,
            api_key=command.api_key,
            auth_env_name=command.auth_env_name,
            model_config=command.channel_model_config,
        )
        await self._profile_repository.save(profile)

        if profile.is_active:
            await self._sync_env_and_disconnect(profile)

        return profile

    async def delete_profile(self, profile_id: str) -> None:
        """Delete a channel profile by profile_id."""
        removed = await self._profile_repository.remove(profile_id)
        if not removed:
            raise BusinessException("Channel profile not found")

    async def list_profiles(self) -> list[ChannelProfile]:
        """List all channel profiles ordered by created_time descending."""
        return await self._profile_repository.find_all()

    async def activate_profile(self, profile_id: str) -> ChannelProfile:
        """Activate the specified channel profile.

        Deactivates any currently active profile, activates the target,
        writes the target's env vars into settings.json, and disconnects
        all SDK subprocesses so they reconnect with the new env.
        """
        profile = await self._profile_repository.find_by_id(profile_id)
        if profile is None:
            raise BusinessException("Channel profile not found")

        current_active = await self._profile_repository.find_active()
        if current_active is not None and current_active.profile_id != profile_id:
            current_active.deactivate()
            await self._profile_repository.save(current_active)

        profile.activate()
        await self._profile_repository.save(profile)

        await self._sync_env_and_disconnect(profile)

        return profile

    async def _sync_env_and_disconnect(self, profile: ChannelProfile) -> None:
        await self._settings_file_gateway.remove_env_keys(self._CHANNEL_ENV_KEYS)
        await self._settings_file_gateway.update_env_section(
            self._profile_to_env_vars(profile)
        )
        await self._claude_agent_gateway.disconnect_all()

    @staticmethod
    def _profile_to_env_vars(profile: ChannelProfile) -> dict[str, str]:
        env_vars: dict[str, str] = {}
        if profile.host:
            env_vars["ANTHROPIC_BASE_URL"] = profile.host
        if profile.api_key:
            env_vars[profile.auth_env_name] = profile.api_key
        for key, value in profile.model_config.items():
            if value:
                env_vars[key] = value
        return env_vars

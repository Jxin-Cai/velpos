from __future__ import annotations

from typing import Any

from domain.channel_profile.model.channel_profile import ChannelProfile


class ChannelProfileAssembler:
    @staticmethod
    def to_dict(profile: ChannelProfile) -> dict[str, Any]:
        return {
            "profile_id": profile.profile_id,
            "name": profile.name,
            "host": profile.host,
            "api_key": profile.api_key,
            "auth_env_name": profile.auth_env_name,
            "model_config": profile.model_config,
            "is_active": profile.is_active,
            "created_time": profile.created_time.isoformat(),
            "updated_time": profile.updated_time.isoformat(),
        }

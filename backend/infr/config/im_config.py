from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class ImConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="IM_")

    ws_addr: str = ""
    api_addr: str = ""
    admin_secret: str = ""
    admin_user_id: str = ""

    @property
    def enabled(self) -> bool:
        return bool(
            self.ws_addr
            and self.api_addr
            and self.admin_secret
            and self.admin_user_id
        )

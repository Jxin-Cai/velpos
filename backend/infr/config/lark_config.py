from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class LarkConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LARK_")

    api_base_url: str = ""
    app_id: str = ""
    app_secret: str = ""

    @property
    def enabled(self) -> bool:
        return bool(self.api_base_url)

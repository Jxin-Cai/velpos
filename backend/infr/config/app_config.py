from __future__ import annotations

import os


class AppConfig:
    def __init__(self) -> None:
        self.mode: str = os.getenv("VELPOS_MODE", "dev")
        self.jwt_secret: str = os.getenv("JWT_SECRET", "velpos-dev-secret-key-change-in-production")
        self.jwt_expire_minutes: int = int(os.getenv("JWT_EXPIRE_MINUTES", "10080"))
        self.admin_password: str = os.getenv("VELPOS_ADMIN_PASSWORD", "")


app_config = AppConfig()

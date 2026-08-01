from __future__ import annotations

import os
from pathlib import Path

_DEFAULT_JWT_SECRET = "velpos-dev-secret-key-change-in-production"


class AppConfig:
    def __init__(self) -> None:
        self.mode: str = os.getenv("VELPOS_MODE", "dev")
        self.jwt_secret: str = os.getenv("JWT_SECRET", _DEFAULT_JWT_SECRET)
        self.jwt_expire_minutes: int = int(os.getenv("JWT_EXPIRE_MINUTES", "10080"))
        self.admin_password: str = os.getenv("VELPOS_ADMIN_PASSWORD", "")
        self.registration_enabled: bool = os.getenv(
            "VELPOS_REGISTRATION_ENABLED", "false"
        ).lower() in ("1", "true", "yes")
        self.projects_root_dir: Path = Path(
            os.path.expanduser(os.getenv("PROJECTS_ROOT_DIR", "~/velpos"))
        )

        if self.mode == "pro":
            if self.jwt_secret == _DEFAULT_JWT_SECRET or len(self.jwt_secret) < 32:
                raise RuntimeError(
                    "JWT_SECRET must be set to a unique value (>= 32 chars) in pro mode. "
                    "Refusing to start with default/weak secret."
                )
            if len(self.admin_password) < 12:
                raise RuntimeError(
                    "VELPOS_ADMIN_PASSWORD must be set (>= 12 chars) in pro mode."
                )


app_config = AppConfig()

from __future__ import annotations

import os

from sqlalchemy.orm import DeclarativeBase

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("环境变量 DATABASE_URL 未设置，请在 .env 文件中配置")


class Base(DeclarativeBase):
    pass

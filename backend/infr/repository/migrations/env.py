"""Alembic async migration environment."""
from __future__ import annotations

import asyncio
import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# 确保 backend/ 在 sys.path 中（migrations 位于 infr/repository/migrations/）
_backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, _backend_dir)

from dotenv import load_dotenv

load_dotenv()

# 从 base.py 导入（不触发 async_engine 的创建，避免 aiomysql 未安装时报错）
from infr.config.base import DATABASE_URL, Base

# --- 确保所有 ORM 模型被导入以支持 autogenerate ---
import infr.repository.evolution_proposal_model  # noqa: F401
import infr.repository.attachment_model  # noqa: F401
import infr.repository.session_model  # noqa: F401
import infr.repository.scheduled_task_model  # noqa: F401
import infr.repository.session_audit_event_model  # noqa: F401
import infr.repository.session_branch_model  # noqa: F401
import infr.repository.session_run_step_model  # noqa: F401
import infr.repository.session_timeline_event_model  # noqa: F401
import infr.repository.im_binding_model  # noqa: F401
import infr.repository.channel_profile_model  # noqa: F401
import infr.repository.project_model  # noqa: F401
import infr.repository.usage_governance_model  # noqa: F401
import infr.repository.project_command_policy_model  # noqa: F401
import infr.repository.project_memory_entry_model  # noqa: F401
import infr.repository.claude_md_revision_model  # noqa: F401
import infr.repository.channel_init_model  # noqa: F401
# ------------------------------------------------

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# 动态注入数据库 URL（DRY：复用 base.py 的配置）
config.set_main_option("sqlalchemy.url", DATABASE_URL)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Generate SQL script without connecting to the database."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Execute migrations on a given connection."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Create an async engine and run migrations."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    支持两种方式：
    1. 由 main.py lifespan 传入已有的 connection（避免嵌套事件循环）
    2. 通过 alembic CLI 直接运行时，自己创建引擎
    """
    connectable = config.attributes.get("connection", None)

    if connectable is not None:
        # 由调用方传入的同步 connection，直接使用
        do_run_migrations(connectable)
    else:
        # CLI 直接调用（如 alembic upgrade head），创建自己的引擎
        asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

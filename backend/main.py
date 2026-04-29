from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

import asyncio
import logging
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from domain.shared.business_exception import BusinessException
from ohs.http.api_response import ApiResponse
from ohs.http.agent_router import router as agent_router
from ohs.http.attachment_router import router as attachment_router
from ohs.http.channel_profile_router import router as channel_profile_router
from ohs.http.claude_session_router import router as claude_session_router
from ohs.http.command_policy_router import router as command_policy_router
from ohs.http.command_router import router as command_router
from ohs.http.evolution_router import router as evolution_router
from ohs.http.git_router import router as git_router
from ohs.http.im_router import router as im_router
from ohs.http.plugin_router import router as plugin_router
from ohs.http.project_memory_router import router as project_memory_router
from ohs.http.project_router import router as project_router
from ohs.http.scheduler_router import router as scheduler_router
from ohs.http.session_router import router as session_router
from ohs.http.session_timeline_router import router as session_timeline_router
from ohs.http.settings_router import router as settings_router
from ohs.http.terminal_router import router as terminal_router
from ohs.http.usage_router import router as usage_router
from ohs.http.memory_router import router as memory_router
from ohs.ws.session_ws import router as ws_router

class _LogContextDefaults(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        for field in ("session_id", "sdk_session_id", "run_id"):
            if not hasattr(record, field):
                setattr(record, field, "-")
        return True


def _configure_logging(*, force: bool = False) -> None:
    log_format = "%(asctime)s [%(levelname)s] %(name)s [session=%(session_id)s sdk=%(sdk_session_id)s run=%(run_id)s] - %(message)s"
    formatter = logging.Formatter(log_format)
    context_filter = _LogContextDefaults()

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    console_handler.addFilter(context_filter)

    repo_root = Path(__file__).resolve().parent.parent
    log_dir = repo_root / ".log"
    log_dir.mkdir(parents=True, exist_ok=True)
    error_handler = RotatingFileHandler(
        log_dir / "backend-error.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)
    error_handler.addFilter(context_filter)

    logging.basicConfig(
        level=logging.INFO,
        handlers=[console_handler, error_handler],
        force=force,
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


_configure_logging()
logger = logging.getLogger("velpos")


async def _run_alembic_upgrade() -> None:
    """启动时执行 Alembic migration（类似 Flyway）。

    Baseline: 若业务表已存在但无有效迁移记录（create_all 遗留），
    先 stamp head 再执行后续增量迁移。
    """
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import inspect, pool, text
    from sqlalchemy.ext.asyncio import async_engine_from_config

    from infr.config.base import DATABASE_URL

    backend_dir = Path(__file__).resolve().parent
    alembic_cfg = Config(str(backend_dir / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(backend_dir / "infr/repository/migrations"))
    alembic_cfg.set_main_option("sqlalchemy.url", DATABASE_URL)

    import infr.repository.evolution_proposal_model  # noqa: F401
    import infr.repository.attachment_model  # noqa: F401
    import infr.repository.session_model  # noqa: F401
    import infr.repository.scheduled_task_model  # noqa: F401
    import infr.repository.session_audit_event_model  # noqa: F401
    import infr.repository.session_branch_model  # noqa: F401
    import infr.repository.session_run_step_model  # noqa: F401
    import infr.repository.session_timeline_event_model  # noqa: F401
    import infr.repository.usage_governance_model  # noqa: F401
    import infr.repository.project_command_policy_model  # noqa: F401
    import infr.repository.project_memory_entry_model  # noqa: F401
    import infr.repository.claude_md_revision_model  # noqa: F401
    from infr.config.base import Base

    connectable = async_engine_from_config(
        alembic_cfg.get_section(alembic_cfg.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    def _do_upgrade(connection):
        alembic_cfg.attributes["connection"] = connection

        insp = inspect(connection)
        existing_tables = set(insp.get_table_names())
        has_app_tables = bool(existing_tables & {"projects", "sessions"})

        if has_app_tables:
            # 检查 alembic_version 中的 revision 是否有效
            needs_baseline = True
            if "alembic_version" in existing_tables:
                row = connection.execute(text("SELECT version_num FROM alembic_version LIMIT 1")).scalar()
                if row is not None:
                    from alembic.script import ScriptDirectory
                    script = ScriptDirectory(str(backend_dir / "infr/repository/migrations"))
                    try:
                        script.get_revision(row)
                        needs_baseline = False
                    except Exception:
                        pass  # 无效 revision，需要 baseline

            if needs_baseline:
                logger.info("Baseline: stamping to 0001_initial for existing schema.")
                if "alembic_version" in existing_tables:
                    connection.execute(text("DROP TABLE alembic_version"))
                    connection.commit()
                command.stamp(alembic_cfg, "0001_initial")
            elif "projects" in existing_tables:
                # Repair: previous baseline wrongly stamped head, schema is behind
                proj_cols = {c["name"] for c in insp.get_columns("projects")}
                if "agents_json" not in proj_cols:
                    logger.info("Schema repair: resetting to 0001_initial")
                    connection.execute(text("DELETE FROM alembic_version"))
                    connection.commit()
                    command.stamp(alembic_cfg, "0001_initial")

        command.upgrade(alembic_cfg, "head")

    async with connectable.connect() as connection:
        await connection.run_sync(_do_upgrade)
    await connectable.dispose()


async def _resume_im_listeners() -> None:
    """Resume server-managed IM listeners for existing bound sessions."""
    from infr.config.database import async_session_factory
    from infr.repository.im_binding_repository_impl import ImBindingRepositoryImpl
    from infr.repository.channel_init_repository_impl import ChannelInitRepositoryImpl
    from ohs.dependencies import (
        get_im_channel_registry,
        get_connection_manager,
        get_create_session_service_factory,
    )
    from application.im_binding.im_channel_application_service import ImChannelApplicationService

    async with async_session_factory() as db_session:
        binding_repo = ImBindingRepositoryImpl(db_session)
        init_repo = ChannelInitRepositoryImpl(db_session)
        svc = ImChannelApplicationService(
            registry=get_im_channel_registry(),
            binding_repo=binding_repo,
            init_repo=init_repo,
            session_service_factory=get_create_session_service_factory(),
            connection_manager=get_connection_manager(),
        )
        bindings = await binding_repo.find_all_bound()
        for binding in bindings:
            try:
                await svc.start_channel_listener(binding)
                logger.info(
                    "Resumed listener: channel=%s session=%s",
                    binding.channel_type.value, binding.session_id,
                )
            except Exception as e:
                logger.warning(
                    "Failed to resume listener: channel=%s session=%s error=%s",
                    binding.channel_type.value, binding.session_id, e,
                )


async def _restore_channel_profile_settings() -> None:
    """Restore active channel profile env vars to ~/.claude/settings.json.

    In production (Docker), settings.json is lost on every rebuild because it
    lives inside the container filesystem. Channel profiles are persisted in
    MySQL, so we re-apply the active profile's env vars on startup to keep
    Claude Code's settings in sync.
    """
    from infr.config.database import async_session_factory
    from infr.repository.channel_profile_repository_impl import ChannelProfileRepositoryImpl
    from application.channel_profile.channel_profile_application_service import (
        ChannelProfileApplicationService,
    )
    from ohs.dependencies import get_settings_application_service

    settings_svc = get_settings_application_service()

    async with async_session_factory() as db_session:
        repo = ChannelProfileRepositoryImpl(db_session)
        active_profile = await repo.find_active()
        if active_profile is None:
            logger.info("No active channel profile found, skipping settings restore.")
            return

        env_vars = ChannelProfileApplicationService._profile_to_env_vars(active_profile)
        if env_vars:
            await settings_svc._settings_file_gateway.update_env_section(env_vars)
            logger.info(
                "Restored active channel profile '%s' env vars to settings.json.",
                active_profile.name,
            )


@asynccontextmanager
async def lifespan(app: FastAPI):
    from ohs.dependencies import get_im_config, get_im_channel_registry

    im_config = get_im_config()
    im_channel_registry = get_im_channel_registry()

    logger.info("Running database migrations...")
    max_retries = 10
    for attempt in range(1, max_retries + 1):
        try:
            await _run_alembic_upgrade()
            logger.info("Database migrations completed.")
            break
        except Exception as e:
            if attempt == max_retries:
                raise
            logger.warning("Migration attempt %d/%d failed: %s. Retrying in %ds...", attempt, max_retries, e, attempt)
            await asyncio.sleep(attempt)

    # Re-apply logging config — Alembic fileConfig resets root logger to WARN
    _configure_logging(force=True)

    registered = [ct.value for ct in im_channel_registry.registered_types]
    logger.info("IM channels registered: %s", registered)

    # Restore active channel profile settings after rebuild
    try:
        await _restore_channel_profile_settings()
    except Exception as e:
        logger.error("Failed to restore channel profile settings: %s", e)

    if im_config.enabled:
        logger.info("OpenIM integration enabled")
    else:
        logger.info("OpenIM integration disabled (missing config)")

    # Resume IM channel listeners for existing bindings (e.g. WeChat poll loop)
    try:
        await _resume_im_listeners()
    except Exception as e:
        logger.error("Failed to resume IM listeners: %s", e)

    scheduler_runner = None
    try:
        from infr.scheduler.scheduler_runner import SchedulerRunner
        scheduler_runner = SchedulerRunner()
        scheduler_runner.start()
        logger.info("Scheduler runner started")
    except Exception:
        logger.error("Failed to start scheduler runner", exc_info=True)

    yield

    if scheduler_runner is not None:
        try:
            await scheduler_runner.stop()
        except Exception:
            logger.error("Failed to stop scheduler runner", exc_info=True)

    from ohs.dependencies import (
        get_im_api_gateway,
        get_im_ws_client,
        get_qq_ws_client,
        get_weixin_adapter,
        get_lark_adapter,
        get_claude_agent_gateway,
    )

    # Disconnect all Claude SDK clients (CLI subprocesses)
    try:
        await get_claude_agent_gateway().disconnect_all()
    except Exception:
        logger.error("Failed to disconnect SDK clients", exc_info=True)

    # Stop IM channel adapters
    try:
        await get_lark_adapter().close()
    except Exception:
        logger.error("Failed to close Lark adapter", exc_info=True)

    try:
        await get_weixin_adapter().close()
    except Exception:
        logger.error("Failed to close WeChat adapter", exc_info=True)

    # Stop QQ WebSocket client
    try:
        await get_qq_ws_client().stop_all()
    except Exception:
        logger.error("Failed to stop QQ WS client", exc_info=True)

    im_ws_client = get_im_ws_client()
    if im_ws_client is not None:
        try:
            await im_ws_client.close_all()
        except Exception:
            logger.error("Failed to close IM WS client", exc_info=True)

    im_api_gateway = get_im_api_gateway()
    if im_api_gateway is not None:
        try:
            await im_api_gateway.close()
        except Exception:
            logger.error("Failed to close IM API gateway", exc_info=True)


app = FastAPI(title="Velpos", version="0.1.0", lifespan=lifespan)

import os as _os

_cors_origins = [o.strip() for o in _os.getenv("CORS_ALLOW_ORIGINS", "*").split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(project_router)
app.include_router(project_memory_router)
app.include_router(session_router)
app.include_router(attachment_router)
app.include_router(evolution_router)
app.include_router(scheduler_router)
app.include_router(session_timeline_router)
app.include_router(agent_router)
app.include_router(plugin_router)
app.include_router(command_router)
app.include_router(command_policy_router)
app.include_router(claude_session_router)
app.include_router(git_router)
app.include_router(im_router)
app.include_router(ws_router)
app.include_router(settings_router)
app.include_router(channel_profile_router)
app.include_router(terminal_router)
app.include_router(usage_router)
app.include_router(memory_router)


@app.exception_handler(BusinessException)
async def business_exception_handler(
    request: Request,
    exc: BusinessException,
) -> JSONResponse:
    response = ApiResponse.fail(code=-1, message=exc.message)
    return JSONResponse(status_code=422, content=response.model_dump())


@app.exception_handler(Exception)
async def global_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    logger.error("Unhandled exception on %s %s: %s", request.method, request.url.path, exc, exc_info=True)
    response = ApiResponse.fail(code=-500, message="Internal server error")
    return JSONResponse(status_code=500, content=response.model_dump())


@app.get("/api/health")
async def health():
    from ohs.dependencies import get_im_config, get_im_channel_registry

    im_config = get_im_config()
    im_channel_registry = get_im_channel_registry()

    return {
        "status": "ok",
        "features": {
            "im": im_config.enabled,
            "im_channels": [ct.value for ct in im_channel_registry.registered_types],
        },
    }


if __name__ == "__main__":
    import os

    import uvicorn

    uvicorn.run(
        "main:app",
        host=os.getenv("SERVER_HOST", "0.0.0.0"),
        port=int(os.getenv("SERVER_PORT", "8083")),
        reload=True,
        log_level="info",
    )

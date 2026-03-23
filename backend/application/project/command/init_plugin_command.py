from pydantic import BaseModel, ConfigDict


class InitPluginCommand(BaseModel):
    model_config = ConfigDict(frozen=True)

    project_id: str
    plugin_type: str  # e.g. "lark"
    session_id: str   # run init in current session

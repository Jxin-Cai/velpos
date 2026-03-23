from pydantic import BaseModel


class ImportClaudeSessionCommand(BaseModel, frozen=True):
    claude_session_id: str
    cwd: str
    name: str = ""

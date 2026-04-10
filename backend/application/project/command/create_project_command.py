import re

from pydantic import BaseModel, ConfigDict, field_validator

# Only allow characters safe for directory names: letters, digits, hyphen, underscore, dot
_PROJECT_NAME_RE = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9._-]*$')


class CreateProjectCommand(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    github_url: str = ""

    @field_validator('name')
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError('Project name cannot be empty')
        if not _PROJECT_NAME_RE.match(v):
            raise ValueError(
                'Project name can only contain letters, digits, hyphens, underscores, and dots, '
                'and must start with a letter or digit'
            )
        return v

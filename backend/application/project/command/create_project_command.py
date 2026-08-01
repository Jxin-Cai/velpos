from pydantic import BaseModel, ConfigDict, field_validator


class CreateProjectCommand(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str = ""
    github_url: str = ""
    user_id: int = 1

    @field_validator('name')
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.strip()
        if len(v) > 200:
            raise ValueError('Agent name must not exceed 200 characters')
        return v

    @field_validator('github_url')
    @classmethod
    def validate_github_url(cls, v: str) -> str:
        return v.strip()

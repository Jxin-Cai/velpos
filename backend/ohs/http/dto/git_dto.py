from __future__ import annotations

from pydantic import BaseModel, Field


class GitConfigResponse(BaseModel):
    user_name: str
    user_email: str


class GitConfigRequest(BaseModel):
    user_name: str = Field(default="", max_length=200, description="Git user.name")
    user_email: str = Field(default="", max_length=200, description="Git user.email")


class SshKeyInfo(BaseModel):
    name: str
    type: str
    public_key: str
    fingerprint: str


class SshKeyListResponse(BaseModel):
    keys: list[SshKeyInfo]


class GenerateSshKeyRequest(BaseModel):
    key_type: str = Field(default="ed25519", description="Key type: ed25519, rsa, ecdsa")
    comment: str = Field(default="", max_length=200, description="Key comment (e.g. email)")


class GenerateSshKeyResponse(BaseModel):
    name: str
    public_key: str


class SshPublicKeyResponse(BaseModel):
    public_key: str

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any

from domain.shared.business_exception import BusinessException

logger = logging.getLogger(__name__)

# Supported SSH key types
_SUPPORTED_KEY_TYPES = {"ed25519", "rsa", "ecdsa"}


class GitApplicationService:
    """Global git config and SSH key management."""

    # ── Git Config ──

    async def get_git_config(self) -> dict[str, str]:
        name = await self._git_config_get("user.name")
        email = await self._git_config_get("user.email")
        return {"user_name": name, "user_email": email}

    async def set_git_config(self, user_name: str, user_email: str) -> dict[str, str]:
        if user_name:
            await self._git_config_set("user.name", user_name)
        if user_email:
            await self._git_config_set("user.email", user_email)
        return await self.get_git_config()

    # ── SSH Keys ──

    async def list_ssh_keys(self) -> list[dict[str, str]]:
        ssh_dir = Path.home() / ".ssh"
        if not ssh_dir.is_dir():
            return []

        keys: list[dict[str, str]] = []
        for pub_file in sorted(ssh_dir.glob("*.pub")):
            private_file = pub_file.with_suffix("")
            if not private_file.exists():
                continue
            try:
                public_key = pub_file.read_text().strip()
                parts = public_key.split()
                key_type = parts[0] if parts else "unknown"
                fingerprint = await self._ssh_key_fingerprint(str(pub_file))
                keys.append({
                    "name": private_file.name,
                    "type": key_type,
                    "public_key": public_key,
                    "fingerprint": fingerprint,
                })
            except Exception:
                logger.debug("Failed to read SSH key %s", pub_file, exc_info=True)
        return keys

    async def generate_ssh_key(
        self, key_type: str = "ed25519", comment: str = "",
    ) -> dict[str, str]:
        if key_type not in _SUPPORTED_KEY_TYPES:
            raise BusinessException(
                f"Unsupported key type: {key_type}. Supported: {', '.join(sorted(_SUPPORTED_KEY_TYPES))}",
                "INVALID_KEY_TYPE",
            )

        ssh_dir = Path.home() / ".ssh"
        ssh_dir.mkdir(mode=0o700, exist_ok=True)

        key_name = f"id_{key_type}"
        key_path = ssh_dir / key_name

        if key_path.exists():
            raise BusinessException(
                f"SSH key {key_name} already exists. Delete it first to regenerate.",
                "SSH_KEY_EXISTS",
            )

        cmd = [
            "ssh-keygen", "-t", key_type,
            "-f", str(key_path),
            "-N", "",  # empty passphrase
        ]
        if comment:
            cmd.extend(["-C", comment])

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            err = stderr.decode().strip()
            raise BusinessException(f"ssh-keygen failed: {err}", "SSH_KEYGEN_FAILED")

        pub_path = key_path.with_suffix(".pub")
        public_key = pub_path.read_text().strip() if pub_path.exists() else ""

        logger.info("Generated SSH key: %s", key_name)
        return {"name": key_name, "public_key": public_key}

    async def get_ssh_public_key(self, key_name: str) -> str:
        # Sanitize key_name to prevent path traversal
        safe_name = Path(key_name).name
        pub_path = Path.home() / ".ssh" / f"{safe_name}.pub"
        if not pub_path.exists():
            raise BusinessException(
                f"SSH public key not found: {safe_name}",
                "SSH_KEY_NOT_FOUND",
            )
        return pub_path.read_text().strip()

    # ── Internal ──

    @staticmethod
    async def _git_config_get(key: str) -> str:
        proc = await asyncio.create_subprocess_exec(
            "git", "config", "--global", key,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        return stdout.decode().strip() if proc.returncode == 0 else ""

    @staticmethod
    async def _git_config_set(key: str, value: str) -> None:
        proc = await asyncio.create_subprocess_exec(
            "git", "config", "--global", key, value,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            err = stderr.decode().strip()
            raise BusinessException(f"Failed to set git config {key}: {err}", "GIT_CONFIG_FAILED")

    @staticmethod
    async def _ssh_key_fingerprint(pub_path: str) -> str:
        proc = await asyncio.create_subprocess_exec(
            "ssh-keygen", "-lf", pub_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        return stdout.decode().strip() if proc.returncode == 0 else ""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path


class AttachmentStorageGateway:
    def save(
        self,
        project_dir: str,
        session_id: str,
        filename: str,
        data: bytes,
    ) -> tuple[str, str]:
        root = self._storage_root(project_dir)
        root.mkdir(parents=True, exist_ok=True)
        safe_name = self._safe_filename(filename)
        digest = hashlib.sha256(data).hexdigest()
        path = root / session_id / f"{digest[:12]}-{safe_name}"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        resolved = path.resolve()
        if not str(resolved).startswith(str(root.resolve())):
            raise ValueError("Attachment path escapes storage root")
        return str(resolved), digest

    @staticmethod
    def _storage_root(project_dir: str) -> Path:
        if project_dir:
            root = Path(project_dir).resolve() / ".claude" / "attachments"
            project_root = Path(project_dir).resolve()
            if not str(root).startswith(str(project_root)):
                raise ValueError("Invalid project directory")
            return root
        return Path(os.getenv("TMPDIR", "/tmp")).resolve() / "velpos-attachments"

    @staticmethod
    def _safe_filename(filename: str) -> str:
        name = os.path.basename(filename or "attachment.bin")
        name = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip(".-")
        return name or "attachment.bin"

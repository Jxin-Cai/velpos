from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path


class AttachmentStorageGateway:
    UPLOAD_ROOT = ".upload-file"

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
        safe_session_id = self._safe_session_id(session_id)
        digest = hashlib.sha256(data).hexdigest()
        session_root = (root / safe_session_id).resolve()
        if session_root != root.resolve() and root.resolve() not in session_root.parents:
            raise ValueError("Attachment session path escapes storage root")
        session_root.mkdir(parents=True, exist_ok=True)
        resolved = self._write_unique_file(session_root, safe_name, data, digest)
        if resolved != root.resolve() and root.resolve() not in resolved.parents:
            raise ValueError("Attachment path escapes storage root")
        return str(resolved), digest

    def stage_file(
        self,
        project_dir: str,
        session_id: str,
        filename: str,
        source_path: str,
    ) -> tuple[str, str]:
        source = Path(source_path).resolve()
        if not source.is_file():
            raise FileNotFoundError(f"Attachment source file does not exist: {source}")
        size = source.stat().st_size
        if size > 25 * 1024 * 1024:
            raise ValueError("Attachment exceeds 25MB limit")
        return self.save(project_dir, session_id, filename, source.read_bytes())

    @staticmethod
    def _storage_root(project_dir: str) -> Path:
        if project_dir:
            project_root = Path(project_dir).resolve()
            root = project_root / AttachmentStorageGateway.UPLOAD_ROOT
            if root != project_root and project_root not in root.parents:
                raise ValueError("Invalid project directory")
            return root
        return Path(os.getenv("TMPDIR", "/tmp")).resolve() / "velpos-attachments"

    @staticmethod
    def _safe_filename(filename: str) -> str:
        name = os.path.basename(filename or "attachment.bin")
        original = Path(name)
        safe_stem = re.sub(
            r"[^A-Za-z0-9_-]+",
            "-",
            original.stem,
        ).strip("-")
        safe_suffix = re.sub(
            r"[^A-Za-z0-9.]+",
            "",
            original.suffix,
        )
        if not safe_stem:
            safe_stem = "attachment"
        return f"{safe_stem}{safe_suffix}" or "attachment.bin"

    @staticmethod
    def _safe_session_id(session_id: str) -> str:
        value = re.sub(r"[^A-Za-z0-9._-]+", "-", session_id or "").strip(".-")
        if not value:
            raise ValueError("Session id is required for attachment storage")
        return value

    @staticmethod
    def _write_unique_file(
        target_dir: Path,
        safe_name: str,
        data: bytes,
        digest: str,
    ) -> Path:
        original = Path(safe_name)
        candidates = [
            target_dir / safe_name,
            target_dir / f"{original.stem}-{digest[:10]}{original.suffix}",
        ]
        index = 2
        while True:
            candidate = candidates.pop(0) if candidates else (
                target_dir / f"{original.stem}-{digest[:10]}-{index}{original.suffix}"
            )
            index += 1
            try:
                descriptor = os.open(candidate, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError:
                if hashlib.sha256(candidate.read_bytes()).hexdigest() == digest:
                    return candidate.resolve()
                continue
            with os.fdopen(descriptor, "wb") as file_obj:
                file_obj.write(data)
            return candidate.resolve()

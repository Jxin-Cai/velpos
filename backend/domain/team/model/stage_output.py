from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from domain.team.model.status import StageOutputStatus
from domain.team.model.team_domain_error import TeamDomainError


@dataclass(frozen=True)
class StageOutputArtifact:
    id: str
    stage_output_id: str
    name: str
    path: str
    media_type: str
    created_at: datetime


@dataclass
class StageOutput:
    id: str
    card_id: str
    execution_id: str
    revision: int
    schema_version: int
    status: StageOutputStatus
    content: dict[str, Any]
    rendered_markdown: str
    source_session_id: str
    checksum: str
    compression_method: str
    created_at: datetime
    previous_output_id: str | None = None
    artifacts: list[StageOutputArtifact] = field(default_factory=list)

    @classmethod
    def create_ready(
        cls,
        *,
        card_id: str,
        execution_id: str,
        revision: int,
        content: dict[str, Any],
        rendered_markdown: str,
        source_session_id: str,
        checksum: str,
        compression_method: str,
        previous_output_id: str | None = None,
    ) -> "StageOutput":
        required = {
            "card_id": card_id,
            "execution_id": execution_id,
            "rendered_markdown": rendered_markdown,
            "source_session_id": source_session_id,
            "checksum": checksum,
            "compression_method": compression_method,
        }
        blank = next((name for name, value in required.items() if not value.strip()), None)
        if blank is not None:
            raise TeamDomainError(f"{blank} must not be blank")
        if revision < 1:
            raise TeamDomainError("stage output revision must be positive")

        return cls(
            id=str(uuid4()),
            card_id=card_id,
            execution_id=execution_id,
            revision=revision,
            schema_version=1,
            status=StageOutputStatus.READY,
            content=content,
            rendered_markdown=rendered_markdown,
            source_session_id=source_session_id,
            checksum=checksum,
            compression_method=compression_method,
            created_at=datetime.now(timezone.utc),
            previous_output_id=previous_output_id,
        )

    def add_artifact(self, *, name: str, path: str, media_type: str = "") -> None:
        if not name.strip():
            raise TeamDomainError("stage output artifact name must not be blank")
        if not path.strip():
            raise TeamDomainError("stage output artifact path must not be blank")
        self.artifacts.append(
            StageOutputArtifact(
                id=str(uuid4()),
                stage_output_id=self.id,
                name=name,
                path=path,
                media_type=media_type,
                created_at=datetime.now(timezone.utc),
            )
        )

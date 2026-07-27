from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from domain.team.model.stage_output import StageOutput, StageOutputArtifact
from domain.team.model.status import StageOutputStatus
from domain.team.repository.stage_output_repository import StageOutputRepository
from infr.repository.team_model import CardStageOutputModel, StageOutputArtifactModel


class StageOutputRepositoryImpl(StageOutputRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, stage_output: StageOutput) -> None:
        await self._session.merge(self._to_model(stage_output))
        await self._session.flush()

    async def find_by_id(self, stage_output_id: str) -> StageOutput | None:
        stmt = (
            select(CardStageOutputModel)
            .options(selectinload(CardStageOutputModel.artifacts))
            .where(CardStageOutputModel.id == stage_output_id)
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_domain(model) if model is not None else None

    async def find_latest_by_execution_id(
        self, execution_id: str
    ) -> StageOutput | None:
        stmt = (
            select(CardStageOutputModel)
            .options(selectinload(CardStageOutputModel.artifacts))
            .where(CardStageOutputModel.execution_id == execution_id)
            .order_by(
                CardStageOutputModel.revision.desc(),
                CardStageOutputModel.created_time.desc(),
            )
            .limit(1)
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_domain(model) if model is not None else None

    async def find_by_card_id(self, card_id: str) -> list[StageOutput]:
        stmt = (
            select(CardStageOutputModel)
            .options(selectinload(CardStageOutputModel.artifacts))
            .where(CardStageOutputModel.card_id == card_id)
            .order_by(
                CardStageOutputModel.created_time.asc(),
                CardStageOutputModel.revision.asc(),
            )
        )
        result = await self._session.execute(stmt)
        return [self._to_domain(model) for model in result.scalars().all()]

    async def remove_by_card_id(self, card_id: str) -> None:
        output_ids = select(CardStageOutputModel.id).where(
            CardStageOutputModel.card_id == card_id
        )
        await self._session.execute(
            delete(StageOutputArtifactModel).where(
                StageOutputArtifactModel.stage_output_id.in_(output_ids)
            )
        )
        await self._session.execute(
            delete(CardStageOutputModel).where(CardStageOutputModel.card_id == card_id)
        )
        await self._session.flush()

    @staticmethod
    def _to_model(stage_output: StageOutput) -> CardStageOutputModel:
        return CardStageOutputModel(
            id=stage_output.id,
            card_id=stage_output.card_id,
            execution_id=stage_output.execution_id,
            previous_output_id=stage_output.previous_output_id,
            revision=stage_output.revision,
            schema_version=stage_output.schema_version,
            status=stage_output.status.value,
            content_json=stage_output.content,
            rendered_markdown=stage_output.rendered_markdown,
            source_session_id=stage_output.source_session_id,
            checksum=stage_output.checksum,
            compression_method=stage_output.compression_method,
            created_time=stage_output.created_at,
            artifacts=[
                StageOutputArtifactModel(
                    id=artifact.id,
                    stage_output_id=artifact.stage_output_id,
                    name=artifact.name,
                    path=artifact.path,
                    media_type=artifact.media_type,
                    created_time=artifact.created_at,
                )
                for artifact in stage_output.artifacts
            ],
        )

    @staticmethod
    def _to_domain(model: CardStageOutputModel) -> StageOutput:
        return StageOutput(
            id=model.id,
            card_id=model.card_id,
            execution_id=model.execution_id,
            previous_output_id=model.previous_output_id,
            revision=model.revision,
            schema_version=model.schema_version,
            status=StageOutputStatus(model.status),
            content=dict(model.content_json or {}),
            rendered_markdown=model.rendered_markdown,
            source_session_id=model.source_session_id,
            checksum=model.checksum,
            compression_method=model.compression_method,
            created_at=model.created_time,
            artifacts=[
                StageOutputArtifact(
                    id=artifact.id,
                    stage_output_id=artifact.stage_output_id,
                    name=artifact.name,
                    path=artifact.path,
                    media_type=artifact.media_type,
                    created_at=artifact.created_time,
                )
                for artifact in model.artifacts
            ],
        )

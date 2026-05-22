from __future__ import annotations

from domain.session.model.sdk_binding_result import SdkBindingResult
from domain.session.model.session import Session
from domain.session.repository.session_repository import SessionRepository


class SdkSessionBindingService:

    def __init__(self, session_repository: SessionRepository) -> None:
        self._repository = session_repository

    @staticmethod
    def is_fork(sdk_session_id: str) -> bool:
        return sdk_session_id.startswith("fork:")

    async def resolve_for_resume(self, session: Session) -> SdkBindingResult:
        sdk_session_id = session.sdk_session_id
        if not sdk_session_id:
            return SdkBindingResult(accepted=False, resolved_id="")

        if self.is_fork(sdk_session_id):
            return SdkBindingResult(accepted=True, resolved_id=sdk_session_id)

        owner = await self._repository.find_by_sdk_session_id(sdk_session_id)
        if owner is None or owner.session_id == session.session_id:
            return SdkBindingResult(accepted=True, resolved_id=sdk_session_id)

        session.update_sdk_session_id("")
        return SdkBindingResult(
            accepted=False,
            resolved_id="",
            conflict_session_id=owner.session_id,
        )

    async def try_bind(
        self,
        session: Session,
        new_sdk_session_id: str,
    ) -> SdkBindingResult:
        if not new_sdk_session_id or new_sdk_session_id == session.sdk_session_id:
            return SdkBindingResult(accepted=False, resolved_id=session.sdk_session_id)

        if self.is_fork(new_sdk_session_id):
            session.update_sdk_session_id(new_sdk_session_id)
            return SdkBindingResult(accepted=True, resolved_id=new_sdk_session_id)

        owner = await self._repository.find_by_sdk_session_id(new_sdk_session_id)
        if owner is not None and owner.session_id != session.session_id:
            session.update_sdk_session_id("")
            return SdkBindingResult(
                accepted=False,
                resolved_id="",
                conflict_session_id=owner.session_id,
            )

        session.update_sdk_session_id(new_sdk_session_id)
        return SdkBindingResult(accepted=True, resolved_id=new_sdk_session_id)

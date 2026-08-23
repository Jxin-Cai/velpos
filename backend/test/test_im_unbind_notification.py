"""``im_unbound`` must never reach clients while the removal is uncommitted.

Clients react to the broadcast by re-reading binding state on a different DB
connection. If the delete is still inside an open transaction, that read serves
the row we just removed and the stale value overwrites the fresh state the
client already applied — the binding appears to come back.
"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from application.im_binding.im_channel_application_service import (
    ImChannelApplicationService,
)
from domain.im_binding.acl.im_channel_adapter import BindResult
from domain.im_binding.model.binding_status import BindingStatus
from domain.im_binding.model.channel_type import ImChannelType
from domain.im_binding.model.im_binding import ImBinding


def _bound_binding(channel_id: str = "channel1") -> ImBinding:
    return ImBinding.reconstitute(
        id="binding1",
        session_id="session1",
        im_user_id="",
        im_token="",
        binding_status=BindingStatus.BOUND,
        friend_user_id="",
        qr_code_data="",
        created_at=datetime.now(),
        channel_type=ImChannelType.LARK,
        channel_id=channel_id,
        config={},
    )


def _recorder(journal: list[str], label: str) -> AsyncMock:
    return AsyncMock(side_effect=lambda *_, **__: journal.append(label))


def _service(
    *,
    binding_repo: Mock,
    init_repo: Mock,
    connection_manager: Mock,
    commit: AsyncMock,
) -> ImChannelApplicationService:
    service = ImChannelApplicationService(
        registry=Mock(),
        binding_repo=binding_repo,
        init_repo=init_repo,
        connection_manager=connection_manager,
        commit_unit_of_work=commit,
    )
    service._facade = Mock(stop_listening=AsyncMock(), unbind=AsyncMock())
    return service


@pytest.mark.asyncio
async def test_commits_removal_before_broadcast_when_session_is_unbound():
    # Arrange
    journal: list[str] = []
    binding_repo = Mock(
        find_by_session_id=AsyncMock(return_value=_bound_binding()),
        remove=_recorder(journal, "remove-binding"),
    )
    connection_manager = Mock(broadcast=_recorder(journal, "broadcast"))
    commit = _recorder(journal, "commit")
    service = _service(
        binding_repo=binding_repo,
        init_repo=Mock(),
        connection_manager=connection_manager,
        commit=commit,
    )

    # Act
    await service.unbind("session1")

    # Assert
    assert journal == ["remove-binding", "commit", "broadcast"]


@pytest.mark.asyncio
async def test_skips_broadcast_when_session_is_rebound_to_another_channel():
    # Arrange
    binding_repo = Mock(
        find_by_channel_id=AsyncMock(return_value=None),
        find_by_session_id=AsyncMock(return_value=_bound_binding("channel1")),
        remove=AsyncMock(),
        save=AsyncMock(),
    )
    init_repo = Mock(
        find_by_id=AsyncMock(
            return_value=SimpleNamespace(
                channel_type=ImChannelType.LARK, is_ready=True, config={},
            ),
        ),
    )
    connection_manager = Mock(broadcast=AsyncMock())
    service = _service(
        binding_repo=binding_repo,
        init_repo=init_repo,
        connection_manager=connection_manager,
        commit=AsyncMock(),
    )
    service._facade.route_config_keys = Mock(return_value=())
    service._facade.bind = AsyncMock(
        return_value=BindResult(status=BindingStatus.BOUND, channel_address="addr"),
    )
    service.start_channel_listener = AsyncMock()
    service._send_bind_notification = AsyncMock()

    # Act
    await service.bind("session1", "channel2", {})

    # Assert
    connection_manager.broadcast.assert_not_awaited()


@pytest.mark.asyncio
async def test_broadcasts_after_instance_removal_when_bound_channel_is_deleted():
    # Arrange
    journal: list[str] = []
    binding_repo = Mock(
        find_by_channel_id=AsyncMock(return_value=_bound_binding()),
        remove=_recorder(journal, "remove-binding"),
    )
    init_repo = Mock(
        find_by_id=AsyncMock(return_value=SimpleNamespace(id="channel1")),
        remove=_recorder(journal, "remove-instance"),
    )
    connection_manager = Mock(broadcast=_recorder(journal, "broadcast"))
    commit = _recorder(journal, "commit")
    service = _service(
        binding_repo=binding_repo,
        init_repo=init_repo,
        connection_manager=connection_manager,
        commit=commit,
    )

    # Act
    await service.delete_channel_instance("channel1")

    # Assert
    assert journal == ["remove-binding", "remove-instance", "commit", "broadcast"]

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from starlette.websockets import WebSocketDisconnect

from ohs.ws.session_ws import _handle_set_permission_mode


@pytest.mark.asyncio
async def test_disconnect_propagated_without_second_send_when_permission_mode_changed() -> None:
    # Arrange
    websocket = SimpleNamespace(
        send_json=AsyncMock(side_effect=WebSocketDisconnect(code=1006)),
    )
    service = SimpleNamespace(set_permission_mode=AsyncMock())
    context = SimpleNamespace(
        websocket=websocket,
        service=service,
        session_id="session-1",
    )

    # Act / Assert
    with pytest.raises(WebSocketDisconnect):
        await _handle_set_permission_mode(
            context,
            {"action": "set_permission_mode", "mode": "bypassPermissions"},
        )

    websocket.send_json.assert_awaited_once_with({
        "event": "info",
        "message": "Permission mode changed to bypassPermissions",
    })

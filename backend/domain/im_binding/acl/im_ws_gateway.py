from abc import ABC, abstractmethod
from typing import Any, AsyncIterator


class ImWsGateway(ABC):

    @abstractmethod
    async def connect(
        self, im_user_id: str, im_token: str
    ) -> None:
        """Establish a WebSocket connection to the IM Server.

        Uses im_user_id and im_token as authentication parameters to connect
        to the IM Server WS endpoint. platformID is fixed to 5 (Web).
        Starts listening for message pushes upon successful connection.
        Raises BusinessException("IM_WS_CONNECT_FAILED") if the connection fails.
        If already connected, treats the call as idempotent and does not reconnect.
        """
        ...

    @abstractmethod
    async def disconnect(self, im_user_id: str) -> None:
        """Disconnect the WebSocket connection for the specified user.

        Releases connection resources and stops message listening.
        If no active connection exists for the user, silently ignores the call
        without raising an exception.
        """
        ...

    @abstractmethod
    def is_connected(self, im_user_id: str) -> bool:
        """Check whether the specified user has an active WebSocket connection.

        Returns True if the connection is active, False if there is no connection
        or it has been disconnected.
        """
        ...

    @abstractmethod
    async def listen_messages(
        self, im_user_id: str
    ) -> AsyncIterator[dict[str, Any]]:
        """Listen for IM messages received by the specified user.

        Returns an async iterator that yields messages pushed by the IM Server
        (reqIdentifier=2001). Each message is returned as a dict containing
        sender_id (str), content (str), and send_time (int, millisecond timestamp).
        The iterator terminates automatically when the connection is disconnected.
        Requires a prior connect call to establish the connection; otherwise raises
        BusinessException("IM_WS_NOT_CONNECTED").
        """
        ...

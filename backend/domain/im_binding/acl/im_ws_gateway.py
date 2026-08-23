from abc import ABC, abstractmethod


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
    async def close_all(self) -> None:
        """Drop every connection this gateway holds, for process shutdown."""
        ...

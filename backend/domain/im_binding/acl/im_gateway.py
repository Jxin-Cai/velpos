from abc import ABC, abstractmethod


class ImGateway(ABC):

    @abstractmethod
    async def register_user(self, im_user_id: str, nickname: str) -> None:
        """Register a new user on the IM Server.

        Calls the IM Server /user/user_register endpoint with admin authentication.
        im_user_id serves as the unique user identifier, nickname as the display name.
        If the im_user_id already exists, the IM Server treats it as an idempotent
        operation and does not raise an error.
        Raises BusinessException("IM_REGISTER_FAILED") if the IM Server is
        unreachable or returns an error.
        """
        ...

    @abstractmethod
    async def get_user_token(self, im_user_id: str) -> str:
        """Obtain an access token for the specified IM user.

        Calls the IM Server /auth/get_user_token endpoint with admin authentication.
        Returns the issued token string.
        Raises BusinessException("IM_TOKEN_FAILED") if the IM Server is
        unreachable or returns an error.
        """
        ...

    @abstractmethod
    async def import_friend(
        self, owner_user_id: str, friend_user_id: str
    ) -> None:
        """Import a bidirectional friend relationship via admin privileges.

        Calls the IM Server /friend/import_friend endpoint, bypassing the friend
        request flow. owner_user_id is the product-side IM user, friend_user_id is
        the mobile-side IM user.
        If the friend relationship already exists, the IM Server treats it as an
        idempotent operation and does not raise an error.
        Raises BusinessException("IM_IMPORT_FRIEND_FAILED") if the IM Server is
        unreachable or returns an error.
        """
        ...

    @abstractmethod
    async def send_message(
        self,
        sender_id: str,
        receiver_id: str,
        content: str,
    ) -> None:
        """Send a text message through the IM Server.

        Calls the IM Server /msg/send_msg endpoint with admin authentication.
        sender_id is the sender IM user ID, receiver_id is the receiver IM user ID.
        content is the text message body.
        sessionType is fixed to single chat (1), contentType is fixed to text (101).
        Raises BusinessException("IM_SEND_MESSAGE_FAILED") if the IM Server is
        unreachable or returns an error.
        """
        ...

    @abstractmethod
    async def generate_add_friend_link(self, im_user_id: str) -> str:
        """Generate an add-friend link for the specified IM user.

        Constructs a standard add-friend link URL based on the IM Server address
        and im_user_id, intended for the frontend to render as a QR code.
        Returns the add-friend link URL string.
        """
        ...

from domain.shared.business_exception import BusinessException


class TeamDomainError(BusinessException):
    """Raised when a team-domain invariant is violated."""

    def __init__(self, message: str) -> None:
        super().__init__(message=message, code="TEAM_DOMAIN_ERROR")

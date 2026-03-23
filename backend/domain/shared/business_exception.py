class BusinessException(Exception):
    """Business exception base class.

    Carries an error code and a human-readable message.
    Caught by the global exception handler in the Infrastructure layer.
    """

    def __init__(self, message: str, code: str = "BUSINESS_ERROR") -> None:
        super().__init__(message)
        self.code = code
        self.message = message

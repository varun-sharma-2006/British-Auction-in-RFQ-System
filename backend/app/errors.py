class DomainError(Exception):
    """A business-rule violation that maps cleanly onto an HTTP status."""

    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.message = message

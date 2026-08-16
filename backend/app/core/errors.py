class AppError(Exception):
    def __init__(self, code: str, message: str, status_code: int):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class InvalidSelectorError(AppError):
    def __init__(self) -> None:
        super().__init__("INVALID_SELECTOR", "The CSS selector is not valid.", 400)


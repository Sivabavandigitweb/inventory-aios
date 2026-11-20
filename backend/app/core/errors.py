from dataclasses import dataclass


@dataclass
class AppError(Exception):
    """Safe application error for deliberate client-facing failures."""

    code: str
    message: str
    status_code: int = 400

    def __str__(self) -> str:
        return self.message
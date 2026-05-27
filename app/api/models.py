"""Data response models."""

from typing import Any

from pydantic import BaseModel


class ResponseModel(BaseModel):
    """Standard success response."""

    code: int = 200
    message: str = "success"
    data: Any | None = None


class ErrorResponse(BaseModel):
    """Standard error response."""

    code: int = 400
    message: str = "An error occurred"
    detail: Any | None = None

"""
数据响应模型
"""

from typing import Any, Optional
from pydantic import BaseModel


class ResponseModel(BaseModel):
    """标准成功响应"""
    code: int = 200
    message: str = "success"
    data: Optional[Any] = None


class ErrorResponse(BaseModel):
    """标准错误响应"""
    code: int = 400
    message: str = "An error occurred"
    detail: Optional[Any] = None

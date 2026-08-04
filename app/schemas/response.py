from typing import Generic, TypeVar, Optional
from pydantic import BaseModel

T = TypeVar("T")


class GenericResponse(BaseModel, Generic[T]):
    status: str = "OK"
    data: Optional[T] = None
    messages: list[str] = []

from __future__ import annotations
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict


class FilterItem(BaseModel):
    field: str
    operation: Optional[str] = "eq"
    value: Any

    model_config = ConfigDict(from_attributes=True)


class PublicationQuery(BaseModel):
    # New format: list of filter items: [{"field":"title","operation":"ilike","value":"x"}, ...]
    filters: Optional[List[FilterItem]] = None
    page: int = 1
    size: int = 20
    order_by: Optional[str] = None
    order_dir: str = "asc"

    model_config = ConfigDict(from_attributes=True)

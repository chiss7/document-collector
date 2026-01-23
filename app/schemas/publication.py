from __future__ import annotations
from typing import List, Optional
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class SubjectDTO(BaseModel):
    id: Optional[int]
    name: str
    language: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class ContributorDTO(BaseModel):
    id: Optional[int]
    name: str
    role: str
    order: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


class PublicationDTO(BaseModel):
    id: Optional[int]
    title: str
    abstract: Optional[str] = None
    source_url: Optional[str] = None
    uuid: Optional[str] = None
    published_date: Optional[date] = None
    accessioned_date: Optional[datetime] = None
    available_date: Optional[datetime] = None
    extent: Optional[str] = None
    publisher: Optional[str] = None
    rights: Optional[str] = None
    rights_uri: Optional[str] = None
    type: Optional[str] = None
    entity_type: Optional[str] = None
    subjects: List[SubjectDTO] = []
    contributors: List[ContributorDTO] = []

    model_config = ConfigDict(from_attributes=True)

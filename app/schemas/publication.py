from __future__ import annotations
from typing import List, Optional
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, field_validator


class SubjectDTO(BaseModel):
    id: Optional[int] = None
    name: str
    language: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class ContributorDTO(BaseModel):
    id: Optional[int] = None
    name: str
    role: str
    order: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


class PublicationDTO(BaseModel):
    id: Optional[int] = None
    title: str
    abstract: Optional[str] = None
    original_abstract: Optional[str] = None
    source_url: Optional[str] = None
    pdf_url: Optional[str] = None
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


class PublicationCreateDTO(BaseModel):
    title: str
    abstract: str
    original_abstract: Optional[str] = None
    source_url: Optional[str] = None
    pdf_url: Optional[str] = None
    published_date: Optional[date] = None
    accessioned_date: Optional[datetime] = None
    available_date: Optional[datetime] = None
    extent: Optional[str] = None
    publisher: Optional[str] = None
    rights: Optional[str] = None
    rights_uri: Optional[str] = None
    type: Optional[str] = None
    entity_type: Optional[str] = None
    # For creation we accept simple subject names
    subjects: List[str] = []
    # Contributors can be provided as objects (name, role, order)
    contributors: List[ContributorDTO] = []

    model_config = ConfigDict(from_attributes=True)

    @field_validator("title")
    def _title_must_not_be_empty(cls, v: str):
        if not v or not str(v).strip():
            raise ValueError("title is required and must not be empty")
        return v

    @field_validator("abstract")
    def _abstract_must_not_be_empty(cls, v: str):
        if not v or not str(v).strip():
            raise ValueError("abstract is required and must not be empty")
        return v

    @field_validator("subjects")
    def _subjects_must_have_items(cls, v: List[str]):
        if not v or len(v) == 0:
            raise ValueError("subjects must contain at least one item")
        return v

    @field_validator("contributors")
    def _contributors_must_have_items(cls, v: List[ContributorDTO]):
        if not v or len(v) == 0:
            raise ValueError("contributors must contain at least one item")
        return v

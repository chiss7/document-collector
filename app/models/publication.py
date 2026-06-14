from datetime import date, datetime
from typing import List, Dict, Any, Optional

from sqlalchemy import String, Text, DateTime, Table, Column, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base

# Association table for many-to-many Publication <-> Subject
publication_subjects = Table(
    "publication_subjects",
    Base.metadata,
    Column("publication_id", Integer, ForeignKey("publications.id", ondelete="CASCADE"), primary_key=True),
    Column("subject_id", Integer, ForeignKey("subjects.id", ondelete="CASCADE"), primary_key=True),
)


class Publication(Base):
    __tablename__ = "publications"

    id: Mapped[int] = mapped_column(primary_key=True)

    title: Mapped[str] = mapped_column(String(500))

    abstract: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    source_url: Mapped[str] = mapped_column(String(1000), unique=True, nullable=True)

    published_date: Mapped[Optional[date]] = mapped_column(nullable=True)
    accessioned_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    available_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relación many-to-many a `Subject`
    subjects: Mapped[List["Subject"]] = relationship(
        "Subject",
        secondary=publication_subjects,
        back_populates="publications",
    )

    # Journal name (OAI source)
    journal_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    # Campos adicionales extraídos desde metadata
    uuid: Mapped[Optional[str]] = mapped_column(String(100), nullable=False)
    extent: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    publisher: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    rights: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    rights_uri: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    original_abstract: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    pdf_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    entity_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Relación a contributors (authors/advisors)
    contributors: Mapped[List["Contributor"]] = relationship(
        "Contributor",
        back_populates="publication",
        cascade="all, delete-orphan",
    )
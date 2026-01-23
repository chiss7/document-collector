from typing import List, Optional

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Subject(Base):
    __tablename__ = "subjects"

    id: Mapped[int] = mapped_column(primary_key=True)

    name: Mapped[str] = mapped_column(String(300), unique=True, nullable=False)

    # Optional: store original language if desired in future
    language: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)

    publications: Mapped[List["Publication"]] = relationship(
        "Publication",
        secondary="publication_subjects",
        back_populates="subjects",
    )

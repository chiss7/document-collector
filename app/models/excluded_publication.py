from typing import Optional
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class ExcludedPublication(Base):
    __tablename__ = "excluded_publication"

    id: Mapped[int] = mapped_column(primary_key=True)

    uuid: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    title: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    url: Mapped[str] = mapped_column(String(1000), unique=True)

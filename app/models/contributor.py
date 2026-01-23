import enum
from typing import Optional

from sqlalchemy import String, Enum as SAEnum, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ContributorRole(enum.Enum):
    author = "author"
    advisor = "advisor"


class Contributor(Base):
    __tablename__ = "contributors"

    id: Mapped[int] = mapped_column(primary_key=True)

    publication_id: Mapped[int] = mapped_column(ForeignKey("publications.id", ondelete="CASCADE"))

    # Nombre completo del contributor
    name: Mapped[str] = mapped_column(String(300))

    # Role: 'author' o 'advisor' (stored as text to avoid DB enum type requirement)
    role: Mapped[ContributorRole] = mapped_column(SAEnum(ContributorRole, native_enum=False), nullable=False)

    # Orden opcional para mantener orden de autores/asesores
    order: Mapped[Optional[int]] = mapped_column(nullable=True)

    publication = relationship("Publication", back_populates="contributors")

from typing import Optional
from sqlalchemy import func, select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories.publication_repository import PublicationRepository
from app.db.session import AsyncSessionLocal
from app.models.publication import Publication, publication_subjects
from app.models.contributor import Contributor, ContributorRole
from app.models.subject import Subject
from app.schemas.publication import PublicationCreateDTO, FilterOptionsResponse, AIPublicationStatsResponse, LatestPublicationItem
import uuid
import logging
from fastapi import UploadFile
from datetime import datetime

logger = logging.getLogger(__name__)

from app.core.storage import get_storage_provider


async def get_all_publications(session: Optional[AsyncSession] = None, limit: int | None = None, offset: int = 0):
    """Return list of Publication ORM objects. If no session provided, create one."""
    own = session is None
    if own:
        async with AsyncSessionLocal() as session:
            return await PublicationRepository.findAll(session, limit=limit, offset=offset)
    return await PublicationRepository.findAll(session, limit=limit, offset=offset)


async def create_publication(payload: PublicationCreateDTO, pdf_file: UploadFile | None = None, session: Optional[AsyncSession] = None) -> int:
    """Create a single Publication from `PublicationCreateDTO` and return its id."""
    own = session is None
    async def _create(sess: AsyncSession):
        # generate uuid for publication (server-side)
        generated_uuid = str(uuid.uuid4())

        pub = Publication(
            title=payload.title,
            abstract=payload.abstract,
            original_abstract=payload.original_abstract or payload.abstract,
            source_url=payload.source_url if payload.source_url else None,
            pdf_url=payload.pdf_url,
            uuid=generated_uuid,
            published_date=datetime.now(),
            accessioned_date=datetime.now(),
            available_date=datetime.now(),
            extent=payload.extent,
            publisher="Universidad Central del Ecuador",
            rights="openAccess",
            rights_uri=payload.rights_uri,
            type=payload.type,
            entity_type=payload.type,
        )

        # attach contributors
        contrib_objs = []
        for c in payload.contributors or []:
            role_val = c.role if isinstance(c.role, str) else (c.role.value if hasattr(c.role, 'value') else c.role)
            try:
                role_enum = ContributorRole(role_val)
            except Exception:
                # fallback: try to interpret by name
                try:
                    role_enum = ContributorRole[role_val]
                except Exception:
                    role_enum = ContributorRole.author

            contrib = Contributor(name=c.name, role=role_enum, order=c.order)
            contrib_objs.append(contrib)

        if contrib_objs:
            pub.contributors = contrib_objs

        # subjects: use transient attribute used by repository
        pub._subject_names = payload.subjects or []

        # If a PDF file was provided, upload via the configured storage provider
        if pdf_file is not None:
            try:
                try:
                    pdf_file.file.seek(0)
                except Exception:
                    pass
                try:
                    data = pdf_file.file.read()
                except Exception:
                    data = await pdf_file.read()

                provider = get_storage_provider()
                pub.pdf_url = await provider.upload(data, f"{generated_uuid}.pdf")
            except Exception as e:
                logger.error("PDF upload failed: %s", repr(e))
                raise RuntimeError(f"PDF upload failed: {e}")

        return await PublicationRepository.save(sess, pub)

    if own:
        async with AsyncSessionLocal() as sess:
            return await _create(sess)
    return await _create(session)


async def get_filter_options(session: Optional[AsyncSession] = None) -> FilterOptionsResponse:
    """Return distinct non-null values for publisher, entity_type, and journal_name."""
    own = session is None
    if own:
        async with AsyncSessionLocal() as s:
            return await _fetch_filter_options(s)
    return await _fetch_filter_options(session)


async def _fetch_filter_options(session: AsyncSession) -> FilterOptionsResponse:
    publisher = await PublicationRepository.get_distinct_values(session, "publisher")
    entity_type = await PublicationRepository.get_distinct_values(session, "entity_type")
    journal_name = await PublicationRepository.get_distinct_values(session, "journal_name")
    return FilterOptionsResponse(
        publisher=publisher,
        entity_type=entity_type,
        journal_name=journal_name,
    )


async def get_ai_publication_stats(session: Optional[AsyncSession] = None) -> AIPublicationStatsResponse:
    own = session is None
    if own:
        async with AsyncSessionLocal() as session:
            return await _fetch_ai_stats(session)
    return await _fetch_ai_stats(session)


async def _fetch_ai_stats(session: AsyncSession) -> AIPublicationStatsResponse:
    total_q = select(func.count(Publication.id))
    journal_q = select(func.count(Publication.id)).where(Publication.entity_type == "JournalArticle")
    academic_q = select(func.count(Publication.id)).where(Publication.entity_type == "AcademicPublication")
    last_class_q = select(func.max(Publication.classified_at))

    total = await session.scalar(total_q) or 0
    journal_count = await session.scalar(journal_q) or 0
    academic_count = await session.scalar(academic_q) or 0
    thesis_count = total - journal_count - academic_count
    last_classification_date = await session.scalar(last_class_q)

    most_used_q = (
        select(Subject.name, func.count(publication_subjects.c.publication_id).label("cnt"))
        .select_from(Subject)
        .join(publication_subjects, Subject.id == publication_subjects.c.subject_id)
        .group_by(Subject.id, Subject.name)
        .order_by(func.count(publication_subjects.c.publication_id).desc())
        .limit(1)
    )
    result = await session.execute(most_used_q)
    row = result.one_or_none()
    most_used_subject = row[0] if row else None

    # Top 3 latest publications per category
    journal_latest_q = (
        select(Publication.title, Publication.classified_at)
        .where(Publication.entity_type == "JournalArticle", Publication.classified_at.isnot(None))
        .order_by(Publication.classified_at.desc())
        .limit(3)
    )
    academic_latest_q = (
        select(Publication.title, Publication.classified_at)
        .where(Publication.entity_type == "AcademicPublication", Publication.classified_at.isnot(None))
        .order_by(Publication.classified_at.desc())
        .limit(3)
    )
    thesis_latest_q = (
        select(Publication.title, Publication.classified_at)
        .where(
            or_(
                Publication.entity_type.is_(None),
                ~Publication.entity_type.in_(["JournalArticle", "AcademicPublication"]),
            ),
            Publication.classified_at.isnot(None),
        )
        .order_by(Publication.classified_at.desc())
        .limit(3)
    )

    last_publications: list[LatestPublicationItem] = []
    for row in (await session.execute(journal_latest_q)).all():
        last_publications.append(LatestPublicationItem(title=row[0], category="Artículo de Revista", classified_at=row[1]))
    for row in (await session.execute(academic_latest_q)).all():
        last_publications.append(LatestPublicationItem(title=row[0], category="Publicación Académica", classified_at=row[1]))
    for row in (await session.execute(thesis_latest_q)).all():
        last_publications.append(LatestPublicationItem(title=row[0], category="Tesis", classified_at=row[1]))

    return AIPublicationStatsResponse(
        total=total,
        thesis_count=thesis_count,
        academic_publication_count=academic_count,
        journal_article_count=journal_count,
        most_used_subject=most_used_subject,
        last_classification_date=last_classification_date,
        last_publications=last_publications,
    )

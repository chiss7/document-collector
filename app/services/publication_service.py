from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories.publication_repository import PublicationRepository
from app.db.session import AsyncSessionLocal
from app.models.publication import Publication
from app.models.contributor import Contributor, ContributorRole
from app.schemas.publication import PublicationCreateDTO
import uuid
from fastapi import UploadFile
import io

from app.core.supabase_config import client as supabase_client
from app.core.config import settings


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
            published_date=payload.published_date,
            accessioned_date=payload.accessioned_date,
            available_date=payload.available_date,
            extent=payload.extent,
            publisher=payload.publisher,
            rights=payload.rights,
            rights_uri=payload.rights_uri,
            type=payload.type,
            entity_type=payload.entity_type,
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

        # If a PDF file was provided, upload to Supabase Storage
        if pdf_file is not None:
            try:
                # ensure file pointer at start
                try:
                    pdf_file.file.seek(0)
                except Exception:
                    pass
                # read bytes
                try:
                    data = pdf_file.file.read()
                except Exception:
                    data = await pdf_file.read()

                sb = supabase_client()
                bucket = settings.SUPABASE_BUCKET or "ia-docs-uce"
                path = f"{generated_uuid}.pdf"
                # upload (upsert True to overwrite if exists)
                # upload bytes directly (supabase client expects bytes/bytearray)
                # Note: some supabase client versions do not accept `upsert` kwarg
                sb.storage.from_(bucket).upload(path, data, file_options={
                    "content-type": "application/pdf",
                    "cache-control": "3600"
                },)

                # try to get public URL from client, fallback to constructed public URL
                try:
                    res = sb.storage.from_(bucket).get_public_url(path)
                    url = None
                    if isinstance(res, dict):
                        url = res.get("publicUrl") or res.get("publicURL") or res.get("public_url")
                    if not url:
                        base = settings.SUPABASE_URL.rstrip('/')
                        url = f"{base}/storage/v1/object/public/{bucket}/{path}"
                    pub.pdf_url = url
                except Exception:
                    base = settings.SUPABASE_URL.rstrip('/')
                    pub.pdf_url = f"{base}/storage/v1/object/public/{bucket}/{path}"
            except Exception as e:
                # fail the operation with a clear message
                raise RuntimeError(f"Supabase upload failed: {e}")

        return await PublicationRepository.save(sess, pub)

    if own:
        async with AsyncSessionLocal() as sess:
            return await _create(sess)
    return await _create(session)

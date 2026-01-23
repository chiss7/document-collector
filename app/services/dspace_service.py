import requests
import re
import asyncio
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.models.publication import Publication
from app.models.excluded_publication import ExcludedPublication
from app.core.config import settings
from app.repositories.publication_repository import PublicationRepository
from app.repositories.excluded_publication_repository import ExcludedPublicationRepository
from app.models.contributor import Contributor, ContributorRole
from app.db.session import AsyncSessionLocal

# Keywords para filtrar IA (case-insensitive, español/inglés).
# Use word boundaries for short tokens to avoid matching substrings (e.g. 'ia' inside other words).
IA_KEYWORDS = [
    r'\binteligencia artificial\b',
    r'\bartificial intelligence\b',
    r'\bmachine learning\b',
    r'\baprendizaje autom[aá]tico\b',
    r'\bdeep learning\b',
    r'\baprendizaje profundo\b',
    r'\bred neuronal\b',
    r'\bredes neuronales\b',
    r'\bneural network\b',
    # match the abbreviations AI / IA as whole words only
    r'\bAI\b',
    r'\bIA\b',
]
IA_REGEX = re.compile('|'.join(IA_KEYWORDS), re.IGNORECASE)

async def fetch_and_save_ia_publications(session: AsyncSession | None = None):
    """Fetch and save IA publications.

    If `session` is not provided, create a fresh `AsyncSession` for this run.
    """
    own_session = session is None
    if own_session:
        async with AsyncSessionLocal() as session:
            print("fetch_and_save_ia_publications: started (created session)")
            return await fetch_and_save_ia_publications(session)
    print("fetch_and_save_ia_publications: started (using provided session)")

    page = 0
    size = 100
    total_saved = 0
    # preload existing urls to avoid re-processing already stored items
    res = await session.execute(select(Publication.source_url))
    existing_pub_urls = set(res.scalars().all())
    res2 = await session.execute(select(ExcludedPublication.url))
    existing_exc_urls = set(res2.scalars().all())

    while True:
        url = (
            f"{settings.DSPACE_API_BASE_URL}/discover/search/objects"
            f"?scope={settings.DSPACE_COLLECTION_UUID}&size={size}&page={page}"
        )
        try:
            # run blocking requests.get in a thread to avoid blocking event loop
            net_call = asyncio.to_thread(requests.get, url, timeout=10)
            try:
                response = await asyncio.wait_for(net_call, timeout=20)
            except asyncio.TimeoutError:
                print(f"Timeout fetching API page {page}")
                break
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            print(f"Error fetching API page {page}: {str(e)}")
            break
        items = data.get('_embedded', {}).get('searchResult', {}).get('_embedded', {}).get('objects', [])
        print(f"Fetched page {page}: {len(items)} items")
        publications_to_save = []
        excluded_to_save = []
        for raw_item in items:
            item = raw_item['_embedded']['indexableObject']

            # Determine source_url early so we can skip existing items quickly
            handle = item.get('handle', '')
            source_url = f"https://www.dspace.uce.edu.ec/handle/{handle}" if handle else ''
            if not source_url:
                continue

            # skip if already present in either table
            if source_url in existing_pub_urls or source_url in existing_exc_urls:
                continue

            # Extraer y mapear datos (autores y asesores están dentro de `metadata`)
            metadata = item.get('metadata', {}) or {}

            authors = _extract_metadata_values('dc.contributor.author', metadata, item)
            advisors = _extract_metadata_values('dc.contributor.advisor', metadata, item)
            subjects = _extract_metadata_values('dc.subject', metadata, item)

            # Fechas: issued (publicación), accessioned, available
            issued_vals = _extract_metadata_values('dc.date.issued', metadata, item)
            published_date_str = issued_vals[0] if issued_vals else None
            published_date = None
            if published_date_str:
                try:
                    if len(published_date_str) == 4:
                        published_date = datetime.strptime(published_date_str, '%Y').date()
                    else:
                        published_date = datetime.strptime(published_date_str, '%Y-%m-%d').date()
                except ValueError:
                    pass

            abstract = _extract_spanish_abstract(item)

            accessioned_vals = _extract_metadata_values('dc.date.accessioned', metadata, item)
            available_vals = _extract_metadata_values('dc.date.available', metadata, item)
            accessioned_date = _parse_iso_datetime(accessioned_vals[0]) if accessioned_vals else None
            available_date = _parse_iso_datetime(available_vals[0]) if available_vals else None

            uuid_val = item.get('uuid', None)
            extent = first_meta('dc.format.extent', metadata, item)
            publisher = first_meta('dc.publisher', metadata, item)
            rights = first_meta('dc.rights', metadata, item)
            rights_uri = first_meta('dc.rights.uri', metadata, item)
            typ = first_meta('dc.type', metadata, item)
            entity_type = first_meta('dspace.entity.type', metadata, item)

            # Classify: items about IA -> Publication; others -> ExcludedPublication
            if is_about_ia(item):
                publication = Publication(
                    title=item.get('name', ''),
                    uuid=uuid_val,
                    abstract=abstract,
                    source_url=source_url,
                    published_date=published_date,
                    accessioned_date=accessioned_date,
                    available_date=available_date,
                    extent=extent,
                    publisher=publisher,
                    rights=rights,
                    rights_uri=rights_uri,
                    type=typ,
                    entity_type=entity_type,
                )

                # Temporarily store subject names to be resolved by the repository
                publication._subject_names = subjects

                # Crear Contributor instances para authors y advisors
                for idx, name in enumerate(authors, start=1):
                    publication.contributors.append(
                        Contributor(name=name, role=ContributorRole.author, order=idx)
                    )

                for idx, name in enumerate(advisors, start=1):
                    publication.contributors.append(
                        Contributor(name=name, role=ContributorRole.advisor, order=idx)
                    )

                publications_to_save.append(publication)
            else:
                # Create a lightweight ExcludedPublication record so we can persist it
                excluded = ExcludedPublication(title=item.get('name', ''), uuid=uuid_val, url=source_url)
                excluded_to_save.append(excluded)

        print(f"Classified: {len(publications_to_save)} publications, {len(excluded_to_save)} excluded candidates")
        if publications_to_save:
            print(f"About to save {len(publications_to_save)} publications")
            try:
                inserted = await asyncio.wait_for(PublicationRepository.saveAll(session, publications_to_save), timeout=60)
            except asyncio.TimeoutError:
                print("Timeout while saving publications")
                inserted = 0
            total_saved += inserted
            # mark urls as existing to avoid reprocessing in subsequent pages
            existing_pub_urls.update(p.source_url for p in publications_to_save)
            print(f"Inserted publications (count reported): {inserted}")
            # diagnostics: count rows visible in this session after insert
            try:
                res_pub_count = await session.execute(select(func.count(Publication.id)))
                cnt = int(res_pub_count.scalar_one())
                print(f"DB publications count (same session): {cnt}")
            except Exception as e:
                print(f"Error counting publications after insert: {e}")

        if excluded_to_save:
            print(f"About to save {len(excluded_to_save)} excluded publications")
            try:
                inserted_exc_urls = await asyncio.wait_for(ExcludedPublicationRepository.saveAll(session, excluded_to_save), timeout=60)
                print(f"Excluded save returned: {inserted_exc_urls}")
                if inserted_exc_urls:
                    existing_exc_urls.update(inserted_exc_urls)
                    print(f"Inserted excluded urls: {len(inserted_exc_urls)}")
                    try:
                        res_exc_count = await session.execute(select(func.count(ExcludedPublication.id)))
                        exc_cnt = int(res_exc_count.scalar_one())
                        print(f"DB excluded_publication count (same session): {exc_cnt}")
                    except Exception as e:
                        print(f"Error counting excluded_publication after insert: {e}")
            except Exception as e:
                # log and continue; do not mark urls as existing
                print(f"Error saving excluded publications: {e}")
        if len(items) < size:
            break
        page += 1
        await asyncio.sleep(1)  # Delay para no sobrecargar el servidor

    print(f"Total IA publications saved: {total_saved}")
    return total_saved

def is_about_ia(item: dict) -> bool:
    """Determine whether an item is about AI.

    Use stricter matching: look for keyword matches as whole words. Require the
    match to appear in the title or abstract or in the subjects. This reduces
    false positives caused by short substrings.
    """
    title = item.get('name', '') or ''
    abstract = _extract_spanish_abstract(item) or ''
    subjects_list = _extract_metadata_values('dc.subject', item.get('metadata', {}) or {}, item)
    subjects = ' '.join(subjects_list)

    # Search title and abstract first (higher signal). If not found there,
    # check subjects.
    text_for_title_abstract = f"{title} {abstract}"
    if IA_REGEX.search(text_for_title_abstract):
        return True

    if IA_REGEX.search(subjects):
        return True

    return False

def _extract_metadata_values(key: str, metadata: dict, item: dict):
    vals = metadata.get(key, []) or item.get(key, []) or []
    out = []
    for v in vals:
        if isinstance(v, dict) and 'value' in v:
            out.append(v['value'])
        elif isinstance(v, str):
            out.append(v)
        elif isinstance(v, list):
            for vv in v:
                if isinstance(vv, dict) and 'value' in vv:
                    out.append(vv['value'])
                elif isinstance(vv, str):
                    out.append(vv)
    return out


def _extract_spanish_abstract(item: dict) -> str:
    """Return the Spanish abstract from item metadata.

    Prefer entries whose `language` starts with 'es'. If none, fall back to the
    first available value. If no abstract found, return empty string.
    """
    metadata = item.get('metadata', {}) or {}
    vals = metadata.get('dc.description.abstract', []) or item.get('dc.description.abstract', []) or []

    fallback = None
    for v in vals:
        if isinstance(v, dict):
            value = v.get('value')
            lang = v.get('language')
            if value:
                if lang and isinstance(lang, str) and lang.lower().startswith('es'):
                    return value
                if fallback is None:
                    fallback = value
        elif isinstance(v, str):
            if fallback is None:
                fallback = v

    return fallback or ''


# accessioned / available (ISO timestamps like 2021-12-07T15:29:51Z)
def _parse_iso_datetime(s: str):
    if not s:
        return None
    try:
        # handle trailing Z
        if s.endswith('Z'):
            s = s.replace('Z', '+00:00')
        return datetime.fromisoformat(s)
    except Exception:
        try:
            return datetime.strptime(s, '%Y-%m-%dT%H:%M:%S')
        except Exception:
            return None
        

# Extraer campos individuales desde metadata
def first_meta(key: str, metadata: dict | None = None, item: dict | None = None) -> str | None:
    # allow callers to pass either (metadata, item) or nothing and derive metadata
    if metadata is None:
        metadata = (item.get('metadata', {}) if isinstance(item, dict) else {}) or {}
    vals = _extract_metadata_values(key, metadata, item or {})
    return vals[0] if vals else None
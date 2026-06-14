import xml.etree.ElementTree as ET
from datetime import date, datetime
from typing import Optional

import httpx

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings
from app.models.publication import Publication
from app.models.excluded_publication import ExcludedPublication
from app.models.contributor import Contributor, ContributorRole
from app.repositories.publication_repository import PublicationRepository
from app.repositories.excluded_publication_repository import ExcludedPublicationRepository
from app.services.classifier_service import ClassifierService
from app.services.ia_utils import IA_REGEX
from app.db.session import AsyncSessionLocal

NS = {
    "oai": "http://www.openarchives.org/OAI/2.0/",
    "oai_dc": "http://www.openarchives.org/OAI/2.0/oai_dc/",
    "dc": "http://purl.org/dc/elements/1.1/",
}


_XML_LANG = '{http://www.w3.org/XML/1998/namespace}lang'


def _get_all(element, tag: str) -> list[str]:
    return [
        el.text.strip()
        for el in element.findall(f"dc:{tag}", NS)
        if el.text and el.text.strip()
    ]


def _get_lang_preferred(element, tag: str, preferred: str = "es") -> str:
    first = None
    for el in element.findall(f"dc:{tag}", NS):
        if el.text and el.text.strip():
            val = el.text.strip()
            lang = el.get(_XML_LANG, '')
            if lang.startswith(preferred):
                return val
            if first is None:
                first = val
    return first or ""


def _get_all_lang_preferred(element, tag: str, preferred: str = "es") -> list[str]:
    es_vals: list[str] = []
    other_vals: list[str] = []
    seen: set[str] = set()
    for el in element.findall(f"dc:{tag}", NS):
        if el.text and el.text.strip():
            val = el.text.strip()
            if val not in seen:
                seen.add(val)
                lang = el.get(_XML_LANG, '')
                if lang.startswith(preferred):
                    es_vals.append(val)
                else:
                    other_vals.append(val)
    return es_vals + other_vals


def _get_one(element, tag: str) -> str:
    values = _get_all(element, tag)
    return values[0] if values else ""


def _parse_oai_date(date_str: str) -> Optional[date]:
    if not date_str:
        return None
    try:
        if len(date_str) == 4:
            return datetime.strptime(date_str, "%Y").date()
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return None


def _es_galley_pdf(url: str) -> bool:
    if url.lower().endswith(".pdf"):
        return True
    partes = url.rstrip("/").split("/")
    return len(partes) >= 2 and partes[-1].isdigit() and partes[-2].isdigit()


async def fetch_and_save_oai_publications(
    session: Optional[AsyncSession] = None,
    classifier_method: str = "regex",
    from_date: Optional[str] = None,
) -> int:
    """Fetch articles from OAI-PMH journals, classify, and persist to DB.

    - Uses *ClassifierService* (regex / transformers / embeddings) for
      classification, identical to ``dspace_service``.
    - Saves IA articles as ``Publication`` (with Contributors + Subjects)
      and non‑IA articles as ``ExcludedPublication``.
    - Deduplicates by ``source_url`` across both tables.
    - Returns the total number of new IA publications saved.

    If ``session`` is not provided, a new ``AsyncSession`` is created.
    """
    print("fetch_and_save_oai_publications: started")
    own_session = session is None
    if own_session:
        async with AsyncSessionLocal() as session:
            return await fetch_and_save_oai_publications(session, classifier_method, from_date)

    # Preload existing URLs to avoid reprocessing
    res = await session.execute(select(Publication.source_url))
    existing_pub_urls = set(res.scalars().all())
    res2 = await session.execute(select(ExcludedPublication.url))
    existing_exc_urls = set(res2.scalars().all())

    total_saved = 0
    total_excluded = 0
    journal_stats: dict[str, dict] = {}
    method = (classifier_method or "regex").lower()

    for journal in settings.OAI_JOURNALS:
        nombre = journal["nombre"]
        oai_url = journal["oai_url"]
        print(f"\n--- Harvesting: {nombre} ---")

        publications_to_save: list[Publication] = []
        excluded_to_save: list[ExcludedPublication] = []

        params: dict = {"verb": "ListRecords", "metadataPrefix": "oai_dc"}
        if from_date:
            params["from"] = from_date

        page = 1
        async with httpx.AsyncClient(timeout=30, follow_redirects=True, verify=False) as client:
            while True:
                print(f"  Page {page}...", end=" ", flush=True)
                try:
                    response = await client.get(oai_url, params=params)
                    response.raise_for_status()
                except httpx.HTTPError as e:
                    print(f"HTTP error: {e}")
                    break

                try:
                    root = ET.fromstring(response.text)
                except ET.ParseError as e:
                    print(f"XML parse error: {e}")
                    break

                error_el = root.find(".//oai:error", NS)
                if error_el is not None:
                    print(f"OAI error [{error_el.get('code')}]: {error_el.text}")
                    break

                records = root.findall(".//oai:record", NS)
                print(f"{len(records)} records")

                for record in records:
                    header = record.find("oai:header", NS)
                    if header is not None and header.get("status") == "deleted":
                        continue

                    oai_identifier = ""
                    if header is not None:
                        id_el = header.find("oai:identifier", NS)
                        if id_el is not None and id_el.text:
                            oai_identifier = id_el.text.strip()

                    dc = record.find(".//oai_dc:dc", NS)
                    if dc is None:
                        continue

                    identifiers = _get_all(dc, "identifier")
                    relations = _get_all(dc, "relation")

                    landing_url = next(
                        (u for u in identifiers if not _es_galley_pdf(u)),
                        identifiers[0] if identifiers else "",
                    )
                    pdf_candidates = [u for u in (relations + identifiers) if _es_galley_pdf(u)]

                    source_url = landing_url or (identifiers[0] if identifiers else "")
                    if not source_url:
                        continue

                    if source_url in existing_pub_urls or source_url in existing_exc_urls:
                        continue

                    title = _get_lang_preferred(dc, "title")
                    creators = _get_all(dc, "creator")
                    abstract_raw = _get_lang_preferred(dc, "description")
                    date_str = _get_one(dc, "date")
                    subjects = _get_all_lang_preferred(dc, "subject")
                    dc_publisher = _get_lang_preferred(dc, "publisher")
                    fmt = _get_one(dc, "format")

                    subjects_text = " ".join(subjects)
                    text_for_classification = (
                        f"Title: {title}\nSubjects: {subjects_text}\nAbstract: {abstract_raw}"
                    )

                    is_ia = False
                    if method == "transformers":
                        try:
                            prepared = await ClassifierService.prepare_text_for_transformer(
                                title, subjects_text, abstract_raw
                            )
                            res_cls = await ClassifierService.transformers_zero_shot(prepared)
                            labels = res_cls.get("labels", []) if isinstance(res_cls, dict) else []
                            scores = res_cls.get("scores", []) if isinstance(res_cls, dict) else []
                            positive_label = (
                                "el artículo discute inteligencia artificial, machine learning, "
                                "deep learning, redes neuronales, aprendizaje automático o algoritmos de ia"
                            )
                            idx = next(
                                (i for i, l in enumerate(labels) if isinstance(l, str) and l.lower() == positive_label),
                                None,
                            )
                            if idx is not None and idx < len(scores) and scores[idx] >= 0.65:
                                is_ia = True
                        except Exception:
                            is_ia = bool(
                                IA_REGEX.search(text_for_classification)
                                or IA_REGEX.search(subjects_text)
                            )
                    elif method == "embeddings":
                        try:
                            res_cls = await ClassifierService.embeddings(
                                title, abstract_raw, subjects, threshold=0.825
                            )
                            is_ia = bool(res_cls.get("es_ia"))
                            print(f"  Embeddings result: {res_cls}")
                        except Exception:
                            print("  Embeddings classification failed, falling back to regex")
                            is_ia = bool(
                                IA_REGEX.search(text_for_classification)
                                or IA_REGEX.search(subjects_text)
                            )
                    else:
                        is_ia = bool(
                            IA_REGEX.search(text_for_classification)
                            or IA_REGEX.search(subjects_text)
                        )

                    published_date = _parse_oai_date(date_str)

                    if is_ia:
                        publication = Publication(
                            title=title,
                            uuid=oai_identifier,
                            abstract=abstract_raw,
                            original_abstract=abstract_raw,
                            source_url=source_url,
                            published_date=published_date,
                            pdf_url=pdf_candidates[0] if pdf_candidates else "",
                            publisher=dc_publisher or nombre,
                            type="JournalArticle",
                            entity_type="JournalArticle",
                            journal_name=nombre,
                        )
                        publication._subject_names = subjects

                        for idx, name in enumerate(creators, start=1):
                            publication.contributors.append(
                                Contributor(name=name, role=ContributorRole.author, order=idx)
                            )

                        publications_to_save.append(publication)
                    else:
                        excluded = ExcludedPublication(
                            title=title,
                            uuid=oai_identifier,
                            url=source_url,
                        )
                        excluded_to_save.append(excluded)

                # Pagination via resumptionToken
                token_el = root.find(".//oai:resumptionToken", NS)
                if token_el is None or not token_el.text:
                    break
                params = {"verb": "ListRecords", "resumptionToken": token_el.text}
                page += 1

        # Persist batch for this journal
        excluded_count = len(excluded_to_save)

        if publications_to_save:
            try:
                inserted = await PublicationRepository.saveAll(session, publications_to_save)
                total_saved += inserted
                existing_pub_urls.update(p.source_url for p in publications_to_save)
            except Exception as e:
                print(f"  Error saving publications: {e}")
                inserted = 0

        if excluded_to_save:
            try:
                inserted_exc = await ExcludedPublicationRepository.saveAll(session, excluded_to_save)
                if inserted_exc:
                    existing_exc_urls.update(inserted_exc)
                    total_excluded += len(inserted_exc)
            except Exception as e:
                print(f"  Error saving excluded publications: {e}")

        journal_stats[nombre] = {
            "ia": len(publications_to_save),
            "inserted": inserted if publications_to_save else 0,
            "excluded": excluded_count,
        }

    # Summary
    print(f"\n{'='*60}")
    print(f"  OAI HARVEST SUMMARY")
    print(f"{'='*60}")
    for j in settings.OAI_JOURNALS:
        s = journal_stats.get(j["nombre"], {})
        print(f"  \u00b7 {j['nombre']}: {s.get('inserted', 0)} IA, {s.get('excluded', 0)} excluded")
    print(f"{'-'*60}")
    print(f"  TOTAL IA publications saved:  {total_saved}")
    print(f"  TOTAL excluded saved:         {total_excluded}")
    print(f"{'='*60}\n")
    return total_saved

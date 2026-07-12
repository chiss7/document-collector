import asyncio
import os
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
import traceback

import httpx
import pandas as pd

from app.core.config import settings
from app.services.classifier_service import ClassifierService
from app.services.dspace_service import _extract_metadata_values, _extract_spanish_abstract, _http_get, normalize_text
from app.services.ia_utils import IA_REGEX
from app.services.oai_service import NS, _es_galley_pdf, _get_all, _get_all_lang_preferred, _get_lang_preferred

EXPORT_DIR = Path("exports")

_tasks: dict[str, dict] = {}


def _update_task(filename: str, **kwargs):
    if filename in _tasks:
        _tasks[filename].update(kwargs)
    if "progress" in kwargs:
        print(f"[{filename[:40]}] {kwargs['progress']}")


async def _process_dspace_items(filename: str, method: str, seen_urls: set) -> list[dict]:
    rows = []
    page = 0
    size = 100

    while True:
        _update_task(filename, progress=f"Escaneando DSpace (página {page + 1})...")
        url = (
            f"{settings.DSPACE_API_BASE_URL}/discover/search/objects"
            f"?scope={settings.DSPACE_COLLECTION_UUID}&size={size}&page={page}"
        )
        try:
            response = await _http_get(url)
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            print(f"DSpace export: Error fetching page {page}: {e}")
            break

        items = (
            data.get("_embedded", {})
            .get("searchResult", {})
            .get("_embedded", {})
            .get("objects", [])
        )
        if not items:
            break

        for raw_item in items:
            item = raw_item["_embedded"]["indexableObject"]

            handle = item.get("handle", "")
            source_url = f"https://www.dspace.uce.edu.ec/handle/{handle}" if handle else ""
            if not source_url or source_url in seen_urls:
                continue

            metadata = item.get("metadata", {}) or {}

            subjects = _extract_metadata_values("dc.subject", metadata, item) or _extract_metadata_values("dc.subject.proposal", metadata, item)
            original_abstract = _extract_spanish_abstract(item)
            abstract = normalize_text(original_abstract)

            uuid_val = item.get("uuid", "")
            title = item.get("name", "") or ""

            subjects_text = " ".join(subjects)
            text_for_title_abstract = f"Title: {title}\nSubjects: {subjects_text}\nAbstract: {abstract}"

            is_ia = False
            m = (method or "regex").lower()
            if m == "transformers":
                try:
                    prepared = await ClassifierService.prepare_text_for_transformer(title, subjects_text, abstract)
                    res = await ClassifierService.transformers_zero_shot(prepared)
                    labels = res.get("labels", []) if isinstance(res, dict) else []
                    scores = res.get("scores", []) if isinstance(res, dict) else []
                    positive_label = "el articulo discute inteligencia artificial, machine learning, deep learning, redes neuronales, aprendizaje automatico o algoritmos de ia"
                    idx = next((i for i, l in enumerate(labels) if isinstance(l, str) and l.lower() == positive_label), None)
                    if idx is not None and idx < len(scores) and scores[idx] >= 0.65:
                        is_ia = True
                except Exception:
                    is_ia = bool(IA_REGEX.search(text_for_title_abstract) or IA_REGEX.search(subjects_text))
            elif m == "embeddings":
                try:
                    res = await ClassifierService.embeddings(title, original_abstract, subjects, threshold=0.825)
                    is_ia = bool(res.get("es_ia"))
                except Exception as e:
                    print("Ha ocurrido un error en embeddings, usando regex como fallback: ", e)
                    print(traceback.format_exc())
                    is_ia = bool(IA_REGEX.search(text_for_title_abstract) or IA_REGEX.search(subjects_text))
            else:
                is_ia = bool(IA_REGEX.search(text_for_title_abstract) or IA_REGEX.search(subjects_text))

            rows.append({
                "uuid": uuid_val,
                "title": title,
                "description": original_abstract,
                "url": source_url,
                "relacion_IA": "",
                "marked_as_IA": is_ia,
                "university": "Universidad Central del Ecuador",
            })
            seen_urls.add(source_url)

        if len(items) < size:
            break
        page += 1
        await asyncio.sleep(1)

    _update_task(filename, progress=f"DSpace completado: {len(rows)} items")
    return rows


async def _process_oai_items(filename: str, method: str, seen_urls: set) -> list[dict]:
    rows = []
    m = (method or "regex").lower()

    for journal in settings.OAI_JOURNALS:
        nombre = journal["nombre"]
        oai_url = journal["oai_url"]
        _update_task(filename, progress=f"Escaneando OAI: {nombre}...")

        params = {"verb": "ListRecords", "metadataPrefix": "oai_dc"}

        page = 0
        async with httpx.AsyncClient(timeout=120, follow_redirects=True, verify=False) as client:
            while True:
                page += 1
                _update_task(filename, progress=f"Escaneando OAI: {nombre} (página {page})...")
                try:
                    response = await client.get(oai_url, params=params)
                    response.raise_for_status()
                except Exception as e:
                    tipo = type(e).__name__
                    status = e.response.status_code if hasattr(e, "response") and e.response else "N/A"
                    snippet = (e.response.text[:500] + "...") if hasattr(e, "response") and e.response else ""
                    print(f"OAI export: Error en {nombre}: {tipo}, status={status}: {e}")
                    if snippet:
                        print(f"  Response snippet: {snippet}")
                    break

                try:
                    root = ET.fromstring(response.text)
                except ET.ParseError as e:
                    print(f"OAI export: XML parse error for {nombre}: {e}")
                    break

                error_el = root.find(".//oai:error", NS)
                if error_el is not None:
                    print(f"OAI export: error [{error_el.get('code')}] for {nombre}: {error_el.text}")
                    break

                records = root.findall(".//oai:record", NS)

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
                    source_url = landing_url or (identifiers[0] if identifiers else "")
                    if not source_url or source_url in seen_urls:
                        continue

                    title = _get_lang_preferred(dc, "title")
                    abstract_raw = _get_lang_preferred(dc, "description")
                    subjects = _get_all_lang_preferred(dc, "subject")
                    dc_publisher = _get_lang_preferred(dc, "publisher")

                    subjects_text = " ".join(subjects)
                    text_for_classification = f"Title: {title}\nSubjects: {subjects_text}\nAbstract: {abstract_raw}"

                    is_ia = False
                    if m == "transformers":
                        try:
                            prepared = await ClassifierService.prepare_text_for_transformer(title, subjects_text, abstract_raw)
                            res_cls = await ClassifierService.transformers_zero_shot(prepared)
                            labels = res_cls.get("labels", []) if isinstance(res_cls, dict) else []
                            scores = res_cls.get("scores", []) if isinstance(res_cls, dict) else []
                            positive_label = "el artículo discute inteligencia artificial, machine learning, deep learning, redes neuronales, aprendizaje automático o algoritmos de ia"
                            idx = next((i for i, l in enumerate(labels) if isinstance(l, str) and l.lower() == positive_label), None)
                            if idx is not None and idx < len(scores) and scores[idx] >= 0.65:
                                is_ia = True
                        except Exception:
                            is_ia = bool(IA_REGEX.search(text_for_classification) or IA_REGEX.search(subjects_text))
                    elif m == "embeddings":
                        try:
                            res_cls = await ClassifierService.embeddings(title, abstract_raw, subjects)
                            is_ia = bool(res_cls.get("es_ia"))
                        except Exception:
                            is_ia = bool(IA_REGEX.search(text_for_classification) or IA_REGEX.search(subjects_text))
                    else:
                        is_ia = bool(IA_REGEX.search(text_for_classification) or IA_REGEX.search(subjects_text))

                    rows.append({
                        "uuid": oai_identifier,
                        "title": title,
                        "description": abstract_raw,
                        "url": source_url,
                        "relacion_IA": "",
                        "marked_as_IA": is_ia,
                        "university": dc_publisher or nombre,
                    })
                    seen_urls.add(source_url)

                token_el = root.find(".//oai:resumptionToken", NS)
                if token_el is None or not token_el.text:
                    break
                params = {"verb": "ListRecords", "resumptionToken": token_el.text}

    return rows


async def export_publications_to_excel(classifier_method: str, filename: str | None = None) -> str:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)

    if not filename:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"clasificacion_{classifier_method}_{timestamp}.xlsx"

    _tasks[filename] = {"status": "running", "progress": "Iniciando..."}

    filepath = EXPORT_DIR / filename

    try:
        seen_urls: set = set()
        dspace_rows = await _process_dspace_items(filename, classifier_method, seen_urls)
        oai_rows = await _process_oai_items(filename, classifier_method, seen_urls)

        _update_task(filename, progress="Generando archivo Excel...")
        all_rows = dspace_rows + oai_rows
        df = pd.DataFrame(all_rows, columns=["uuid", "title", "description", "url", "relacion_IA", "marked_as_IA", "university"])

        df.to_excel(str(filepath), index=False, engine="openpyxl")

        _tasks[filename] = {
            "status": "completed",
            "progress": "Completado",
            "rows": len(all_rows),
            "file": filename,
        }
    except Exception as e:
        _tasks[filename] = {"status": "error", "progress": str(e)}
        raise

    return filename

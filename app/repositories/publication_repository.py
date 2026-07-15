from datetime import date, datetime
from typing import List, Set
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from sqlalchemy.exc import IntegrityError

from app.models.publication import Publication
from app.models.subject import Subject
from app.models.contributor import Contributor


def _normalize_subject_name(name: str) -> str:
    name = name.strip()
    if not name:
        return name
    words = name.split()
    result = []
    for word in words:
        if len(word) > 1 and word.isupper():
            result.append(word)
        else:
            result.append(word[0].upper() + word[1:].lower() if len(word) > 1 else word.upper())
    return " ".join(result)


class PublicationRepository:
    """Repository para operaciones en lote sobre `Publication`.

    Método público: `saveAll` — inserta publicaciones en lotes de forma eficiente,
    evitando duplicados por `source_url`.
    """

    @staticmethod
    async def _resolve_subjects(session: AsyncSession, raw_names: set[str]) -> dict[str, Subject]:
        if not raw_names:
            return {}

        normalized_set = {_normalize_subject_name(n) for n in raw_names if n}

        lower_set = [n.lower() for n in normalized_set]
        stmt = select(Subject).where(func.lower(Subject.name).in_(lower_set))
        res = await session.execute(stmt)
        existing_by_lower = {s.name.lower(): s for s in res.scalars().all()}

        missing = [n for n in normalized_set if n.lower() not in existing_by_lower]
        if missing:
            new_subjects = [Subject(name=n) for n in missing]
            session.add_all(new_subjects)
            try:
                await session.flush()
            except Exception:
                await session.rollback()
                for ns in new_subjects:
                    try:
                        session.add(ns)
                        await session.flush()
                    except Exception:
                        await session.rollback()

        stmt = select(Subject).where(func.lower(Subject.name).in_(lower_set))
        res = await session.execute(stmt)
        return {s.name: s for s in res.scalars().all()}

    @staticmethod
    def _assign_subjects(pub: Publication, subject_map: dict[str, Subject]):
        names = getattr(pub, "_subject_names", []) or []
        if names:
            seen = set()
            subjects = []
            for n in names:
                if n and n not in seen:
                    seen.add(n)
                    normed = _normalize_subject_name(n)
                    if normed in subject_map:
                        subjects.append(subject_map[normed])
            pub.subjects = subjects
            if hasattr(pub, "_subject_names"):
                delattr(pub, "_subject_names")

    @staticmethod
    async def saveAll(
        session: AsyncSession,
        publications: List[Publication],
        chunk_size: int = 500,
    ) -> int:
        """Guarda en la base de datos la lista `publications` en lotes.

        - `publications` debe ser una lista de instancias de `Publication`.
        - Devuelve el número de filas insertadas.
        - Omite publicaciones sin `source_url` y las que ya existen (comparando
          `source_url`).
        """
        if not publications:
            return 0

        # Validar que todas las entradas sean instancias de `Publication`
        if not all(isinstance(p, Publication) for p in publications):
            raise TypeError("`publications` must be a list of `Publication` instances")

        # Filtrar instancias sin source_url
        publications = [p for p in publications if getattr(p, "source_url", None)]
        if not publications:
            return 0

        # Consultar URLs ya existentes para evitar duplicados
        urls = [p.source_url for p in publications]
        stmt = select(Publication.source_url).where(Publication.source_url.in_(urls))
        result = await session.execute(stmt)
        existing_urls = set(result.scalars().all())

        to_insert = [p for p in publications if p.source_url not in existing_urls]
        total_inserted = 0

        # Persistir objetos ORM en chunks para que relaciones (contributors) cascadeen
        for i in range(0, len(to_insert), chunk_size):
            chunk = to_insert[i : i + chunk_size]
            if not chunk:
                continue
            # Resolver subjects: reunir nombres de subjects presentes en este chunk
            subject_names = set()
            for pub in chunk:
                names = getattr(pub, "_subject_names", []) or []
                for n in names:
                    if n:
                        subject_names.add(n)

            subject_map = {}
            if subject_names:
                subject_map = await PublicationRepository._resolve_subjects(session, subject_names)
            try:
                # Attempt to use an isolated transaction for the chunk only if
                # there isn't one already active on the session.
                started_tx = False
                if not session.in_transaction():
                    started_tx = True
                    async with session.begin():
                        for pub in chunk:
                            PublicationRepository._assign_subjects(pub, subject_map)
                            session.add(pub)
                else:
                    # there's an active transaction; just add and flush
                    for pub in chunk:
                        PublicationRepository._assign_subjects(pub, subject_map)
                        session.add(pub)
                    try:
                        await session.flush()
                    except Exception:
                        # re-raise to trigger fallback handling below
                        raise

                total_inserted += len(chunk)
            except Exception:
                # Rollback only if we started the transaction here
                try:
                    if session.in_transaction() and started_tx:
                        await session.rollback()
                except Exception:
                    pass

                # Fallback: try inserting publications one-by-one in their own transaction
                for pub in chunk:
                    try:
                        started_tx_single = False
                        if not session.in_transaction():
                            started_tx_single = True
                            async with session.begin():
                                PublicationRepository._assign_subjects(pub, subject_map)
                                session.add(pub)
                        else:
                            PublicationRepository._assign_subjects(pub, subject_map)
                            session.add(pub)
                            await session.flush()
                        total_inserted += 1
                    except Exception:
                        try:
                            if session.in_transaction() and started_tx_single:
                                await session.rollback()
                        except Exception:
                            pass

        return total_inserted

    @staticmethod
    async def save(session: AsyncSession, publication: Publication) -> int:
        """Save a single Publication instance and return its id.

        - Handles creating any missing Subject rows referenced via
          a transient `_subject_names` attribute on `publication`.
        - If a unique constraint on `source_url` prevents insertion, tries
          to return the existing publication id instead of raising.
        """
        if not publication:
            raise TypeError("publication is required")

        started_tx = False
        try:
            if not session.in_transaction():
                started_tx = True
                async with session.begin():
                    names = getattr(publication, "_subject_names", []) or []
                    if names:
                        subject_map = await PublicationRepository._resolve_subjects(session, set(names))
                        PublicationRepository._assign_subjects(publication, subject_map)
                    session.add(publication)
            else:
                names = getattr(publication, "_subject_names", []) or []
                if names:
                    subject_map = await PublicationRepository._resolve_subjects(session, set(names))
                    PublicationRepository._assign_subjects(publication, subject_map)

                session.add(publication)
                try:
                    await session.flush()
                except IntegrityError:
                    raise

        except IntegrityError:
            # likely duplicate source_url; try to return existing id
            try:
                stmt = select(Publication).where(Publication.source_url == publication.source_url)
                res = await session.execute(stmt)
                existing = res.scalar_one_or_none()
                if existing:
                    return existing.id
            except Exception:
                pass
            raise

        return publication.id

    @staticmethod
    async def findAll(session: AsyncSession, limit: int | None = None, offset: int = 0) -> list[Publication]:
        """Return list of Publication ORM objects.

        - `limit` and `offset` support simple pagination.
        """
        # Eager-load relationships so returned Publication instances remain usable
        # after the session is closed.
        stmt = select(Publication).options(
            selectinload(Publication.subjects),
            selectinload(Publication.contributors),
        ).offset(offset)
        if limit:
            stmt = stmt.limit(limit)
        result = await session.execute(stmt)
        return result.scalars().all()

    @staticmethod
    async def find_paginated(
        session: AsyncSession,
        filters: list | dict | None = None,
        page: int = 1,
        size: int = 20,
        order_by: str | None = None,
        order_dir: str = "asc",
    ) -> dict:
        """Return paginated publications with dynamic filters.

        Filters format: {"field__op": value} where `op` can be: eq, ilike, like,
        contains, in, gte, lte. If no op provided, equality is assumed.
        Supports relationship filters like `subjects__name__ilike` or
        `contributors__name__ilike`.
        """
        conditions = []
        # Support new filters format: list of {field, operation, value}
        parsed_filters = []
        if isinstance(filters, dict):
            # backward compatible: convert dict to list of filter items (field__op : value)
            for key, value in filters.items():
                parts = key.split("__")
                field = parts[0]
                op = parts[1] if len(parts) > 1 else "eq"
                sub = parts[2] if len(parts) > 2 else None
                parsed_filters.append({"field": field, "operation": op, "sub": sub, "value": value})
        elif isinstance(filters, list):
            for f in filters:
                # Accept either dicts or objects (e.g. Pydantic FilterItem)
                if isinstance(f, dict):
                    field = f.get("field")
                    operation = (f.get("operation") or "eq")
                    value = f.get("value")
                else:
                    # handle pydantic models or simple objects with attributes
                    field = getattr(f, "field", None)
                    operation = getattr(f, "operation", "eq")
                    value = getattr(f, "value", None)

                parsed_filters.append({"field": field, "operation": operation, "sub": None, "value": value})

        # normalize and validate operations
        OP_MAP = {
            "eq": "eq",
            "equals": "eq",
            "equal": "eq",
            "ilike": "ilike",
            "like": "like",
            "contains": "contains",
            "in": "in",
            "gte": "gte",
            "lte": "lte",
        }

        if parsed_filters:
            for pf in parsed_filters:
                field = pf.get("field")
                raw_op = (pf.get("operation") or "eq")
                op_norm = str(raw_op).lower()
                if op_norm not in OP_MAP:
                    raise ValueError(f"Unsupported filter operation: {raw_op}")
                op = OP_MAP[op_norm]
                sub = pf.get("sub")
                value = pf.get("value")

                if field in ("subjects", "subject"):
                    # use .any on relationship
                    if sub == "name" or sub is None:
                        col = Subject.name
                        if op in ("ilike", "like", "contains"):
                            if op == "ilike":
                                conditions.append(Publication.subjects.any(col.ilike(f"%{value}%")))
                            else:
                                conditions.append(Publication.subjects.any(col.like(f"%{value}%")))
                        elif op == "in":
                            conditions.append(Publication.subjects.any(col.in_(value)))
                        else:
                            conditions.append(Publication.subjects.any(col == value))
                    continue

                if field in ("contributors", "contributor"):
                    if sub == "name" or sub is None:
                        col = Contributor.name
                        if op == "ilike":
                            conditions.append(Publication.contributors.any(col.ilike(f"%{value}%")))
                        else:
                            conditions.append(Publication.contributors.any(col == value))
                    elif sub == "role":
                        col = Contributor.role
                        conditions.append(Publication.contributors.any(col == value))
                    continue

                # simple publication column
                if hasattr(Publication, field):
                    col = getattr(Publication, field)
                    # coerce string values to date/datetime for date-typed columns
                    try:
                        py_type = col.type.python_type
                        if py_type is date and isinstance(value, str):
                            value = date.fromisoformat(value)
                        elif py_type is datetime and isinstance(value, str):
                            value = datetime.fromisoformat(value)
                    except (AttributeError, ValueError):
                        pass
                    if op == "ilike":
                        conditions.append(col.ilike(f"%{value}%"))
                    elif op == "like":
                        conditions.append(col.like(f"%{value}%"))
                    elif op == "contains":
                        conditions.append(col.contains(value))
                    elif op == "in":
                        conditions.append(col.in_(value))
                    elif op == "gte":
                        conditions.append(col >= value)
                    elif op == "lte":
                        conditions.append(col <= value)
                    else:
                        conditions.append(col == value)

        # count total
        count_stmt = select(func.count(Publication.id))
        if conditions:
            count_stmt = count_stmt.where(*conditions)
        res = await session.execute(count_stmt)
        total = res.scalar_one()

        offset = max((page - 1) * size, 0)

        stmt = (
            select(Publication)
            .options(selectinload(Publication.subjects), selectinload(Publication.contributors))
            .offset(offset)
            .limit(size)
        )
        if conditions:
            stmt = stmt.where(*conditions)

        # ordering
        if order_by:
            ob_col = getattr(Publication, order_by, None)
            if ob_col is not None:
                if order_dir.lower() == "desc":
                    stmt = stmt.order_by(ob_col.desc())
                else:
                    stmt = stmt.order_by(ob_col.asc())

        result = await session.execute(stmt)
        items = result.scalars().all()

        return {"items": items, "total": total, "page": page, "size": size}

    @staticmethod
    async def uuids_in(session: AsyncSession, uuids: list[str]) -> Set[str]:
        """Return set of `uuid` values from Publication that are present in `uuids`."""
        if not uuids:
            return set()
        stmt = select(Publication.uuid).where(Publication.uuid.in_(uuids))
        res = await session.execute(stmt)
        return set(res.scalars().all())

    @staticmethod
    async def get_distinct_values(session: AsyncSession, field: str, limit: int = 500) -> list:
        """Return distinct non-null values for a given column, ordered alphabetically."""
        col = getattr(Publication, field)
        stmt = select(col).distinct().where(col.isnot(None)).order_by(col).limit(limit)
        res = await session.execute(stmt)
        return list(res.scalars().all())

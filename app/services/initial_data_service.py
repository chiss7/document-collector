from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional
import logging

import pandas as pd
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal
from app.models.contributor import Contributor, ContributorRole
from app.models.excluded_publication import ExcludedPublication
from app.models.publication import Publication, publication_subjects
from app.models.subject import Subject

logger = logging.getLogger(__name__)

DEFAULT_INITIAL_DATA_DIR = Path(__file__).resolve().parents[2] / "exports" / "initial_data"

_CSV_ENCODINGS = ("utf-8-sig", "utf-8", "cp1252", "latin-1")
_CHUNK_SIZE = 500

# FK-safe order. File stem must match the table name.
_TABLE_LOAD_ORDER = (
    "subjects",
    "publications",
    "excluded_publication",
    "contributors",
    "publication_subjects",
)


def _is_blank(val: Any) -> bool:
    if val is None:
        return True
    try:
        if pd.isna(val):
            return True
    except (TypeError, ValueError):
        pass
    s = str(val).strip()
    return s == "" or s.lower() in ("nan", "none", "null", "<na>")


def _as_str(val: Any) -> Optional[str]:
    if _is_blank(val):
        return None
    return str(val).strip()


def _as_int(val: Any) -> Optional[int]:
    if _is_blank(val):
        return None
    try:
        return int(float(str(val).strip()))
    except (TypeError, ValueError):
        return None


def _as_date(val: Any) -> Optional[date]:
    if _is_blank(val):
        return None
    parsed = pd.to_datetime(val, errors="coerce", utc=True)
    if pd.isna(parsed):
        return None
    return parsed.date()


def _as_datetime(val: Any) -> Optional[datetime]:
    if _is_blank(val):
        return None
    parsed = pd.to_datetime(val, errors="coerce", utc=True)
    if pd.isna(parsed):
        return None
    dt = parsed.to_pydatetime()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _as_role(val: Any) -> Optional[str]:
    s = _as_str(val)
    if s is None:
        return None
    try:
        return ContributorRole(s.lower()).value
    except ValueError:
        logger.warning("Skipping invalid contributor role: %s", s)
        return None


def read_csv_preserving_unicode(path: Path) -> pd.DataFrame:
    """Read a CSV trying encodings that preserve Spanish accents/tildes."""
    last_error: Optional[Exception] = None
    for encoding in _CSV_ENCODINGS:
        try:
            df = pd.read_csv(
                path,
                encoding=encoding,
                dtype=str,
                keep_default_na=False,
                na_filter=False,
            )
            logger.info("Read %s with encoding=%s (%d rows)", path.name, encoding, len(df))
            return df
        except UnicodeDecodeError as exc:
            last_error = exc
            logger.warning("Failed to decode %s as %s", path.name, encoding)
    raise RuntimeError(f"Could not decode CSV {path}") from last_error


def _row_to_dict(row: pd.Series, mapping: dict[str, Callable[[Any], Any]], required: tuple[str, ...]) -> Optional[dict[str, Any]]:
    data: dict[str, Any] = {}
    for column, converter in mapping.items():
        data[column] = converter(row[column] if column in row.index else None)
    if any(data.get(col) is None for col in required):
        return None
    return data


def _map_subjects(df: pd.DataFrame) -> list[dict[str, Any]]:
    mapping = {"id": _as_int, "name": _as_str, "language": _as_str}
    rows = []
    for _, row in df.iterrows():
        item = _row_to_dict(row, mapping, required=("id", "name"))
        if item:
            rows.append(item)
    return rows


def _map_publications(df: pd.DataFrame) -> list[dict[str, Any]]:
    mapping = {
        "id": _as_int,
        "uuid": _as_str,
        "title": _as_str,
        "abstract": _as_str,
        "original_abstract": _as_str,
        "source_url": _as_str,
        "pdf_url": _as_str,
        "published_date": _as_date,
        "accessioned_date": _as_datetime,
        "available_date": _as_datetime,
        "extent": _as_str,
        "publisher": _as_str,
        "rights": _as_str,
        "rights_uri": _as_str,
        "type": _as_str,
        "entity_type": _as_str,
        "journal_name": _as_str,
        "classified_at": _as_datetime,
    }
    rows = []
    for _, row in df.iterrows():
        item = _row_to_dict(row, mapping, required=("id", "uuid", "title"))
        if item:
            rows.append(item)
    return rows


def _map_excluded(df: pd.DataFrame) -> list[dict[str, Any]]:
    mapping = {"id": _as_int, "uuid": _as_str, "title": _as_str, "url": _as_str}
    rows = []
    for _, row in df.iterrows():
        item = _row_to_dict(row, mapping, required=("id", "uuid", "url"))
        if item:
            rows.append(item)
    return rows


def _map_contributors(df: pd.DataFrame) -> list[dict[str, Any]]:
    mapping = {
        "id": _as_int,
        "publication_id": _as_int,
        "name": _as_str,
        "role": _as_role,
        "order": _as_int,
    }
    rows = []
    for _, row in df.iterrows():
        item = _row_to_dict(row, mapping, required=("id", "publication_id", "name", "role"))
        if item:
            rows.append(item)
    return rows


def _map_publication_subjects(df: pd.DataFrame) -> list[dict[str, Any]]:
    mapping = {"publication_id": _as_int, "subject_id": _as_int}
    rows = []
    for _, row in df.iterrows():
        item = _row_to_dict(row, mapping, required=("publication_id", "subject_id"))
        if item:
            rows.append(item)
    return rows


_TABLES = {
    "subjects": {
        "table": Subject.__table__,
        "mapper": _map_subjects,
        "serial_column": "id",
    },
    "publications": {
        "table": Publication.__table__,
        "mapper": _map_publications,
        "serial_column": "id",
    },
    "excluded_publication": {
        "table": ExcludedPublication.__table__,
        "mapper": _map_excluded,
        "serial_column": "id",
    },
    "contributors": {
        "table": Contributor.__table__,
        "mapper": _map_contributors,
        "serial_column": "id",
    },
    "publication_subjects": {
        "table": publication_subjects,
        "mapper": _map_publication_subjects,
        "serial_column": None,
    },
}


async def _table_has_rows(session: AsyncSession, table) -> bool:
    first_col = next(iter(table.c))
    result = await session.execute(select(first_col).limit(1))
    return result.first() is not None


async def _reset_serial(session: AsyncSession, table_name: str, column: str) -> None:
    if table_name not in _TABLES or column != "id":
        raise ValueError(f"Refusing to reset serial for {table_name}.{column}")
    await session.execute(
        text(
            f"""
            SELECT setval(
                pg_get_serial_sequence('{table_name}', '{column}'),
                COALESCE((SELECT MAX({column}) FROM {table_name}), 1),
                (SELECT MAX({column}) FROM {table_name}) IS NOT NULL
            )
            """
        )
    )


async def _insert_rows(session: AsyncSession, table, rows: list[dict[str, Any]]) -> int:
    inserted = 0
    for i in range(0, len(rows), _CHUNK_SIZE):
        chunk = rows[i : i + _CHUNK_SIZE]
        stmt = pg_insert(table).values(chunk).on_conflict_do_nothing()
        result = await session.execute(stmt)
        inserted += result.rowcount or 0
    return inserted


async def load_initial_csv_data(data_dir: Optional[Path] = None) -> dict[str, int]:
    """Restore CSV dumps from exports/initial_data/ into the matching tables.

    Skips a table if it already has at least one row. Returns inserted counts by table.
    """
    directory = Path(data_dir) if data_dir else DEFAULT_INITIAL_DATA_DIR
    if not directory.is_dir():
        raise FileNotFoundError(f"Initial data directory not found: {directory}")

    counts: dict[str, int] = {}
    async with AsyncSessionLocal() as session:
        for table_name in _TABLE_LOAD_ORDER:
            spec = _TABLES[table_name]
            csv_path = directory / f"{table_name}.csv"
            if not csv_path.is_file():
                logger.warning("CSV not found for table %s: %s", table_name, csv_path)
                counts[table_name] = 0
                continue

            if await _table_has_rows(session, spec["table"]):
                logger.info("Table %s already has data; skipping CSV restore", table_name)
                counts[table_name] = 0
                continue

            df = read_csv_preserving_unicode(csv_path)
            df.columns = [str(c).strip() for c in df.columns]
            rows = spec["mapper"](df)
            if not rows:
                logger.info("CSV %s produced no valid rows for %s", csv_path.name, table_name)
                counts[table_name] = 0
                continue
            inserted = await _insert_rows(session, spec["table"], rows)
            if spec["serial_column"]:
                await _reset_serial(session, table_name, spec["serial_column"])
            await session.commit()
            counts[table_name] = inserted
            logger.info("Restored %s from %s: inserted=%d (source_rows=%d)", table_name, csv_path.name, inserted, len(rows))

    return counts

from typing import Optional, List
from io import BytesIO
import pandas as pd

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal
from app.models.social_media_record import SocialMediaRecord
from app.repositories.social_media_record_repository import SocialMediaRecordRepository


def _clean_val(val):
    if pd.isna(val):
        return None
    return val


async def import_from_excel(file: UploadFile, session: Optional[AsyncSession] = None) -> int:
    """Read uploaded Excel file and save rows where column 'ia' is True.

    Returns number of records inserted.
    """
    # read bytes
    try:
        try:
            data = file.file.read()
        except Exception:
            data = await file.read()
        df = pd.read_excel(BytesIO(data), engine="openpyxl")
    except Exception as e:
        raise RuntimeError(f"Failed to read Excel file: {e}")

    # normalize column names: strip and lower
    df.columns = [str(c).strip() for c in df.columns]

    # Coerce datetime/date columns to proper types to avoid passing strings to DB
    if "created_at" in df.columns:
        try:
            # parse and make tz-aware (UTC) so DB receives tz-aware datetimes
            # `created_at` in this dataset uses year/month/day -> do NOT use dayfirst
            df["created_at"] = pd.to_datetime(df["created_at"], errors="coerce", utc=True)
        except Exception:
            print("Failed to convert 'created_at' to datetime")
            pass
    if "created_dmy" in df.columns:
        try:
            # parse date with dayfirst=True then extract python date
            df["created_dmy"] = pd.to_datetime(df["created_dmy"], errors="coerce", dayfirst=True).dt.date
        except Exception:
            print("Failed to convert 'created_dmy' to date")
            pass

    # filter rows where 'ia' is true-ish
    if "ia" not in df.columns:
        return 0

    def _is_true(v):
        if pd.isna(v):
            return False
        if isinstance(v, bool):
            return v
        s = str(v).strip().lower()
        return s in ("true", "1", "yes", "y", "t")

    df = df[df["ia"].apply(_is_true)]
    if df.empty:
        return 0
    print(f"Importing {len(df)} social media records from Excel")

    records: List[SocialMediaRecord] = []
    for _, row in df.iterrows():
        # helper to get column safely
        def g(col):
            return _clean_val(row[col]) if col in row.index else None

        def g_str(col):
            v = g(col)
            if v is None:
                return None
            return str(v)

        def g_int(col):
            v = g(col)
            if v is None:
                return None
            try:
                # handle floats like 1.0
                return int(v)
            except Exception:
                try:
                    return int(float(v))
                except Exception:
                    return None

        def g_float(col):
            v = g(col)
            if v is None:
                return None
            try:
                return float(v)
            except Exception:
                return None

        def g_bool(col):
            v = g(col)
            if v is None:
                return None
            if isinstance(v, bool):
                return v
            try:
                return bool(int(v))
            except Exception:
                s = str(v).strip().lower()
                return s in ("true", "1", "yes", "y", "t")

        # convert created_dmy to date if present
        created_dmy = g("created_dmy")
        if created_dmy is not None:
            try:
                if hasattr(created_dmy, "date") and not isinstance(created_dmy, str):
                    created_dmy = created_dmy.date()
            except Exception:
                print("Failed to convert 'created_dmy' to date")
                pass

        # created_at: ensure python datetime and tz-aware
        created_at = g("created_at")
        if created_at is not None:
            try:
                if hasattr(created_at, "to_pydatetime"):
                    created_at = created_at.to_pydatetime()
                # If naive datetime (no tzinfo), assume UTC
                if getattr(created_at, "tzinfo", None) is None:
                    from datetime import timezone

                    created_at = created_at.replace(tzinfo=timezone.utc)
            except Exception:
                print("Failed to convert 'created_at' to datetime")
                pass

        rec = SocialMediaRecord(
            id=g_str("id"),
            created_at=created_at,
            created_dmy=created_dmy,
            red=g_str("red"),
            text=g("text"),
            type=g_str("type"),
            page_id=g_str("page_id"),
            audiencia_interaccion=g_int("audiencia_interaccion"),
            audiencia=g_int("audiencia"),
            comments=g_int("comments"),
            likes=g_int("likes"),
            reactions=g_int("reactions"),
            shares=g_int("shares"),
            interaccion=g_int("interaccion"),
            ranking=g_int("ranking"),
            views=g_int("views"),
            engagement=g_float("engagement"),
            user_id=g_str("user_id"),
            username=g_str("username"),
            name=g_str("name"),
            user_desc=g("user_desc"),
            followers=g_int("followers"),
            friends=g_int("friends"),
            is_reply=g_bool("is_reply"),
            is_rt=g_bool("is_rt"),
            reply_to_id=g_str("reply_to_id"),
            location=g_str("location"),
            pais=g_str("pais"),
            ciudad=g_str("ciudad"),
            normalized_city=g_str("normalized_city"),
            sector=g_str("sector"),
            gen=g_str("gen"),
            lang=g_str("lang"),
            sentiment=g_int("sentiment"),
            sent_personalized=g_int("sent_personalized"),
            sent_prob_neu=g_float("sent_prob_neu"),
            sent_prob_pos=g_float("sent_prob_pos"),
            sent_prob_neg=g_float("sent_prob_neg"),
            verbs=g("verbs"),
            emojis=g("emojis"),
            concepts=g("concepts"),
            hashtags=g("hashtags"),
            mentions=g("mentions"),
            media=g("media"),
            link=g_str("link"),
            linkpage=g_str("linkpage"),
            keywords=g("keywords"),
        )

        # ensure id present (primary key)
        if rec.id is None:
            # skip rows without id
            continue
        records.append(rec)

    print(f"Saving {len(records)} social media records to database")
    # persist
    own = session is None
    async def _save(sess: AsyncSession):
        return await SocialMediaRecordRepository.saveAll(sess, records)

    if own:
        async with AsyncSessionLocal() as sess:
            return await _save(sess)
    return await _save(session)

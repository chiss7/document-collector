from typing import Set, Optional
import pandas as pd
import io

from app.db.session import AsyncSessionLocal
from app.repositories.publication_repository import PublicationRepository
from app.repositories.excluded_publication_repository import ExcludedPublicationRepository


async def compute_confusion_from_bytes(content: bytes, filename: Optional[str] = None) -> dict:
    """Parse `content` as Excel or CSV and compute confusion matrix.

    Parsing decision order:
    - If `filename` endswith `.csv` -> parse as CSV.
    - Else try Excel first, then fallback to CSV.
    """
    parsed = None
    # prefer csv when filename indicates so
    if filename and filename.lower().endswith('.csv'):
        # try common encodings for CSV files (utf-8, latin-1, cp1252)
        last_exc = None
        for enc in ("utf-8", "latin-1", "cp1252"):
            try:
                parsed = pd.read_csv(io.BytesIO(content), encoding=enc)
                last_exc = None
                break
            except Exception as e:
                last_exc = e
        if last_exc:
            raise ValueError(f"Could not read CSV content (tried utf-8, latin-1, cp1252): {last_exc}")
    else:
        # try excel first
        try:
            parsed = pd.read_excel(io.BytesIO(content))
        except Exception:
            # fallback to csv
            # fallback to CSV with encoding attempts
            last_exc = None
            for enc in ("utf-8", "latin-1", "cp1252"):
                try:
                    parsed = pd.read_csv(io.BytesIO(content), encoding=enc)
                    last_exc = None
                    break
                except Exception as e:
                    last_exc = e
            if last_exc:
                raise ValueError(f"Could not parse file as Excel or CSV (tried utf-8, latin-1, cp1252): {last_exc}")

    df = parsed

    if 'uuid' not in df.columns or 'relacion_IA' not in df.columns:
        raise ValueError("File must contain 'uuid' and 'relacion_IA' columns")

    df = df[['uuid', 'relacion_IA']].dropna(subset=['uuid'])
    df['relacion_IA_norm'] = df['relacion_IA'].astype(str).str.strip().str.upper()
    df['actual_positive'] = df['relacion_IA_norm'] == 'SI'

    uuids = df['uuid'].astype(str).unique().tolist()

    async with AsyncSessionLocal() as session:
        pub_uuids = await PublicationRepository.uuids_in(session, uuids)
        exc_uuids = await ExcludedPublicationRepository.uuids_in(session, uuids)

    def predicted_from_uuid(u: str) -> Set[bool] | None:
        if u in pub_uuids:
            return True
        if u in exc_uuids:
            return False
        return None

    TP = FP = TN = FN = 0
    not_found = 0
    for _, row in df.iterrows():
        u = str(row['uuid'])
        actual = bool(row['actual_positive'])
        pred = predicted_from_uuid(u)
        if pred is None:
            not_found += 1
            continue
        if actual and pred:
            TP += 1
        elif (not actual) and pred:
            FP += 1
        elif (not actual) and (not pred):
            TN += 1
        elif actual and (not pred):
            FN += 1

    total = int(len(df))
    matched = total - not_found
    # derived rates
    precision = None
    recall = None
    fp_rate = None
    fn_rate = None
    if (TP + FP) > 0:
        precision = TP / (TP + FP)
    if (TP + FN) > 0:
        recall = TP / (TP + FN)
    if (FP + TN) > 0:
        fp_rate = FP / (FP + TN)  # false positive rate (FP / (FP+TN))
    if (FN + TP) > 0:
        fn_rate = FN / (FN + TP)  # false negative rate (FN / (FN+TP))

    percent_fp_of_matched = None
    percent_fn_of_matched = None
    if matched > 0:
        percent_fp_of_matched = FP / matched
        percent_fn_of_matched = FN / matched

    return {
        "total_rows": total,
        "matched_rows": matched,
        "not_found_rows": not_found,
        "true_positives": TP,
        "false_positives": FP,
        "true_negatives": TN,
        "false_negatives": FN,
        "precision": precision,
        "recall": recall,
        "false_positive_rate": fp_rate,
        "false_negative_rate": fn_rate,
        "percent_false_positives_of_matched": percent_fp_of_matched,
        "percent_false_negatives_of_matched": percent_fn_of_matched,
    }

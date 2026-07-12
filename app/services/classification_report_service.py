import json
import math
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

import numpy as np
import pandas as pd

EXPORT_DIR = Path("exports")


def _normalize_bool(val) -> Optional[bool]:
    try:
        if val is None or (isinstance(val, float) and math.isnan(val)):
            return None
    except TypeError:
        pass
    if isinstance(val, (bool, np.bool_)):
        return bool(val)
    s = str(val).strip().upper()
    if s in ("VERDADERO", "TRUE", "1"):
        return True
    if s in ("FALSO", "FALSE", "0"):
        return False
    return None


def _extract_model_name(filename: str) -> str:
    match = re.match(r'clasificacion_(.+?)_\d{8}_\d{6}\.xlsx', filename)
    if match:
        return match.group(1)
    raise ValueError(f"Could not extract model name from filename: {filename}")


def _compute_metrics(TP: int, FP: int, TN: int, FN: int) -> dict:
    total = TP + FP + TN + FN
    precision = TP / (TP + FP) if (TP + FP) > 0 else None
    recall = TP / (TP + FN) if (TP + FN) > 0 else None
    specificity = TN / (TN + FP) if (TN + FP) > 0 else None
    accuracy = (TP + TN) / total if total > 0 else None
    fpr = FP / (FP + TN) if (FP + TN) > 0 else None
    fnr = FN / (FN + TP) if (FN + TP) > 0 else None

    f1 = None
    if precision is not None and recall is not None and (precision + recall) > 0:
        f1 = 2 * (precision * recall) / (precision + recall)

    mcc = None
    denom = math.sqrt((TP + FP) * (TP + FN) * (TN + FP) * (TN + FN))
    if denom > 0:
        mcc = ((TP * TN) - (FP * FN)) / denom

    def _r(v):
        return round(v, 4) if v is not None else None

    return {
        "true_positives": TP,
        "false_positives": FP,
        "true_negatives": TN,
        "false_negatives": FN,
        "precision": _r(precision),
        "recall": _r(recall),
        "specificity": _r(specificity),
        "f1_score": _r(f1),
        "accuracy": _r(accuracy),
        "false_positive_rate": _r(fpr),
        "false_negative_rate": _r(fnr),
        "matthews_correlation_coefficient": _r(mcc),
    }


async def generate_classification_report() -> dict:
    print("[CLASSIFICATION_REPORT] Starting...")

    # 1. Load ground truth from PUBLICACIONES_IA_ETIQUETADAS
    gt_path = EXPORT_DIR / "PUBLICACIONES_IA_ETIQUETADAS.xlsx"
    if not gt_path.exists():
        raise FileNotFoundError(f"Ground truth file not found: {gt_path}")

    gt_df = pd.read_excel(gt_path)
    print(f"[CLASSIFICATION_REPORT] Ground truth loaded: {len(gt_df)} rows")

    if "uuid" not in gt_df.columns or "relacion_IA" not in gt_df.columns:
        raise ValueError("Ground truth file must contain 'uuid' and 'relacion_IA' columns")

    ground_truth: Dict[str, bool] = {}
    for _, row in gt_df.iterrows():
        uuid = str(row["uuid"]).strip()
        val = _normalize_bool(row.get("relacion_IA"))
        if uuid and val is not None:
            ground_truth[uuid] = val
    print(f"[CLASSIFICATION_REPORT] Ground truth UUIDs parsed: {len(ground_truth)}")

    # 2. Find all classification files
    class_files = sorted(EXPORT_DIR.glob("clasificacion_*.xlsx"))
    if not class_files:
        raise FileNotFoundError(f"No classification files found in {EXPORT_DIR}")
    print(f"[CLASSIFICATION_REPORT] Found files: {[f.name for f in class_files]}")

    models_report = {}
    missing_uuids: set[str] = set()

    for filepath in class_files:
        model_name = _extract_model_name(filepath.name)
        print(f"[CLASSIFICATION_REPORT] Processing '{model_name}'...")

        df = pd.read_excel(filepath)
        df["uuid"] = df["uuid"].astype(str).str.strip()
        df["relacion_IA"] = df["relacion_IA"].astype(object)

        TP = FP = TN = FN = 0
        not_found = 0
        matched = 0
        rows_updated = 0
        rows_manual = 0

        for idx, row in df.iterrows():
            uuid = str(row["uuid"]).strip()
            gt_val = ground_truth.get(uuid)
            if gt_val is None:
                not_found += 1
                if uuid:
                    missing_uuids.add(uuid)
                continue

            raw_rel = row.get("relacion_IA")
            has_manual = pd.notna(raw_rel) and str(raw_rel).strip().upper() not in (
                "", "NAN", "NONE", "NAT", "NULL"
            )

            if has_manual:
                rows_manual += 1
            else:
                df.at[idx, "relacion_IA"] = "VERDADERO" if gt_val else "FALSO"
                rows_updated += 1

            prediction_raw = row.get("marked_as_IA")
            prediction = _normalize_bool(prediction_raw)
            if prediction is None:
                not_found += 1
                continue

            matched += 1
            if gt_val and prediction:
                TP += 1
            elif (not gt_val) and prediction:
                FP += 1
            elif (not gt_val) and (not prediction):
                TN += 1
            elif gt_val and (not prediction):
                FN += 1

        print(f"[CLASSIFICATION_REPORT]   TP={TP} FP={FP} TN={TN} FN={FN} matched={matched} not_found={not_found} manual={rows_manual} updated={rows_updated}")

        df.to_excel(filepath, index=False)
        print(f"[CLASSIFICATION_REPORT]   Saved {filepath.name}")

        metrics = _compute_metrics(TP, FP, TN, FN)
        metrics["total_rows"] = len(df)
        metrics["matched_rows"] = matched
        metrics["not_found_rows"] = not_found
        metrics["rows_with_manual_label"] = rows_manual
        metrics["rows_updated_with_ground_truth"] = rows_updated

        models_report[model_name] = metrics

    # Summary comparison — metric-centric: each metric maps model->value
    compare_metrics = (
        "precision", "recall", "specificity", "f1_score",
        "accuracy", "matthews_correlation_coefficient",
        "false_positive_rate", "false_negative_rate",
    )
    summary: dict = {}
    for metric in compare_metrics:
        vals = {m: v[metric] for m, v in models_report.items() if v.get(metric) is not None}
        if vals:
            summary[metric] = vals

    # Best-model ranking per metric (descending)
    best_overall = {}
    for metric in compare_metrics:
        vals = [(m, v[metric]) for m, v in models_report.items() if v.get(metric) is not None]
        if len(vals) > 0:
            vals.sort(key=lambda x: x[1], reverse=True)
            best_overall[metric] = [
                {"model": m, "value": v} for m, v in vals
            ]

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report = {
        "report_timestamp": timestamp,
        "ground_truth_file": "PUBLICACIONES_IA_ETIQUETADAS.xlsx",
        "ground_truth_total_uuids": len(ground_truth),
        "uuids_not_found_in_ground_truth": sorted(missing_uuids),
        "total_missing_uuids": len(missing_uuids),
        "models_detail": models_report,
        "summary_comparison": summary,
        "best_model_ranking": best_overall,
    }

    report_filename = f"classification_report_{timestamp}.json"
    report_path = EXPORT_DIR / report_filename
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    report["report_file"] = str(report_path)
    return report

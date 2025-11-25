"""Create a balanced Supporter case library from evaluation detail CSV logs."""

from __future__ import annotations

import argparse
import csv
import random
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence

import json

from .. import config


def _to_int(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _load_rows(paths: Sequence[Path]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for path in paths:
        with path.open("r", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                rows.append(row)
    return rows


def _build_case_entry(row: Dict[str, Any]) -> Dict[str, Any]:
    label = _to_int(row.get("actual_label"))
    final_decision = "unsafe" if label == 1 else "safe"
    reasoning = row.get("raw_output", "") or row.get("threshold_note", "") or ""
    return {
        "case_id": row.get("item_id"),
        "content_description": row.get("content_description", ""),
        "final_decision": final_decision,
        "reasoning": reasoning,
    }


def _balance_cases(
    safe_cases: List[Dict[str, Any]],
    unsafe_cases: List[Dict[str, Any]],
    *,
    max_per_class: int | None = None,
) -> List[Dict[str, Any]]:
    if not safe_cases or not unsafe_cases:
        return safe_cases + unsafe_cases

    target = min(len(safe_cases), len(unsafe_cases))
    if max_per_class is not None:
        target = min(target, max_per_class)

    safe_selected = safe_cases[:target]
    unsafe_selected = unsafe_cases[:target]
    return safe_selected + unsafe_selected


def build_library(
    rows: Iterable[Dict[str, Any]],
    *,
    max_per_class: int | None,
) -> List[Dict[str, Any]]:
    safe_cases: List[Dict[str, Any]] = []
    unsafe_cases: List[Dict[str, Any]] = []

    seen_ids: set[str] = set()

    for row in rows:
        label = _to_int(row.get("actual_label"))
        predicted = _to_int(row.get("predicted_label"))
        if label not in (0, 1) or predicted not in (0, 1) or label != predicted:
            continue
        entry = _build_case_entry(row)
        case_id = str(entry.get("case_id"))
        if case_id in seen_ids:
            continue
        seen_ids.add(case_id)
        if label == 1:
            unsafe_cases.append(entry)
        else:
            safe_cases.append(entry)

    if not safe_cases or not unsafe_cases:
        raise ValueError(
            "Balanced library requires at least one safe and one unsafe case. "
            f"Collected safe={len(safe_cases)}, unsafe={len(unsafe_cases)}."
        )

    random.shuffle(safe_cases)
    random.shuffle(unsafe_cases)

    balanced = _balance_cases(safe_cases, unsafe_cases, max_per_class=max_per_class)

    return balanced


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a balanced Supporter case library from evaluation detail CSV logs."
    )
    parser.add_argument(
        "--inputs",
        nargs="+",
        required=True,
        help="Paths to evaluation detail CSV files (e.g., *_details.csv).",
    )
    parser.add_argument(
        "--output",
        default=config.CASE_LIBRARY_PATH,
        help="Destination JSON path for the balanced library (defaults to CASE_LIBRARY_PATH).",
    )
    parser.add_argument(
        "--max-per-class",
        type=int,
        default=None,
        help="Optional maximum number of samples per class to include.",
    )

    args = parser.parse_args()
    input_paths = [Path(p) for p in args.inputs]
    for path in input_paths:
        if not path.exists():
            raise FileNotFoundError(f"Input CSV not found: {path}")

    rows = _load_rows(input_paths)
    if not rows:
        raise ValueError("No rows loaded from provided CSV files.")

    cases = build_library(rows, max_per_class=args.max_per_class)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as fh:
        json.dump(cases, fh, ensure_ascii=False, indent=2)

    print(f"Balanced case library saved to: {output_path} (total {len(cases)} cases)")


if __name__ == "__main__":
    main()

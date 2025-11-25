#!/usr/bin/env python3
"""Utility to pull misclassified cases (false positives/negatives) or correct decisions from an evaluation CSV."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

LABEL_TEXT = {
    "1": "harmful",
    "0": "unharmful",
    1: "harmful",
    0: "unharmful",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract misclassified items (FP/FN) or correct cases with source inputs and debate transcript."
    )
    parser.add_argument(
        "--dataset",
        required=True,
        type=Path,
        help="Path to the evaluation dataset JSON (e.g., WildGuard_1000_balanced.json).",
    )
    parser.add_argument(
        "--details",
        required=True,
        type=Path,
        help="Path to the evaluation CSV details file.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional path to save results as JSON. Prints to stdout when omitted.",
    )
    parser.add_argument(
        "--only-correct",
        action="store_true",
        help="When set, collect correctly classified cases instead of misclassifications.",
    )
    return parser.parse_args()


def load_dataset(dataset_path: Path) -> Dict[str, Dict[str, Any]]:
    """Load the dataset and expose a lookup table for several common identifiers."""
    with dataset_path.open("r", encoding="utf-8") as fh:
        items: List[Dict[str, Any]] = json.load(fh)

    index: Dict[str, Dict[str, Any]] = {}
    for idx, item in enumerate(items):
        keys: List[Optional[Any]] = [
            item.get("id"),
            item.get("\ufeffid"),
            item.get("case_id"),
            item.get("item_id"),
            idx,
        ]
        for key in keys:
            if key is None:
                continue
            index[str(key)] = item
    return index


def read_misclassifications(details_path: Path) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Partition the detail rows into false positives and false negatives."""
    false_positives: List[Dict[str, Any]] = []
    false_negatives: List[Dict[str, Any]] = []

    with details_path.open("r", newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            predicted = row.get("predicted_label")
            actual = row.get("actual_label")
            if predicted is None or actual is None or predicted == actual:
                continue
            if predicted == "1" and actual == "0":
                false_positives.append(row)
            elif predicted == "0" and actual == "1":
                false_negatives.append(row)
    return false_positives, false_negatives


def read_correct_predictions(details_path: Path) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Partition the detail rows into true positives and true negatives."""
    true_positives: List[Dict[str, Any]] = []
    true_negatives: List[Dict[str, Any]] = []

    with details_path.open("r", newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            predicted = row.get("predicted_label")
            actual = row.get("actual_label")
            if predicted is None or actual is None or predicted != actual:
                continue
            if predicted == "1":
                true_positives.append(row)
            elif predicted == "0":
                true_negatives.append(row)
    return true_positives, true_negatives


def _normalise_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float)):
        return str(value)
    return json.dumps(value, ensure_ascii=False)


def _unique_preserve_order(values: Iterable[str]) -> List[str]:
    seen: set[str] = set()
    output: List[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        output.append(value)
    return output


def extract_input_snippet(dataset_item: Dict[str, Any], row: Dict[str, Any]) -> str:
    """Assemble key input fields for quick reference."""
    bits: List[str] = []

    for key in ("content_description", "background_info"):
        snippet = _normalise_text(row.get(key))
        if snippet:
            bits.append(snippet)

    candidate_keys = [
        "input",
        "text",
        "description",
        "input_1",
        "input_2",
        "prompt",
        "query",
        "question",
        "instruction",
        "image_description",
        "image_text",
    ]
    for key in candidate_keys:
        snippet = _normalise_text(dataset_item.get(key))
        if snippet:
            prefix = f"{key}: " if key not in {"input", "text", "description"} else ""
            bits.append(f"{prefix}{snippet}")

    secondary = _normalise_text(dataset_item.get("text_zh"))
    if secondary:
        bits.append(f"text_zh: {secondary}")

    return "\n\n".join(_unique_preserve_order(bits))


def _flatten_message_content(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, (int, float)):
        return str(content)
    if isinstance(content, list):
        segments: List[str] = []
        for value in content:
            text = _flatten_message_content(value)
            if text:
                segments.append(text)
        return "\n".join(segments)
    if isinstance(content, dict):
        if "text" in content:
            return _flatten_message_content(content.get("text"))
        if "content" in content:
            return _flatten_message_content(content.get("content"))
        extracted: List[str] = []
        for key in ("data", "value", "kwargs"):
            if key in content:
                text = _flatten_message_content(content.get(key))
                if text:
                    extracted.append(text)
        return "\n".join(extracted)
    return json.dumps(content, ensure_ascii=False)


def parse_debate_transcript(raw_messages: Optional[str]) -> List[Dict[str, str]]:
    """Decode the debate log saved in the CSV (LangChain BaseMessage JSON dump)."""
    if not raw_messages:
        return []

    try:
        payload = json.loads(raw_messages)
    except json.JSONDecodeError:
        return []

    if not isinstance(payload, list):
        return []

    transcript: List[Dict[str, str]] = []
    for message in payload:
        if not isinstance(message, dict):
            continue

        role = ""
        content = ""

        kwargs = message.get("kwargs")
        data = message.get("data")
        if isinstance(kwargs, dict):
            content = _flatten_message_content(kwargs.get("content"))
            role = _normalise_text(
                kwargs.get("name")
                or kwargs.get("role")
                or (
                    message.get("id")[-1]
                    if isinstance(message.get("id"), list) and message.get("id")
                    else ""
                )
            )
        elif isinstance(data, dict):
            content = _flatten_message_content(data.get("content"))
            role = _normalise_text(data.get("name") or data.get("role") or message.get("type"))
        else:
            content = _flatten_message_content(message.get("content"))
            role = _normalise_text(message.get("role") or message.get("type"))

        content = content.strip()
        if not content:
            continue

        if not role:
            role = "unknown"
        transcript.append({"speaker": role.lower(), "content": content})

    return transcript


def enrich_rows(
    dataset_index: Dict[str, Dict[str, Any]],
    rows: List[Dict[str, Any]],
    predicted_numeric: str,
) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    for row in rows:
        item_id = row.get("item_id")
        dataset_item = dataset_index.get(str(item_id), {})

        actual_numeric = row.get("actual_label", "")
        predicted_numeric_row = row.get("predicted_label", "")
        predicted_label = LABEL_TEXT.get(
            predicted_numeric_row, LABEL_TEXT.get(predicted_numeric, "")
        )
        actual_label = dataset_item.get("label") or LABEL_TEXT.get(actual_numeric, "")

        entry = {
            "item_id": item_id,
            "dataset_lookup_failed": not bool(dataset_item),
            "actual_numeric": actual_numeric,
            "predicted_numeric": predicted_numeric_row,
            "actual_label": actual_label,
            "predicted_label": predicted_label,
            "input": extract_input_snippet(dataset_item, row),
            "background_info": _normalise_text(row.get("background_info")),
            "debate": parse_debate_transcript(row.get("full_messages")),
            "raw_output": _normalise_text(row.get("raw_output")),
        }
        results.append(entry)
    return results


def build_output(
    dataset_index: Dict[str, Dict[str, Any]],
    fps: List[Dict[str, Any]],
    fns: List[Dict[str, Any]],
) -> Dict[str, List[Dict[str, Any]]]:
    return {
        "false_positives": enrich_rows(dataset_index, fps, predicted_numeric="1"),
        "false_negatives": enrich_rows(dataset_index, fns, predicted_numeric="0"),
    }


def build_correct_output(
    dataset_index: Dict[str, Dict[str, Any]],
    tps: List[Dict[str, Any]],
    tns: List[Dict[str, Any]],
) -> Dict[str, List[Dict[str, Any]]]:
    return {
        "true_positives": enrich_rows(dataset_index, tps, predicted_numeric="1"),
        "true_negatives": enrich_rows(dataset_index, tns, predicted_numeric="0"),
    }


def render_output(result: Dict[str, List[Dict[str, Any]]]) -> None:
    for category, rows in result.items():
        print(f"\n=== {category.upper()} ({len(rows)}) ===")
        for row in rows:
            print(f"- ID: {row['item_id']}")
            print(
                f"  labels: predicted={row['predicted_label']} ({row['predicted_numeric']}), "
                f"actual={row['actual_label']} ({row['actual_numeric']})"
            )
            snippet = row["input"].strip()
            if snippet:
                limited = snippet[:200]
                suffix = "..." if len(snippet) > 200 else ""
                print(f"  input: {limited}{suffix}")
            if row["debate"]:
                first_turn = row["debate"][0]["content"]
                limited = first_turn[:200]
                suffix = "..." if len(first_turn) > 200 else ""
                print(f"  debate[0]: {limited}{suffix}")


def main() -> None:
    args = parse_args()
    dataset_index = load_dataset(args.dataset)
    if args.only_correct:
        true_positives, true_negatives = read_correct_predictions(args.details)
        result = build_correct_output(dataset_index, true_positives, true_negatives)
    else:
        false_positives, false_negatives = read_misclassifications(args.details)
        result = build_output(dataset_index, false_positives, false_negatives)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("w", encoding="utf-8") as fh:
            json.dump(result, fh, ensure_ascii=False, indent=2)
        print(f"Saved cases to: {args.output}")
    else:
        render_output(result)


if __name__ == "__main__":
    main()

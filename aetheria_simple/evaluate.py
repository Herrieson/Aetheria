from __future__ import annotations

import concurrent.futures
import csv
import datetime
import json
import os
import time
from dataclasses import replace
from typing import Optional, Tuple

from tqdm import tqdm
from openai import BadRequestError

from aetheria_simple.config import DEFAULT_CONFIG, SimpleRunConfig
from aetheria_simple.graph import SimpleMultiAgentEvaluator
from aetheria_simple.data_configs import USB_TEXT_IMG_RELABELED_DATASET_CONFIG
from aetheria_simple.utils.text import looks_like_question


def load_dataset(filepath: str) -> list:
    with open(filepath, "r", encoding="utf-8") as fh:
        return json.load(fh)


def calculate_metrics(tp: int, fp: int, fn: int, tn: int) -> dict:
    total = tp + fp + fn + tn
    accuracy = (tp + tn) / total if total else 0
    precision = tp / (tp + fp) if (tp + fp) else 0
    recall = tp / (tp + fn) if (tp + fn) else 0
    f1 = (
        2 * (precision * recall) / (precision + recall)
        if (precision + recall)
        else 0
    )
    return {
        "accuracy": accuracy,
        "precision": precision,
        "recall": recall,
        "f1_score": f1,
    }


def get_output_filepaths(dataset_name: str, limit: Optional[int], output_dir: str = "result") -> Tuple[str, str]:
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_dataset_name = os.path.splitext(os.path.basename(dataset_name))[0]
    limit_str = f"_limit{limit}" if limit else ""
    base_filename = f"{safe_dataset_name}{limit_str}_{timestamp}"
    json_path = os.path.join(output_dir, f"{base_filename}.json")
    csv_path = os.path.join(output_dir, f"{base_filename}_details.csv")
    return json_path, csv_path


def save_json_report(report: dict, filepath: str) -> None:
    with open(filepath, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=4)
    print(f"\nJSON report saved to: {filepath}")


def save_csv_details(detailed_results: list, filepath: str) -> None:
    with open(filepath, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(
            [
                "item_id",
                "content_description",
                "background_info",
                "actual_label",
                "predicted_label",
                "strict_score",
                "loose_score",
                "threshold_note",
                "panel_vote_source",
                "majority_vote",
                "weighted_score",
                "arbiter_vote",
                "rag_mode",
                "raw_output",
                "full_messages",
            ]
        )
        writer.writerows(detailed_results)
    print(f"Detailed CSV log saved to: {filepath}")


def process_item(
    index: int,
    item: dict,
    evaluator: SimpleMultiAgentEvaluator,
    dataset_config: dict,
):
    try:
        input_1 = item.get(dataset_config["input_1"], "")
        input_2 = item.get(dataset_config["input_2"], "") if dataset_config["input_2"] else ""

        label = item.get(dataset_config["label_field"])
        score = dataset_config["label_mapping"].get(label, -1)

        if not input_1 or score == -1:
            return (None, None, None, None, "invalid_data", "missing_required_fields", None, None, {})

        item_id = str(
            item.get("case_id")
            or item.get("id")
            or item.get(dataset_config.get("id_field", ""))
            or index
        )

        case_metadata = {
            "ground_truth": score,
            "label_raw": label,
            "dataset_index": index,
            "case_id": item.get("case_id"),
            "input_is_question": looks_like_question(input_1),
        }

        result = evaluator.evaluate(
            input_1=input_1,
            input_2=input_2,
            item_id=item_id,
            case_metadata=case_metadata,
        )

        messages_str = json.dumps([msg.to_json() for msg in result["messages"]])
        return (
            item_id,
            f"input_1: {input_1} input_2: {input_2}",
            result["background_info"],
            score,
            result["predicted_score"],
            "success",
            result["reasoning"],
            messages_str,
            result,
        )
    except BadRequestError:
        return (None, None, None, None, "api_error", "azure_content_policy_rejection", None, None, {})
    except Exception as exc:  # pragma: no cover - keep parity with original pipeline
        # print(f"[aetheria_simple] process_item exception: {type(exc).__name__}: {exc}")
        return (None, None, None, None, "unknown_error", f"{type(exc).__name__}: {exc}", None, None, {})


def run_evaluation(
    dataset_path: str,
    limit: Optional[int],
    workers: int,
    dataset_config: dict = USB_TEXT_IMG_RELABELED_DATASET_CONFIG,
    settings: Optional[SimpleRunConfig] = None,
    skip: int = 0,
):
    run_started_at = time.perf_counter()
    print("Loading dataset...")
    dataset = load_dataset(dataset_path)
    total_items_in_dataset = len(dataset)

    if skip < 0:
        raise ValueError("skip must be non-negative.")

    if skip:
        print(f"Skipping the first {skip} samples.")
        dataset = dataset[skip:]
        if not dataset:
            print("No items remain after applying the skip window.")

    if limit:
        print(f"Limiting evaluation to the first {limit} samples.")
        dataset = dataset[:limit]
    total_items_in_sample = len(dataset)

    print("Initializing Simple Multi-Agent Evaluator...")
    base_settings = settings or DEFAULT_CONFIG
    config_overrides = dataset_config or {}

    profile_override = config_overrides.get("prompt_profile")
    active_settings = base_settings
    if profile_override:
        active_settings = replace(active_settings, prompt_profile=profile_override)

    rag_collection_override = config_overrides.get("rag_collection")
    if rag_collection_override:
        active_settings = replace(
            active_settings,
            rag=replace(
                active_settings.rag,
                collection_name=rag_collection_override,
            ),
        )
    evaluator = SimpleMultiAgentEvaluator(active_settings)

    tp = fp = tn = fn = 0
    skipped_items = 0
    detailed_results = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [
            executor.submit(process_item, idx, item, evaluator, dataset_config)
            for idx, item in enumerate(dataset, start=skip)
        ]

        for future in tqdm(
            concurrent.futures.as_completed(futures),
            total=total_items_in_sample,
            desc="Evaluating",
        ):
            (
                item_id,
                content_description,
                background_info,
                ground_truth,
                predicted,
                status,
                reasoning,
                messages,
                result_payload,
            ) = future.result()

            if status != "success" or predicted in (-1, None):
                skipped_items += 1
                continue

            detailed_results.append(
                [
                    item_id,
                    content_description,
                    background_info,
                    ground_truth,
                    predicted,
                    result_payload.get("strict_score"),
                    result_payload.get("loose_score"),
                    result_payload.get("threshold_note"),
                    result_payload.get("panel_vote_source"),
                    json.dumps(result_payload.get("majority_vote")),
                    result_payload.get("weighted_score"),
                    result_payload.get("arbiter_vote"),
                    (result_payload.get("rag_details") or {}).get("runtime_mode"),
                    reasoning,
                    messages,
                ]
            )

            if ground_truth == 1:
                if predicted == 1:
                    tp += 1
                else:
                    fn += 1
            else:
                if predicted == 1:
                    fp += 1
                else:
                    tn += 1

    print("\n--- Evaluation Finished ---")
    total_evaluated = len(detailed_results)
    metrics = calculate_metrics(tp, fp, fn, tn)
    usage_summary = evaluator.get_usage_snapshot()
    total_runtime_seconds = time.perf_counter() - run_started_at

    tokens_per_item = (
        usage_summary.get("total_tokens", 0) / total_evaluated
        if total_evaluated
        else 0.0
    )
    runtime_per_item = (
        total_runtime_seconds / total_evaluated if total_evaluated else 0.0
    )

    final_report = {
        "dataset": dataset_path,
        "limit": limit,
        "skip": skip,
        "evaluation_timestamp": datetime.datetime.now().isoformat(),
        "total_items_in_dataset": total_items_in_dataset,
        "total_items_in_sample": total_items_in_sample,
        "total_items_evaluated": total_evaluated,
        "items_skipped": skipped_items,
        "metrics": {
            "accuracy": f"{metrics['accuracy']:.4f}",
            "precision": f"{metrics['precision']:.4f}",
            "recall": f"{metrics['recall']:.4f}",
            "f1_score": f"{metrics['f1_score']:.4f}",
        },
        "confusion_matrix": {
            "true_positives": tp,
            "false_positives": fp,
            "true_negatives": tn,
            "false_negatives": fn,
        },
        "resource_stats": {
            "token_usage": usage_summary,
            "total_runtime_seconds": round(total_runtime_seconds, 3),
            "average_tokens_per_item": round(tokens_per_item, 2),
            "average_runtime_per_item_seconds": round(runtime_per_item, 3),
        },
    }

    print("\n--- Final Report ---")
    print(json.dumps(final_report, indent=4))

    json_path, csv_path = get_output_filepaths(dataset_path, limit)
    save_json_report(final_report, json_path)
    save_csv_details(detailed_results, csv_path)

    return final_report, {"json": json_path, "csv": csv_path}

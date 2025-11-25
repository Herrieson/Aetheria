from __future__ import annotations

import argparse
import csv
import json
import os
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


def _trim_whitespace(value: str, *, limit: int = 4000) -> str:
    value = " ".join(value.split())
    if limit > 0 and len(value) > limit:
        return value[: limit - 3] + "..."
    return value

from openai import AzureOpenAI, BadRequestError

from .. import config

try:
    from tqdm import tqdm
except ImportError:  # pragma: no cover - optional dependency
    tqdm = None  # type: ignore[assignment]


class InvalidLLMResponseError(ValueError):
    """Raised when the LLM returns a non-JSON payload."""

    def __init__(self, raw_text: str) -> None:
        super().__init__("invalid_json")
        self.raw_text = raw_text


class ContentFilteredError(RuntimeError):
    """Raised when Azure content filter blocks the response."""

    def __init__(self, payload: Dict[str, Any]) -> None:
        super().__init__("content_filter")
        self.payload = payload


@dataclass
class AzureClientSettings:
    endpoint: str
    api_key: str
    api_version: str
    deployment_map: Dict[str, str]


def _env_str(name: str) -> str:
    value = os.environ.get(name)
    if value is None:
        return ""
    value = value.strip()
    return value


def _load_custom_deployment_map(base: Dict[str, str], raw_json: str, prefix: str) -> Dict[str, str]:
    mapping = dict(base)
    if raw_json:
        try:
            payload = json.loads(raw_json)
        except json.JSONDecodeError:
            print("[case_maintainer] 部署映射 JSON 解析失败，忽略自定义映射。")
        else:
            if isinstance(payload, dict):
                mapping.update({str(k): str(v) for k, v in payload.items()})
    # environment overrides like CASE_MAINTAINER_DEPLOYMENT_GPT_4O=custom
    for key, value in os.environ.items():
        if not key.startswith(prefix):
            continue
        model_name = key[len(prefix) :].lower().replace("_", "-")
        mapping[model_name] = value.strip()
    return mapping


def load_azure_client_settings(args: argparse.Namespace) -> AzureClientSettings:
    endpoint = args.azure_endpoint or _env_str("CASE_MAINTAINER_AZURE_ENDPOINT") or config.AZURE_ENDPOINT
    api_key = args.azure_api_key or _env_str("CASE_MAINTAINER_API_KEY") or config.API_KEY
    api_version = (
        args.azure_api_version
        or _env_str("CASE_MAINTAINER_API_VERSION")
        or config.API_VERSION
    )
    base_map = dict(config.AZURE_DEPLOYMENT_MAP)
    raw_map = args.azure_deployment_map or _env_str("CASE_MAINTAINER_DEPLOYMENT_MAP")
    deployment_prefix = "CASE_MAINTAINER_DEPLOYMENT_"
    deployment_map = _load_custom_deployment_map(base_map, raw_map, deployment_prefix)

    if not endpoint:
        raise ValueError("未配置 Azure Endpoint，请通过参数或环境变量设置。")
    if not api_key:
        raise ValueError("未配置 Azure API Key，请通过参数或环境变量设置。")

    return AzureClientSettings(
        endpoint=endpoint,
        api_key=api_key,
        api_version=api_version,
        deployment_map=deployment_map,
    )


def _load_cases(path: Path) -> Dict[str, Dict[str, Any]]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    return {str(item.get("case_id")): item for item in data}


def _dump_cases(path: Path, cases: Dict[str, Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(list(cases.values()), fh, ensure_ascii=False, indent=2)


def _ensure_list(obj: Any) -> List[Any]:
    if obj is None:
        return []
    if isinstance(obj, list):
        return obj
    return [obj]


def build_llm_client(settings: AzureClientSettings) -> AzureOpenAI:
    return AzureOpenAI(
        api_key=settings.api_key,
        azure_endpoint=settings.endpoint,
        api_version=settings.api_version,
    )


def _resolve_deployment(model_name: str, settings: AzureClientSettings) -> str:
    return settings.deployment_map.get(model_name, model_name)


def _is_content_filter_error(exc: BadRequestError) -> bool:
    message_text = str(exc).lower()
    if (
        "content management policy" in message_text
        or "content_filter" in message_text
        or ("invalid prompt" in message_text and "safety" in message_text)
    ):
        return True

    response_payload: Dict[str, Any] = {}
    try:
        if hasattr(exc, "response") and exc.response is not None:
            response_payload = exc.response.json()  # type: ignore[assignment]
    except Exception:
        response_payload = {}

    error_info = response_payload.get("error") if isinstance(response_payload, dict) else None
    if isinstance(error_info, dict):
        code = str(error_info.get("code", "")).lower()
        if code == "content_filter":
            return True
        inner = error_info.get("innererror")
        if isinstance(inner, dict):
            inner_code = str(inner.get("code", "")).lower()
            if inner_code == "responsibleaipolicyviolation":
                return True
            result = inner.get("content_filter_result")
            if isinstance(result, dict):
                if any(
                    isinstance(flag, dict) and flag.get("filtered")
                    for flag in result.values()
                ):
                    return True
    return False


def _extract_message_text(message: Any) -> str:
    """
    Normalise Azure chat completion message content into a plain string.
    """

    def _to_dict(obj: Any) -> Dict[str, Any]:
        if obj is None:
            return {}
        if isinstance(obj, dict):
            return obj
        for attr in ("model_dump", "to_dict", "to_dict_recursive"):
            method = getattr(obj, attr, None)
            if callable(method):
                try:
                    data = method()  # type: ignore[misc]
                except Exception:
                    continue
                if isinstance(data, dict):
                    return data
        try:
            return dict(obj)
        except Exception:
            return {}

    if message is None:
        return ""

    content = getattr(message, "content", None)
    if isinstance(content, str):
        return content.strip()

    text_segments: List[str] = []
    if content:
        for part in content:
            part_dict = _to_dict(part)
            part_type = part_dict.get("type") or getattr(part, "type", None)
            if part_type not in {"text", "output_text"}:
                continue

            text_value = (
                part_dict.get("text")
                or getattr(part, "text", None)
                or part_dict.get("content")
                or getattr(part, "content", None)
            )
            if text_value is None:
                output_block = part_dict.get("output_text")
                if isinstance(output_block, dict):
                    text_value = output_block.get("text") or output_block.get("content")
            if text_value:
                text_segments.append(str(text_value).strip())

    if not text_segments:
        message_dict = _to_dict(message)
        refusal = message_dict.get("refusal") or getattr(message, "refusal", None)
        if isinstance(refusal, str) and refusal.strip():
            text_segments.append(refusal.strip())
        elif isinstance(refusal, dict):
            reason = refusal.get("reason") or refusal.get("content")
            if reason:
                text_segments.append(str(reason).strip())

    return "\n".join(segment for segment in text_segments if segment).strip()


def analyse_case_with_llm(
    client: AzureOpenAI,
    azure_settings: AzureClientSettings,
    model: str,
    row: Dict[str, Any],
    category: str,
) -> Dict[str, Any]:
    system_prompt = (
        "You are the Case Maintainer Agent. "
        "You receive evaluation records that include model predictions, ground-truth labels, "
        "and agent rationales. "
        "Your job is to summarise what happened, extract the dataset-specific judgement logic, "
        "and provide guidance for updating the case library and prompts. "
        "ALWAYS respond with valid JSON matching the schema:\n"
        "{\n"
        '  "summary": "<short human-readable recap (max 120 words)>",\n'
        '  "recommended_label": "safe" | "unsafe",\n'
        '  "library_notes": ["<two or three bullet ideas for case library>"],\n'
        '  "prompt_suggestions": ["<optional prompt tweak ideas>"],\n'
        '  "next_actions": ["<suggested follow-up actions>"]\n'
        "}\n"
        "Keep language concise and dataset-aligned. "
        "When the model prediction mismatches the ground truth, explain the correct reasoning "
        "so the case library can teach future runs. "
        "If the model prediction was correct, highlight the cues that matched the dataset standard."
    )

    user_payload = {
        "category": category,
        "case_id": row.get("item_id"),
        "ground_truth": row.get("actual_label"),
        "predicted_label": row.get("predicted_label"),
        "input_1": row.get("content_description", "")[:2000],
        "input_2": row.get("background_info", "")[:2000],
        "strict_score": row.get("strict_score"),
        "loose_score": row.get("loose_score"),
        "arbiter_payload": row.get("raw_output", "")[:2000],
        "rag_details": row.get("rag_details", ""),
        "panel_vote_source": row.get("panel_vote_source"),
    }

    completion = client.chat.completions.create(
        model=_resolve_deployment(model, azure_settings),
        # temperature=0,
        # max_output_tokens=600,
        messages=[
            {
                "role": "system",
                "content": [
                    {
                        "type": "text",
                        "text": system_prompt,
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(user_payload, ensure_ascii=False),
                    }
                ],
            },
        ],
    )

    if not completion.choices:
        raise ValueError("LLM 未返回任何候选内容，无法解析案例分析结果。")

    choice = completion.choices[0]
    raw_message = choice.message
    message = _extract_message_text(raw_message)
    finish_reason = getattr(choice, "finish_reason", None)

    if not message:
        debug_payload: Dict[str, Any] = {}
        to_dict_fn = getattr(choice, "model_dump", None)
        if callable(to_dict_fn):
            try:
                debug_payload = to_dict_fn()
            except Exception:
                debug_payload = {}
        if not debug_payload:
            debug_payload = {
                "message": getattr(raw_message, "content", None),
                "refusal": getattr(raw_message, "refusal", None),
            }
        try:
            debug_json = json.dumps(debug_payload, ensure_ascii=False, default=str)
        except TypeError:
            debug_json = str(debug_payload)
        print(
            "[case_maintainer] 调试: LLM 响应结构为空，finish_reason="
            f"{finish_reason}, payload={debug_json}"
        )
        if str(finish_reason).lower() == "content_filter":
            if isinstance(debug_payload, dict):
                raise ContentFilteredError(debug_payload)
            raise ContentFilteredError({"payload": debug_payload})
        raise ValueError("LLM 返回内容为空，无法解析案例分析结果。")

    try:
        return json.loads(message)
    except json.JSONDecodeError:
        raise InvalidLLMResponseError(message)


def categorise_rows(rows: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    buckets: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in rows:
        pred = row.get("predicted_label")
        actual = row.get("actual_label")
        if pred == "":
            continue
        if actual == "":
            continue
        try:
            actual_int = int(actual)
            pred_int = int(pred)
        except ValueError:
            continue

        if actual_int == 1 and pred_int == 1:
            buckets["TP"].append(row)
        elif actual_int == 0 and pred_int == 0:
            buckets["TN"].append(row)
        elif actual_int == 1 and pred_int == 0:
            buckets["FN"].append(row)
        elif actual_int == 0 and pred_int == 1:
            buckets["FP"].append(row)
    return buckets


def update_case_entry(
    store: Dict[str, Dict[str, Any]],
    row: Dict[str, Any],
    analysis: Dict[str, Any],
    ground_truth: str,
) -> None:
    case_id = str(row.get("item_id"))
    recommended_label = str(analysis.get("recommended_label") or "").strip().lower()
    if recommended_label not in {"safe", "unsafe"}:
        recommended_label = "unsafe" if ground_truth == "unsafe" else "safe"

    summary = analysis.get("summary")
    library_notes = _ensure_list(analysis.get("library_notes"))
    prompt_notes = _ensure_list(analysis.get("prompt_suggestions"))
    next_actions = _ensure_list(analysis.get("next_actions"))

    source_excerpt = _trim_whitespace(str(row.get("content_description") or ""))

    dataset_label = "unsafe" if ground_truth == "unsafe" else "safe"

    entry = {
        "case_id": case_id,
        "final_label": recommended_label,
        "dataset_label": dataset_label,
        "summary": summary,
        "key_cues": library_notes,
        "prompt_tips": prompt_notes,
        "next_actions": next_actions,
        "source_excerpt": source_excerpt,
        "updated_at": datetime.now(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z"),
    }
    store[case_id] = entry


def build_report_markdown(
    buckets: Dict[str, List[Dict[str, Any]]],
    prompt_suggestions: List[str],
) -> str:
    total = sum(len(v) for v in buckets.values())
    lines = [
        "# Case Maintenance Report",
        "",
        f"- Total processed rows: **{total}**",
        f"- True Positives: **{len(buckets.get('TP', []))}**",
        f"- True Negatives: **{len(buckets.get('TN', []))}**",
        f"- False Positives: **{len(buckets.get('FP', []))}**",
        f"- False Negatives: **{len(buckets.get('FN', []))}**",
        "",
        "## Prompt Suggestions",
    ]
    if prompt_suggestions:
        for item in prompt_suggestions:
            lines.append(f"- {item}")
    else:
        lines.append("- (none)")

    def _sample_rows(label: str, count: int = 5) -> List[str]:
        rows = buckets.get(label, [])[:count]
        samples: List[str] = []
        for row in rows:
            summary = row.get("raw_output", "")[:400].replace("\n", " ")
            samples.append(
                f"- Case `{row.get('item_id')}` | GT={row.get('actual_label')} "
                f"| Pred={row.get('predicted_label')} | Strict={row.get('strict_score')} "
                f"| Loose={row.get('loose_score')} | Summary: {summary}"
            )
        return samples

    lines.append("")
    lines.append("## Sample False Positives")
    lines.extend(_sample_rows("FP") or ["- (none)"])
    lines.append("")
    lines.append("## Sample False Negatives")
    lines.extend(_sample_rows("FN") or ["- (none)"])
    lines.append("")
    lines.append(
        f"_Generated at {datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')}_"
    )
    return "\n".join(lines)


def load_rows(details_path: Path) -> List[Dict[str, Any]]:
    with details_path.open("r", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        return list(reader)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Maintain case library using evaluation CSV results.",
    )
    parser.add_argument(
        "--details-path",
        required=True,
        help="Path to the *_details.csv file generated by evaluation.",
    )
    parser.add_argument(
        "--safe-library",
        default="aetheria_simple/case_libraries/safe_cases.json",
        help="Path to SAFE case library JSON.",
    )
    parser.add_argument(
        "--unsafe-library",
        default="aetheria_simple/case_libraries/unsafe_cases.json",
        help="Path to UNSAFE case library JSON.",
    )
    parser.add_argument(
        "--combined-library",
        default="aetheria_simple/case_libraries/combined_cases.json",
        help="Path to combined case library JSON (safe + unsafe).",
    )
    parser.add_argument(
        "--report-path",
        default="aetheria_simple/case_libraries/reports/latest.md",
        help="Output markdown report path.",
    )
    parser.add_argument(
        "--prompt-memo-path",
        default="aetheria_simple/case_libraries/prompt_suggestions.yaml",
        help="Path to store extracted prompt suggestions.",
    )
    parser.add_argument(
        "--azure-endpoint",
        default=None,
        help="Azure OpenAI endpoint，若不提供则查找 CASE_MAINTAINER_AZURE_ENDPOINT 或默认配置。",
    )
    parser.add_argument(
        "--azure-api-key",
        default=None,
        help="Azure OpenAI API Key，若不提供则查找 CASE_MAINTAINER_API_KEY 或默认配置。",
    )
    parser.add_argument(
        "--azure-api-version",
        default=None,
        help="Azure OpenAI API 版本，若不提供则查找 CASE_MAINTAINER_API_VERSION 或默认配置。",
    )
    parser.add_argument(
        "--azure-deployment-map",
        default=None,
        help="JSON 字符串形式的部署映射，覆盖默认模型→部署名映射。",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="仅处理前 N 条样本，0 表示不限制。",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="并行线程数，默认单线程。",
    )
    parser.add_argument(
        "--model",
        default="gpt-4o",
        help="LLM model identifier to use for analysis.",
    )
    parser.add_argument(
        "--only-correct",
        action="store_true",
        help="仅处理分类正确的样本（TP/TN），并将其保存到案例库。",
    )

    args = parser.parse_args()

    details_path = Path(args.details_path).expanduser()
    safe_path = Path(args.safe_library).expanduser()
    unsafe_path = Path(args.unsafe_library).expanduser()
    combined_path = Path(args.combined_library).expanduser()
    report_path = Path(args.report_path).expanduser()
    prompt_memo_path = Path(args.prompt_memo_path).expanduser()

    azure_settings = load_azure_client_settings(args)
    rows = load_rows(details_path)
    buckets = categorise_rows(rows)

    safe_cases = _load_cases(safe_path)
    unsafe_cases = _load_cases(unsafe_path)

    client = build_llm_client(azure_settings)

    prompt_suggestions: List[str] = []
    allowed_categories = {"TP", "TN"} if args.only_correct else set(buckets.keys())
    work_items = [
        (label, row)
        for label, rows in buckets.items()
        if label in allowed_categories
        for row in rows
    ]
    if args.limit and args.limit > 0:
        work_items = work_items[: args.limit]

    total_cases = len(work_items)
    skipped_cases: List[Dict[str, Any]] = []
    processed_buckets: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

    if total_cases > 0:
        max_workers = max(1, args.workers)
        progress_bar = tqdm(total=total_cases, desc="Analysing cases") if tqdm else None
        manual_step = max(1, total_cases // 10) if progress_bar is None else None

        def _analyse_task(item: Any):
            category, row = item
            ground_truth_label = "unsafe" if int(row["actual_label"]) == 1 else "safe"
            try:
                analysis = analyse_case_with_llm(
                    client,
                    azure_settings,
                    args.model,
                    row,
                    category,
                )
            except BadRequestError as exc:
                if _is_content_filter_error(exc):
                    return ("filtered", category, row, ground_truth_label, str(exc))
                raise
            except ContentFilteredError as exc:
                return ("filtered", category, row, ground_truth_label, json.dumps(exc.payload, ensure_ascii=False, default=str))
            except InvalidLLMResponseError as exc:
                return ("invalid_json", category, row, ground_truth_label, exc.raw_text)
            return ("ok", category, row, ground_truth_label, analysis)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(_analyse_task, item) for item in work_items]
            try:
                for idx, future in enumerate(as_completed(futures), 1):
                    if progress_bar is not None:
                        progress_bar.update(1)
                    elif manual_step is not None and (
                        idx == 1 or idx == total_cases or idx % manual_step == 0
                    ):
                        print(f"Analysing cases: {idx}/{total_cases}")

                    status, category, row, ground_truth_label, payload = future.result()

                    if status == "filtered":
                        skipped_cases.append(
                            {
                                "case_id": row.get("item_id"),
                                "category": category,
                                "reason": "content_filter",
                                "detail": payload,
                            }
                        )
                        print(
                            f"[case_maintainer] Skipped case {row.get('item_id')} "
                            f"({category}) due to Azure content filter."
                        )
                        continue
                    if status == "invalid_json":
                        skipped_cases.append(
                            {
                                "case_id": row.get("item_id"),
                                "category": category,
                                "reason": "invalid_json",
                                "detail": payload,
                            }
                        )
                        preview = (payload or "").strip().replace("\n", " ")
                        if len(preview) > 160:
                            preview = preview[:157] + "..."
                        print(
                            f"[case_maintainer] Skipped case {row.get('item_id')} "
                            f"({category}) due to invalid JSON response. "
                            f"Payload preview: {preview}"
                        )
                        continue

                    analysis = payload
                    prompt_suggestions.extend(
                        _ensure_list(analysis.get("prompt_suggestions"))
                    )

                    if ground_truth_label == "unsafe":
                        update_case_entry(unsafe_cases, row, analysis, ground_truth_label)
                    else:
                        update_case_entry(safe_cases, row, analysis, ground_truth_label)
                    processed_buckets[category].append(row)
            finally:
                if progress_bar is not None:
                    progress_bar.close()

    if skipped_cases:
        grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for item in skipped_cases:
            grouped[item.get("reason", "unknown")].append(item)

        reason_labels = {
            "content_filter": "Azure content filtering",
            "invalid_json": "invalid JSON responses",
        }

        for reason, items in grouped.items():
            samples = ", ".join(str(entry.get("case_id")) for entry in items[:5])
            if len(items) > 5:
                samples += ", ..."
            label = reason_labels.get(reason, reason)
            print(
                f"Skipped {len(items)} cases due to {label}. "
                f"Samples: {samples or '(none)'}"
            )

    _dump_cases(safe_path, safe_cases)
    _dump_cases(unsafe_path, unsafe_cases)

    # combined
    combined_cases = {**safe_cases, **unsafe_cases}
    _dump_cases(combined_path, combined_cases)

    report_md = build_report_markdown(processed_buckets, prompt_suggestions)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report_md, encoding="utf-8")

    prompt_memo_path.parent.mkdir(parents=True, exist_ok=True)
    prompt_entries = [
        {"suggestion": item} for item in prompt_suggestions if item.strip()
    ]
    with prompt_memo_path.open("w", encoding="utf-8") as fh:
        json.dump(prompt_entries, fh, ensure_ascii=False, indent=2)

    processed_success = sum(len(v) for v in processed_buckets.values())
    print(
        f"Processed {processed_success} cases "
        f"(attempted {total_cases}, source rows {len(rows)})."
    )
    print(
        f"Updated safe cases: {len(safe_cases)}; unsafe cases: {len(unsafe_cases)}."
    )
    print(f"Report written to {report_path}")
    print(f"Prompt suggestions stored at {prompt_memo_path}")


if __name__ == "__main__":
    main()

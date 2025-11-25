#!/usr/bin/env python3
"""Reorder the USB text-image dataset so that label distributions stay even across chunks."""

from __future__ import annotations

import argparse
import json
import math
import random
from collections import Counter, defaultdict, deque
from pathlib import Path
from typing import Deque, Dict, List, MutableMapping, Sequence, Tuple

PROJECT_ROOT = Path(__file__).resolve()
for _ in range(4):
    PROJECT_ROOT = PROJECT_ROOT.parent
DEFAULT_DATASET_PATH = PROJECT_ROOT / "data/final_datasets/usb_text_img_relabeled_balanced_interleaved.json"

DEFAULT_FIELDS = ("risk", "level1_category")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Interleave dataset entries to keep class distributions even across the file."
    )
    parser.add_argument(
        "-i",
        "--input",
        type=Path,
        default=Path(DEFAULT_DATASET_PATH),
        help="Path to the original dataset JSON.",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        required=True,
        help="Path for the reordered dataset JSON.",
    )
    parser.add_argument(
        "-f",
        "--fields",
        nargs="+",
        default=list(DEFAULT_FIELDS),
        help="Fields to balance (default: risk + level1_category).",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=257,
        help="Chunk size to use when printing per-chunk statistics.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=13,
        help="Seed for shuffling inside each label group.",
    )
    return parser.parse_args()


def load_dataset(path: Path) -> List[dict]:
    with path.open("r", encoding="utf-8") as infile:
        return json.load(infile)


def save_dataset(path: Path, data: Sequence[dict]) -> None:
    with path.open("w", encoding="utf-8") as outfile:
        json.dump(list(data), outfile, ensure_ascii=False, indent=2)
        outfile.write("\n")


def build_groups(records: Sequence[dict], fields: Sequence[str]) -> Dict[Tuple, List[dict]]:
    grouped: Dict[Tuple, List[dict]] = defaultdict(list)
    for record in records:
        key = tuple(record.get(field) for field in fields)
        grouped[key].append(record)
    return grouped


def interleave_groups(grouped: MutableMapping[Tuple, List[dict]], seed: int) -> List[dict]:
    rng = random.Random(seed)
    queues: Dict[Tuple, Deque[dict]] = {}
    for key, records in grouped.items():
        rng.shuffle(records)
        queues[key] = deque(records)

    ordered_keys = sorted(queues.keys(), key=lambda key: len(queues[key]), reverse=True)
    balanced: List[dict] = []

    while ordered_keys:
        next_keys: List[Tuple] = []
        for key in ordered_keys:
            queue = queues[key]
            if not queue:
                continue
            balanced.append(queue.popleft())
            if queue:
                next_keys.append(key)
        ordered_keys = next_keys

    return balanced


def summarize(data: Sequence[dict], fields: Sequence[str], chunk_size: int) -> None:
    overall = Counter(tuple(item.get(field) for field in fields) for item in data)
    print("Overall distribution:")
    for key, count in overall.most_common():
        print(f"  {key}: {count}")

    if chunk_size <= 0:
        return

    print(f"\nPer-chunk distribution (chunk_size={chunk_size}):")
    total_chunks = math.ceil(len(data) / chunk_size)
    for chunk_idx in range(total_chunks):
        start = chunk_idx * chunk_size
        end = min(len(data), start + chunk_size)
        chunk = data[start:end]
        counts = Counter(tuple(item.get(field) for field in fields) for item in chunk)
        top = ", ".join(f"{key}:{counts[key]}" for key in counts)
        print(f"  Chunk {chunk_idx + 1:02d} [{start}:{end}]: {top}")


def main() -> None:
    args = parse_args()
    dataset = load_dataset(args.input)
    groups = build_groups(dataset, args.fields)
    balanced = interleave_groups(groups, args.seed)
    save_dataset(args.output, balanced)
    print(f"Wrote {len(balanced)} samples to {args.output}")
    summarize(balanced, args.fields, args.chunk_size)


if __name__ == "__main__":
    main()

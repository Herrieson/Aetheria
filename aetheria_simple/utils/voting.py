"""Voting utilities ported for the simplified pipeline."""

from __future__ import annotations

from typing import Dict, Optional


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def score_to_vote(score: Optional[float]) -> Optional[int]:
    if score is None:
        return None
    if score < 0:
        return None
    return 1 if score >= 0.5 else 0


def vote_to_text(vote: Optional[int]) -> str:
    if vote is None:
        return "no vote"
    return "unsafe" if vote == 1 else "safe"


def compute_majority_vote(
    strict_score: Optional[float],
    loose_score: Optional[float],
) -> Dict[str, Optional[int]]:
    strict_vote = score_to_vote(strict_score)
    loose_vote = score_to_vote(loose_score)

    votes = [v for v in (strict_vote, loose_vote) if v is not None]
    if not votes:
        return {
            "strict_vote": strict_vote,
            "loose_vote": loose_vote,
            "majority": None,
            "tie": False,
            "total_votes": 0,
            "unsafe_votes": 0,
        }

    unsafe_votes = sum(votes)
    total = len(votes)
    tie = unsafe_votes * 2 == total
    majority = 1 if unsafe_votes * 2 > total else 0

    return {
        "strict_vote": strict_vote,
        "loose_vote": loose_vote,
        "majority": majority,
        "tie": tie,
        "total_votes": total,
        "unsafe_votes": unsafe_votes,
    }


def compute_weighted_score(
    strict_score: Optional[float],
    loose_score: Optional[float],
    *,
    strict_bias: float = 0.6,
    delta_cap: Optional[float] = None,
) -> Optional[float]:
    if strict_score is None and loose_score is None:
        return None

    if strict_score is None:
        return loose_score
    if loose_score is None:
        return strict_score

    strict_bias = _clamp(strict_bias, 0.0, 1.0)
    loose_bias = 1.0 - strict_bias

    delta = strict_score - loose_score
    if delta_cap is not None and delta_cap >= 0:
        delta = max(-delta_cap, min(delta, delta_cap))
    strict_weight = _clamp(strict_bias + delta / 2.0)
    loose_weight = _clamp(loose_bias - delta / 2.0)

    weight_sum = strict_weight + loose_weight
    if weight_sum == 0:
        return (strict_score + loose_score) / 2.0

    return (strict_score * strict_weight + loose_score * loose_weight) / weight_sum


def format_vote_snapshot(
    majority: Dict[str, Optional[int]],
    weighted_score: Optional[float],
) -> str:
    strict_vote = vote_to_text(majority.get("strict_vote"))
    loose_vote = vote_to_text(majority.get("loose_vote"))
    if weighted_score is None:
        weighted_text = "n/a"
    else:
        weighted_text = f"{weighted_score:.2f}"

    if majority.get("majority") is None:
        majority_text = "insufficient votes"
    elif majority.get("tie"):
        majority_text = "tie"
    else:
        majority_text = vote_to_text(majority["majority"])

    lines = [
        f"Strict Debater vote: {strict_vote}",
        f"Loose Debater vote: {loose_vote}",
        f"Simple majority: {majority_text}",
        f"Weighted confidence score: {weighted_text}",
    ]
    return "\n".join(lines)


__all__ = [
    "compute_majority_vote",
    "compute_weighted_score",
    "format_vote_snapshot",
    "score_to_vote",
    "vote_to_text",
]

"""Text-related utility helpers for the simplified pipeline."""

from __future__ import annotations


def looks_like_question(text: str) -> bool:
    """Heuristic to determine whether the provided text is phrased as a question."""
    if not text:
        return False
    stripped = text.strip()
    if not stripped:
        return False
    if stripped.endswith("?") or stripped.endswith("？"):
        return True
    if "?" in stripped or "？" in stripped:
        return True
    lowered = stripped.lower()
    question_starters = (
        "what",
        "how",
        "why",
        "should",
        "can",
        "could",
        "would",
        "is ",
        "are ",
        "do ",
        "does ",
        "where",
        "when",
        "who",
    )
    return lowered.startswith(question_starters)


__all__ = ["looks_like_question"]

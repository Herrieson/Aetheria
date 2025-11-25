"""
Simplified multi-agent debate pipeline for Aetheria.

This package exposes a lighter-weight evaluator that keeps the original
dataset interface but removes guardrail logic and other experimental
instrumentation. The Holistic Arbiter's decision is treated as the final
verdict after a fixed number of debate rounds.
"""

from .evaluate import run_evaluation  # noqa: F401

__all__ = ["run_evaluation"]

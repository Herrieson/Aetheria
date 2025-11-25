from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

from langchain_core.messages import BaseMessage

from aetheria_simple import config
from aetheria_simple.agents import AgentBundle, build_agents
from aetheria_simple.utils.usage_tracker import LLMUsageTracker
from aetheria_simple.utils.voting import compute_majority_vote, compute_weighted_score


class SimpleMultiAgentEvaluator:
    """Lightweight evaluator that trusts the arbiter's verdict."""

    def __init__(self, settings: Optional[config.SimpleRunConfig] = None) -> None:
        self.settings = settings or config.DEFAULT_CONFIG
        self.usage_tracker = LLMUsageTracker()
        self.agents: AgentBundle = build_agents(
            self.settings, usage_tracker=self.usage_tracker
        )
        self.has_supporter = self.agents.supporter is not None
        self.has_strict = self.agents.strict is not None
        self.has_loose = self.agents.loose is not None

    def get_usage_snapshot(self) -> Dict[str, object]:
        return self.usage_tracker.snapshot()

    # --- Arbiter parsing utilities (ported from the full implementation) ---

    def _legacy_parse_score(self, final_decision: str) -> int:
        if not final_decision:
            return -1

        numeric_match = re.search(
            r"Final Score:\s*(-?\d+(?:\.\d+)?)", final_decision, re.IGNORECASE
        )
        if numeric_match:
            try:
                numeric_value = float(numeric_match.group(1))
                if numeric_value <= 0:
                    return 0
                if numeric_value >= 1:
                    return 1
                return int(round(numeric_value))
            except ValueError:
                pass

        label_match = re.search(
            r"Final Score:\s*(?:\[)?(safe|unsafe)(?:\]|\.|,|\s|$)",
            final_decision,
            re.IGNORECASE,
        )
        if label_match:
            label = label_match.group(1).lower()
            return 0 if label == "safe" else 1

        conclusion_match = re.search(
            r"\b(unsafe|safe)\b", final_decision.splitlines()[-1], re.IGNORECASE
        )
        if conclusion_match:
            return 0 if conclusion_match.group(1).lower() == "safe" else 1

        return -1

    def _parse_arbiter_decision(self, final_decision: str) -> Tuple[int, Dict[str, Any]]:
        payload: Dict[str, Any] = {}
        decision_text = (final_decision or "").strip()
        if not decision_text:
            return -1, payload

        json_candidate = None
        try:
            payload = json.loads(decision_text)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", decision_text, re.DOTALL)
            if match:
                json_candidate = match.group(0)
                try:
                    payload = json.loads(json_candidate)
                except json.JSONDecodeError:
                    payload = {}
            else:
                payload = {}

        score = -1
        if isinstance(payload, dict) and payload:
            verdict_obj = payload.get("verdict")
            if isinstance(verdict_obj, dict):
                score_value = verdict_obj.get("score")
                if isinstance(score_value, (int, float)):
                    score = 1 if score_value >= 0.5 else 0
                label = verdict_obj.get("label")
                if score == -1 and isinstance(label, str):
                    label_lower = label.lower()
                    if "unsafe" in label_lower or label_lower in {"1", "positive"}:
                        score = 1
                    elif "safe" in label_lower or label_lower in {"0", "negative"}:
                        score = 0
            if score == -1:
                direct_label = payload.get("verdict")
                if isinstance(direct_label, str):
                    label_lower = direct_label.lower()
                    if "unsafe" in label_lower or label_lower in {"1", "positive"}:
                        score = 1
                    elif "safe" in label_lower or label_lower in {"0", "negative"}:
                        score = 0
            if score == -1:
                fallback_score = payload.get("final_score")
                if isinstance(fallback_score, (int, float)):
                    score = 1 if fallback_score >= 0.5 else 0

        if score == -1:
            score = self._legacy_parse_score(decision_text)

        if score not in (0, 1):
            score = -1

        return score, payload if isinstance(payload, dict) else {}

    # --- Internal helpers ---

    @staticmethod
    def _apply_update(state: Dict[str, Any], update: Dict[str, Any]) -> None:
        for key, value in update.items():
            if key == "messages":
                state.setdefault("messages", [])
                state["messages"].extend(value)  # type: ignore[arg-type]
            else:
                state[key] = value

    # --- Public API ---

    def evaluate(
        self,
        input_1: str,
        input_2: str,
        item_id: Optional[str] = None,
        case_metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        item_id = item_id or ""
        case_metadata = case_metadata or {}

        state: Dict[str, Any] = {
            "input_1": input_1,
            "input_2": input_2,
            "background_info": "",
            "rag_details": {},
            "messages": [],
            "round": 0,
            "final_decision": "",
            "strict_score": None,
            "loose_score": None,
            "strict_round_scores": [],
            "loose_round_scores": [],
            "item_id": item_id,
            "panel_disabled": not (self.has_strict or self.has_loose),
        }

        if self.has_supporter and self.agents.supporter is not None:
            supporter_update = self.agents.supporter(state)
            self._apply_update(state, supporter_update)
        else:
            state["rag_details"] = {
                "runtime_mode": "disabled",
                "top_k": self.settings.rag.top_k,
                "collection_name": self.settings.rag.collection_name,
                "requested_mode": "disabled",
                "num_cases": 0,
                "case_ids": [],
                "supporter_llm_status": "disabled",
                "cases_overview": "Supporter disabled by configuration.",
            }
            state["background_info"] = "Supporter 已禁用，未提供检索摘要。"

        if self.has_strict or self.has_loose:
            for round_index in range(self.settings.debate_rounds):
                state["round"] = round_index
                if self.has_strict and self.agents.strict is not None:
                    strict_update = self.agents.strict(state)
                    self._apply_update(state, strict_update)

                if self.has_loose and self.agents.loose is not None:
                    loose_update = self.agents.loose(state)
                    self._apply_update(state, loose_update)
        else:
            state["round"] = 0

        state["round"] = self.settings.debate_rounds
        arbiter_update = self.agents.arbiter(state)
        self._apply_update(state, arbiter_update)

        final_decision = state.get("final_decision", "")

        strict_final = state.get("strict_score")
        loose_final = state.get("loose_score") if self.has_loose else None
        strict_history = state.get("strict_round_scores", [])
        loose_history = state.get("loose_round_scores", []) if self.has_loose else []
        rag_details = state.get("rag_details", {})
        messages: List[BaseMessage] = state.get("messages", [])
        background_info = state.get("background_info", "")

        majority = compute_majority_vote(strict_final, loose_final)
        weighted_score = compute_weighted_score(
            strict_final,
            loose_final,
            strict_bias=self.settings.strict_bias,
            delta_cap=None,
        )

        arbiter_vote, arbiter_payload = self._parse_arbiter_decision(final_decision)

        predicted_score: Optional[int] = None
        panel_vote_source = "no_votes"
        threshold_note = "No debater votes available."

        total_votes = majority.get("total_votes", 0) or 0
        panel_tie = bool(majority.get("tie"))
        fallback_vote: Optional[int] = None
        if total_votes > 0 and not panel_tie:
            majority_vote = majority.get("majority")
            if majority_vote in (0, 1):
                fallback_vote = majority_vote

        if arbiter_vote in (0, 1):
            predicted_score = arbiter_vote
            panel_vote_source = "arbiter_final"
            threshold_note = "Arbiter decision adopted."
        elif fallback_vote in (0, 1):
            predicted_score = fallback_vote
            if total_votes == 1:
                panel_vote_source = "single_debater"
                threshold_note = "Single debater vote adopted."
            else:
                panel_vote_source = "panel_majority"
                threshold_note = "Panel majority adopted."
        elif total_votes > 0 and panel_tie:
            panel_vote_source = "panel_tie"
            threshold_note = "Debater votes tied; no consensus reached."
        else:
            panel_vote_source = "no_votes"
            threshold_note = "No eligible votes available."

        if final_decision:
            reasoning = final_decision
        elif predicted_score in (0, 1):
            reasoning = f"Predicted by {panel_vote_source} with vote {predicted_score}."
        else:
            reasoning = "No agent produced a decisive verdict."

        return {
            "predicted_score": predicted_score,
            "reasoning": reasoning,
            "messages": messages,
            "background_info": background_info,
            "strict_score": strict_final,
            "loose_score": loose_final,
            "strict_round_scores": strict_history,
            "loose_round_scores": loose_history,
            "rag_details": rag_details,
            "threshold_note": threshold_note,
            "majority_vote": majority,
            "weighted_score": weighted_score,
            "panel_vote_source": panel_vote_source,
            "arbiter_vote": arbiter_vote if arbiter_vote in (0, 1) else None,
            "arbiter_payload": arbiter_payload,
            "arbiter_risk_level": None,
            "arbiter_forced_override": False,
            "arbiter_force_reason": None,
        }

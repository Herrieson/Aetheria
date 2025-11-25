import asyncio
import base64
import binascii
import logging
from functools import partial
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from aetheria_simple.services import ReviewResult, ReviewService

logger = logging.getLogger(__name__)


class ReviewRequest(BaseModel):
    input_1: str = Field(..., description="Primary user submitted content.")
    input_2: str | None = Field(
        "",
        description=(
            "Optional second content. Supports plain text or image data encoded as a "
            "base64 string (data URI or raw base64)."
        ),
    )
    metadata: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Arbitrary metadata to store alongside the review log.",
    )


class MessagePayload(BaseModel):
    role: str
    content: str


class ReviewResponse(BaseModel):
    request_id: str
    created_at: str
    predicted_score: int | None
    reasoning: str
    background_info: str
    messages: List[MessagePayload]
    log_path: str
    metadata: Dict[str, Any]
    rag_details: Dict[str, Any]
    strict_score: float | None
    loose_score: float | None
    strict_round_scores: List[float]
    loose_round_scores: List[float]
    panel_vote_source: str
    threshold_note: str
    majority_vote: Dict[str, Any]
    weighted_score: float | None
    arbiter_vote: int | None
    arbiter_payload: Dict[str, Any]


app = FastAPI(title="Aetheria Simple Review BFF")

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
    ],
)

_service = ReviewService()


def _is_base64_image(value: str | None) -> bool:
    if not value:
        return False

    candidate = value.strip()
    if candidate.startswith("data:image/"):
        return True

    try:
        base64.b64decode(candidate, validate=True)
    except (binascii.Error, ValueError):
        return False

    return True


@app.get("/health")
async def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/api/review", response_model=ReviewResponse)
async def review(payload: ReviewRequest) -> Dict[str, Any]:
    loop = asyncio.get_running_loop()

    metadata: Dict[str, Any] = {"source": "frontend"}
    if payload.metadata:
        metadata.update(payload.metadata)

    if _is_base64_image(payload.input_2):
        metadata.setdefault("input_2_hint", "image_base64")

    try:
        result: ReviewResult = await loop.run_in_executor(
            None,
            partial(
                _service.review,
                payload.input_1,
                payload.input_2 or "",
                metadata=metadata,
            ),
        )
    except Exception as exc:  # pragma: no cover - just bubble via API response
        logger.exception("Simplified evaluation failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {
        "request_id": result.request_id,
        "created_at": result.created_at.isoformat(),
        "predicted_score": result.predicted_score,
        "reasoning": result.reasoning,
        "background_info": result.background_info,
        "messages": result.messages,
        "log_path": str(result.log_path),
        "metadata": result.metadata,
        "rag_details": result.rag_details,
        "strict_score": result.strict_score,
        "loose_score": result.loose_score,
        "strict_round_scores": result.strict_round_scores,
        "loose_round_scores": result.loose_round_scores,
        "panel_vote_source": result.panel_vote_source,
        "threshold_note": result.threshold_note,
        "majority_vote": result.majority_vote,
        "weighted_score": result.weighted_score,
        "arbiter_vote": result.arbiter_vote,
        "arbiter_payload": result.arbiter_payload,
    }


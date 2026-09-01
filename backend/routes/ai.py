"""Groq-backed explanations for discrepancies that the deterministic engine
in reconciliation.py has already classified.

IMPORTANT: Groq is only ever asked to *explain* a result, never to decide
one. The category, priority, and amounts sent to the model are already
final by the time we get here -- the prompt explicitly tells the model not
to change them. This keeps the LLM a narrator, not a decision-maker.
"""

import json
import logging

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException
from groq import Groq

from auth import get_current_user
from config import settings
from database import get_db
from models import AIAnalysisResponse, AIExplanation, AnalyzeRequest

router = APIRouter(prefix="/ai", tags=["ai"])
logger = logging.getLogger("reconcile.ai")

_client: Groq | None = Groq(api_key=settings.groq_api_key) if settings.groq_api_key else None

SYSTEM_PROMPT = """You are a financial reconciliation assistant. A deterministic \
rules engine has already compared orders against payments and produced a final \
classification. You do not re-decide anything -- the category, amounts, and \
whether records match are already fixed facts. Your only job is to explain the \
result in plain English and suggest a practical next step for a finance user.

Rules:
- Never contradict or change the given category.
- Never claim two records match if the data says they don't, or vice versa.
- Clearly separate what is a known fact (from the data given) from what is a \
hypothesis about why it happened.
- Be concise and practical.

Respond with ONLY a JSON object with exactly these keys: \
"what_happened", "likely_cause", "recommended_action". No other text."""


def _call_groq(user_prompt: str) -> dict | None:
    if _client is None:
        return None
    try:
        response = _client.chat.completions.create(
            model=settings.groq_model,
            temperature=0.2,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        )
        content = response.choices[0].message.content
        return json.loads(content)
    except Exception:
        logger.exception("Groq call failed")
        return None


def _fallback_explanation(reason: str) -> AIExplanation:
    return AIExplanation(
        what_happened=reason,
        likely_cause="AI explanation is unavailable right now.",
        recommended_action="Review the deterministic reason above and the order/payment records manually.",
        is_fallback=True,
    )


@router.post("/explain/{reconciliation_id}/{discrepancy_id}", response_model=AIExplanation)
def explain_discrepancy(reconciliation_id: str, discrepancy_id: str, user: dict = Depends(get_current_user)):
    db = get_db()
    user_id = str(user["_id"])
    dataset = db.datasets.find_one({"_id": _oid_or_404(reconciliation_id), "user_id": user_id})
    if not dataset:
        raise HTTPException(status_code=404, detail="Reconciliation not found")

    doc = db.reconciliations.find_one({
        "_id": _oid_or_404(discrepancy_id), "reconciliation_id": reconciliation_id, "user_id": user_id,
    })
    if not doc:
        raise HTTPException(status_code=404, detail="Discrepancy not found")

    prompt = (
        f"Category: {doc['category']}\n"
        f"Priority: {doc['priority']}\n"
        f"Reason (deterministic): {doc['reason']}\n"
        f"Order: {json.dumps(doc.get('order'))}\n"
        f"Payment: {json.dumps(doc.get('payment'))}\n"
        f"Difference: {doc.get('difference')}\n"
        f"Financial impact: {doc.get('financial_impact')}\n"
        "Explain this single discrepancy."
    )
    result = _call_groq(prompt)
    if result is None:
        return _fallback_explanation(doc["reason"])
    try:
        return AIExplanation(**result, is_fallback=False)
    except Exception:
        logger.exception("Groq returned a malformed response: %r", result)
        return _fallback_explanation(doc["reason"])


@router.post("/analyze/{reconciliation_id}", response_model=AIAnalysisResponse)
def analyze_discrepancies(reconciliation_id: str, payload: AnalyzeRequest, user: dict = Depends(get_current_user)):
    db = get_db()
    user_id = str(user["_id"])
    dataset = db.datasets.find_one({"_id": _oid_or_404(reconciliation_id), "user_id": user_id})
    if not dataset:
        raise HTTPException(status_code=404, detail="Reconciliation not found")

    oids = [_oid_or_404(i) for i in payload.discrepancy_ids]
    docs = list(db.reconciliations.find({
        "_id": {"$in": oids}, "reconciliation_id": reconciliation_id, "user_id": user_id,
    }))
    if not docs:
        raise HTTPException(status_code=404, detail="No matching discrepancies found")

    total_impact = sum(d.get("financial_impact", 0.0) for d in docs)
    lines = [
        f"- {d['category']} ({d['priority']}): order {d.get('order_id')}, impact {d.get('financial_impact')}: {d['reason']}"
        for d in docs
    ]
    prompt = (
        f"There are {len(docs)} discrepancies selected, total financial impact {total_impact}.\n"
        + "\n".join(lines)
        + "\n\nProvide: what_happened as an overall summary across all of them, "
        "likely_cause as the most likely shared cause(s), and recommended_action as "
        "the most useful next step(s)."
    )
    result = _call_groq(prompt)
    if result is None:
        return AIAnalysisResponse(
            selected_count=len(docs),
            total_financial_impact=total_impact,
            summary="AI analysis is unavailable right now. Review the discrepancies below manually.",
            recommended_actions=["Check GROQ_API_KEY is configured on the backend."],
            is_fallback=True,
        )
    try:
        action = result.get("recommended_action", "")
        actions = action if isinstance(action, list) else [action] if action else []
        return AIAnalysisResponse(
            selected_count=len(docs),
            total_financial_impact=total_impact,
            summary=f"{result.get('what_happened', '')} {result.get('likely_cause', '')}".strip(),
            recommended_actions=actions,
            is_fallback=False,
        )
    except Exception:
        logger.exception("Groq returned a malformed response: %r", result)
        return AIAnalysisResponse(
            selected_count=len(docs),
            total_financial_impact=total_impact,
            summary="AI analysis returned an unexpected format. Review the discrepancies below manually.",
            recommended_actions=[],
            is_fallback=True,
        )


def _oid_or_404(id_str: str) -> ObjectId:
    try:
        return ObjectId(id_str)
    except InvalidId:
        raise HTTPException(status_code=404, detail="Not found")

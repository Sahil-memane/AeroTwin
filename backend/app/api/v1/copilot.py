import logging
import sys
import os

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from typing import List, Optional
from uuid import UUID
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import settings
from app.core.security import get_current_active_user

logger = logging.getLogger(__name__)
router = APIRouter()
# This endpoint's every call proxies to a paid, quota-limited external LLM
# (Gemini) — unlike the other read/write endpoints in this API, an
# unthrottled authenticated user could run up real cost or exhaust the
# shared daily quota for everyone. Same per-router Limiter pattern as
# auth.py (its own in-memory store, not app.state.limiter).
limiter = Limiter(key_func=get_remote_address)

# AeroTwin_Rag/ is a sibling of app/ under backend/, not a proper package
# (no __init__.py) — add it to sys.path once so copilot_engine is importable.
_RAG_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "AeroTwin_Rag"))
if _RAG_DIR not in sys.path:
    sys.path.insert(0, _RAG_DIR)


class CopilotQuery(BaseModel):
    message: str
    engine_id: Optional[UUID] = None


class CopilotResponse(BaseModel):
    answer: str
    sources: List[str] = []


@router.post("/query", response_model=CopilotResponse)
@limiter.limit("10/minute")
async def query_copilot(
    request: Request,
    query: CopilotQuery,
    current_user=Depends(get_current_active_user),
):
    """
    Ask the AeroTwin Maintenance Copilot a question. Answered from the
    static AeroTwin knowledge base (RAG), live engine data (when the
    question and `engine_id` call for it), or both — see
    AeroTwin_Rag/context_selector.py for how that's decided.
    """
    from copilot_engine import get_engine, CopilotNotConfigured
    from llm_providers import ErrorCategory, LLMProviderError

    try:
        engine = get_engine(settings)
    except CopilotNotConfigured as e:
        raise HTTPException(status_code=503, detail=str(e))

    try:
        result = await engine.answer(query.message, str(query.engine_id) if query.engine_id else None)
    except LLMProviderError as e:
        # e.technical_detail may include SDK error bodies — logged only,
        # never sent to the client. The client gets a short, category-
        # specific message instead of a single undifferentiated 502.
        logger.error("Copilot provider error [%s]: %s", e.category, e.technical_detail)
        safe_messages = {
            ErrorCategory.NOT_CONFIGURED: "Copilot isn't configured — no LLM provider has a valid API key set.",
            ErrorCategory.INVALID_KEY: "The configured LLM provider rejected its API key. Check backend configuration.",
            ErrorCategory.QUOTA_EXCEEDED: "The LLM provider's rate limit or quota was reached. Please try again shortly.",
            ErrorCategory.TIMEOUT: "The LLM provider took too long to respond. Please try again.",
            ErrorCategory.UNAVAILABLE: "The LLM provider is temporarily unavailable. Please try again shortly.",
            ErrorCategory.INVALID_MODEL: "The configured model name isn't valid for this provider.",
            ErrorCategory.MALFORMED_RESPONSE: "The LLM provider returned an unexpected response.",
            ErrorCategory.EMPTY_RESPONSE: "The LLM provider returned an empty response. Please try again.",
        }
        detail = safe_messages.get(e.category, "Copilot upstream error — check backend logs for details.")
        status_code = 503 if e.category == ErrorCategory.NOT_CONFIGURED else 502
        raise HTTPException(status_code=status_code, detail=detail)
    except Exception as e:
        logger.exception("Copilot query failed")
        raise HTTPException(status_code=502, detail=f"Copilot upstream error: {e}")

    return CopilotResponse(**result)

"""
AeroTwin Copilot engine — one RAG pipeline, pluggable LLM provider.

    User query
        -> classify_intent()          (context_selector.py)
        -> resolve_engine_reference() (context_selector.py)
        -> ChromaDB retrieval          [only if intent needs it]
        -> build_live_context()       (context_selector.py)  [only if intent needs it]
        -> short system prompt + compact user prompt
        -> LLMProvider.generate()      (llm_providers.py, with fallback)

Loads lazily (`get_engine()`) so importing this module — and therefore
starting the FastAPI app — never requires any provider's API key or the
ChromaDB store to exist; only actually answering a query does.
"""
import logging
import os
import time
from typing import Optional

from context_selector import build_live_context, classify_intent, resolve_engine_reference
from llm_providers import ErrorCategory, LLMProviderError, build_provider

logger = logging.getLogger(__name__)

_HERE = os.path.dirname(os.path.abspath(__file__))
_CHROMA_DIR = os.path.join(_HERE, "ChromaDB_AeroTwin")

TOP_K = 3
MAX_CHUNK_CHARS = 800
PROVIDER_ORDER = ("groq", "gemini", "ollama")

CASUAL_QUERIES = {
    "hi", "hello", "hey", "hii", "okk", "ok", "okay",
    "thanks", "thank you", "got it",
    "good morning", "good afternoon", "good evening",
}
CASUAL_REPLY = "Sure! Let me know what you'd like to know about AeroTwin."

# Kept short deliberately — the spec this was built against explicitly
# calls out prompt-size reduction as the main objective, and grounding
# rules don't need multi-paragraph elaboration to be effective.
#
# Accuracy-First Phase 6 (Copilot Accuracy & Grounding): every context
# line handed to the model below is PRE-TAGGED by code (see
# `_tag_context_line`/`_tag_chunk`), not left for the model to guess —
# it only has to copy the tag it was already given, not classify
# live-telemetry-vs-model-prediction itself.
SYSTEM_PROMPT = """You are the AeroTwin Maintenance Copilot for a UAV engine health monitoring and predictive maintenance system.

Rules:
- Use ONLY the knowledge/live-data given below. Never invent sensor values, RUL, fault classes, confidence, health scores, maintenance records, thresholds, or regulatory requirements.
- Clearly distinguish a measured/live value from a model prediction — never state a prediction as a confirmed fact.
- Never treat old or example data as the current state.
- If live data needed to answer isn't provided below, say plainly that live data isn't available — do not guess.
- If the knowledge base doesn't cover something, say so plainly.
- If the question is unrelated to AeroTwin or engine health, decline briefly.
- Answer directly and concisely; use structure only for genuinely technical answers.
- Every line under "Live data:"/"Knowledge:" below already ends with its own bracketed source tag — [LIVE] for directly measured telemetry, [PREDICTION] for a model's output (RUL/health score/fault/bearing/aux), [DOCS] for knowledge-base content, [SIMULATION] for replay/what-if data. When you state a fact drawn from one of those lines, prefix that sentence with the SAME tag, copied exactly. Never assign a tag yourself to a fact from your own general knowledge — leave it untagged instead."""

_PREDICTION_FIELDS = {
    "rul_cycles", "degradation_index",
    "health_score", "contributing_factors",
    "fault_class", "fault_confidence", "fault_input_coverage", "fault_reliable", "fault_note",
    "bearing_condition", "bearing_location", "bearing_severity_inches",
    "aux_risk_level", "aux_failure_probability_pct", "aux_primary_cause",
}


def _tag_context_line(key: str) -> Optional[str]:
    """Every `build_live_context()` field is either raw measured
    telemetry (LIVE) or a model's own output (PREDICTION) — which one
    is a static, known mapping, not something the LLM should have to
    infer per-query. `engine`/`telemetry_ts` are identifiers, not facts
    worth tagging."""
    if key in ("engine", "telemetry_ts"):
        return None
    return "PREDICTION" if key in _PREDICTION_FIELDS else "LIVE"


class CopilotNotConfigured(RuntimeError):
    """Raised when no LLM provider is usable or the ChromaDB store doesn't exist yet."""


def _dedupe_and_trim(docs) -> list[str]:
    """Drops duplicate chunks (same content retrieved twice) and caps each
    chunk's length — a single long chunk shouldn't be able to dominate
    the prompt budget."""
    seen = set()
    out = []
    for doc in docs:
        text = doc.page_content.strip()
        key = text[:200]
        if key in seen or not text:
            continue
        seen.add(key)
        if len(text) > MAX_CHUNK_CHARS:
            text = text[:MAX_CHUNK_CHARS].rsplit(" ", 1)[0] + "…"
        out.append(text)
    return out


class _CopilotEngine:
    def __init__(self, settings):
        from langchain_google_genai import GoogleGenerativeAIEmbeddings
        from langchain_chroma import Chroma

        self._settings = settings

        if not os.path.isdir(_CHROMA_DIR):
            raise CopilotNotConfigured(
                f"ChromaDB store not found at {_CHROMA_DIR} — run AeroTwin_Rag/rag.py to build it first."
            )
        # Embeddings still go through Gemini regardless of which provider
        # answers the chat — Groq/Ollama don't offer an equivalent
        # embedding endpoint this ChromaDB store was built with, and
        # embeddings are a separate, much cheaper call than generation.
        if not settings.GEMINI_API_KEY:
            raise CopilotNotConfigured("GEMINI_API_KEY is required for retrieval embeddings even when a different LLM_PROVIDER answers.")

        embedding_model = GoogleGenerativeAIEmbeddings(model="gemini-embedding-001", google_api_key=settings.GEMINI_API_KEY)
        self._vector_store = Chroma(persist_directory=_CHROMA_DIR, embedding_function=embedding_model)
        self._retriever = self._vector_store.as_retriever(search_type="similarity", search_kwargs={"k": TOP_K})

    def _generate_with_fallback(self, system_prompt: str, user_prompt: str):
        primary = self._settings.LLM_PROVIDER
        order = [primary] + [p for p in PROVIDER_ORDER if p != primary]
        if not self._settings.LLM_FALLBACK_ENABLED:
            order = order[:1]

        last_error: Optional[LLMProviderError] = None
        for name in order:
            try:
                provider = build_provider(name, self._settings)
            except LLMProviderError as e:
                if e.category != ErrorCategory.NOT_CONFIGURED:
                    last_error = e
                continue  # not configured for this provider — skip quietly, not a "failure"
            try:
                return provider.generate(system_prompt, user_prompt)
            except LLMProviderError as e:
                logger.warning("LLM provider '%s' failed (%s): %s", name, e.category, e.technical_detail)
                last_error = e
                continue

        raise last_error or LLMProviderError(ErrorCategory.NOT_CONFIGURED, "No LLM provider is configured")

    async def answer(self, question: str, engine_id_hint: Optional[str] = None) -> dict:
        normalized = question.strip().lower()
        if normalized in CASUAL_QUERIES:
            return {"answer": CASUAL_REPLY, "sources": []}

        # Intent is decided from the question's own words alone — engine
        # resolution (and its "unknown identifier" short-circuit) only
        # happens once that's already established a live lookup is
        # actually needed, not merely because an engine_id is in scope.
        intent, requested_fields = classify_intent(question)

        chunks: list[str] = []
        sources: list[str] = []
        live_context: Optional[dict] = None
        engine_ref = None

        if intent in ("live", "combined"):
            engine_ref = await resolve_engine_reference(question, engine_id_hint)
            if engine_ref == "unknown":
                return {
                    "answer": "I don't recognize that engine identifier — please check it and try again.",
                    "sources": [],
                }
            if engine_ref:
                live_context = await build_live_context(engine_ref, requested_fields)

        if intent in ("static", "combined"):
            retrieved_docs = self._retriever.invoke(question)
            chunks = _dedupe_and_trim(retrieved_docs)
            sources = sorted({f"page {d.metadata['page']}" for d in retrieved_docs if "page" in d.metadata})

        prompt_parts = []
        if live_context:
            live_lines = []
            for k, v in live_context.items():
                tag = _tag_context_line(k)
                live_lines.append(f"{k}: {v} [{tag}]" if tag else f"{k}: {v}")
            prompt_parts.append("Live data:\n" + "\n".join(live_lines))
        if chunks:
            # Every retrieved chunk is knowledge-base content by
            # construction (the ChromaDB store built from the docs PDF),
            # never live/simulation data — tag each one [DOCS].
            tagged_chunks = [f"{c} [DOCS]" for c in chunks]
            prompt_parts.append(f"Knowledge:\n{chr(10).join(tagged_chunks)}")
        prompt_parts.append(f"Question: {question}")
        user_prompt = "\n\n".join(prompt_parts)

        started = time.monotonic()
        try:
            result = await _run_in_thread(self._generate_with_fallback, SYSTEM_PROMPT, user_prompt)
        except LLMProviderError as e:
            logger.error(
                "Copilot LLM call failed [%s]: %s (intent=%s, chunks=%d, engine=%s)",
                e.category, e.technical_detail, intent, len(chunks),
                engine_ref.serial_number if engine_ref else None,
            )
            raise

        logger.info(
            "Copilot query: intent=%s query_len=%d chunks=%d live_fields=%s "
            "prompt_chars=%d provider=%s model=%s latency=%.2fs input_tokens=%s output_tokens=%s",
            intent, len(question), len(chunks), sorted(requested_fields) if requested_fields else None,
            len(SYSTEM_PROMPT) + len(user_prompt), result.provider, result.model,
            time.monotonic() - started, result.input_tokens, result.output_tokens,
        )

        return {"answer": result.text, "sources": sources}


async def _run_in_thread(fn, *args):
    """The provider call is a blocking network request (up to tens of
    seconds under retry/backoff, proven live this session) — running it
    directly inside this async method would stall the whole event loop
    for every other request, the same bug already found and fixed in
    the live telemetry ingestion path this session."""
    import asyncio
    return await asyncio.to_thread(fn, *args)


_engine: Optional[_CopilotEngine] = None


def get_engine(settings) -> _CopilotEngine:
    global _engine
    if _engine is None:
        _engine = _CopilotEngine(settings)
    return _engine

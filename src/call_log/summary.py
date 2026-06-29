"""Call summary generation and outcome derivation (NOTIF-02, D-05, D-06).

_determine_outcome  : derives outcome taxonomy value from flow state (Pattern 5).
generate_summary    : LLM-backed 2-3 sentence Italian summary via direct Anthropic SDK.

Security:
- T-03-PII: exception handlers log only type(exc).__name__; NEVER transcript/name/phone.
- T-03-KEY: ANTHROPIC_API_KEY read exclusively via os.getenv (never hardcoded).

Pattern analog: src/flows/functions.py (async handler + PII-safe except).
"""

from __future__ import annotations

import os

from loguru import logger

from src.config.tenant_config import TenantConfig


def _determine_outcome(state: dict) -> str:
    """Derive the D-06 outcome taxonomy value from the flow manager's state dict.

    Priority (Pattern 5, RESEARCH.md — corrected 260629-tkr):
    1. state['outcome'] == 'trasferito'  — deliberate operator handoff always surfaces
    2. confirmed_event_id present        → 'prenotato'
       (a confirmed Google Calendar event must NEVER be downgraded to 'fallito' or
       'abbandonato' by a later dead-air watchdog or error observer — 260629-tkr bug)
    3. any other explicit state['outcome'] — e.g. 'fallito' when no booking confirmed
    4. faq_answered truthy               → 'faq'
    5. booking_slot without event        → 'abbandonato' (D-18 bozza behavior)
    6. default                           → 'faq' (no booking attempted)

    Args:
        state: flow_manager.state dict (or any equivalent dict of flow state).

    Returns:
        One of: 'prenotato', 'faq', 'trasferito', 'abbandonato', 'fallito'.
    """
    # Rule 1: deliberate human handoff surfaces to the owner even over a confirmed booking.
    # 'trasferito' is set by handle_transfer_call (03-01); it must never be silenced.
    if state.get("outcome") == "trasferito":
        return "trasferito"

    # Rule 2: booking was completed and a Google Calendar event was created.
    # This check precedes the generic explicit-outcome check (Rule 3) to prevent a
    # background watchdog (e.g. dead-air T2) or error observer from setting
    # state['outcome'] = 'fallito'/'abbandonato' and burying a confirmed booking
    # (260629-tkr root cause: call_logs id=2 had outcome='fallito' but google_event_id set).
    if state.get("confirmed_event_id"):
        return "prenotato"

    # Rule 3: any other explicit override (e.g. 'fallito' set by ErrorFallbackObserver
    # escalation when no booking was confirmed; outcome='abbandonato' from early timeout).
    if state.get("outcome"):
        return state["outcome"]

    # Rule 4: caller's question was answered via FAQ
    if state.get("faq_answered"):
        return "faq"

    # Rule 5: booking was started (slot chosen) but not confirmed — call ended mid-booking
    if state.get("booking_slot") and not state.get("confirmed_event_id"):
        return "abbandonato"

    # Rule 6: default — call ended without booking attempt
    return "faq"


async def generate_summary(
    tenant: TenantConfig,
    transcript: list,
    outcome: str,
) -> str:
    """Generate a 2-3 sentence Italian call summary via direct Anthropic SDK call.

    Uses tenant.model (default claude-haiku-4-5) — does NOT hardcode a different
    model id (CLAUDE.md constraint, A2 note: verify model id at build time).
    API key read only via os.getenv("ANTHROPIC_API_KEY") (T-03-KEY).

    On any exception, returns a safe fallback string and logs ONLY the exception
    type — never the transcript, caller name, or phone (T-03-PII, D-05).

    Args:
        tenant:     TenantConfig with .business_name and .model fields.
        transcript: List of {role, content} dicts from context.messages (last ~20 turns used).
        outcome:    D-06 outcome taxonomy value for this call.

    Returns:
        A 2-3 sentence Italian summary string, or a safe fallback on failure.
    """
    try:
        # Build a condensed transcript from the last 20 user/assistant turns
        turns = [
            f"{'Cliente' if m.get('role') == 'user' else 'Bot'}: {m.get('content', '')}"
            for m in transcript
            if m.get("role") in ("user", "assistant")
            and isinstance(m.get("content"), str)
        ]
        transcript_text = "\n".join(turns[-20:])

        prompt = (
            f"Sei un assistente che riassume chiamate per il titolare di {tenant.business_name}.\n"
            f"Esito della chiamata: {outcome}.\n\n"
            f"Trascrizione:\n{transcript_text}\n\n"
            "Scrivi un riassunto in italiano di 2-3 frasi brevi: chi ha chiamato (se noto), "
            "cosa voleva, e com'è andata a finire. Sii conciso e professionale."
        )

        import anthropic  # noqa: PLC0415 — imported here to keep top-level deps minimal

        # Security (T-03-KEY): API key only via os.getenv; never hardcoded or logged.
        client = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

        # Use tenant.model (per CLAUDE.md: do NOT hardcode a competing model id).
        response = await client.messages.create(
            model=tenant.model,
            max_tokens=256,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text

    except Exception as exc:  # noqa: BLE001
        # Security (T-03-PII): NEVER log transcript content, caller name, or phone.
        # Log only exception type so the on-call operator can diagnose the failure class.
        logger.error(
            f"generate_summary failed for tenant {tenant.business_name!r}: "
            f"{type(exc).__name__}"
        )
        # Return a safe operator-visible fallback that includes the outcome (D-05).
        return f"Riepilogo non disponibile (esito: {outcome})."

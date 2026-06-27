"""Centralino AI bot entry point — async def bot(runner_args).

The runner calls `bot(runner_args)` for each incoming WebRTC connection.
This module:
  1. Reads --tenant from runner_args.cli_args (D-04).
  2. Loads TenantConfig from TenantRepository.get_tenant() (D-03).
  3. Builds the SmallWebRTCTransport via TransportFactory (D-05).
  4. Assembles the streaming pipeline via build_pipeline() (VOICE-01).
  5. Registers on_client_connected to queue the Italian greeting (VOICE-02 / D-11).
  6. Wires FlowManager with per-node model override (D-19, Plan 02-03).
  7. Registers on_client_disconnected to save draft on abandonment (D-18, B2).
  8. Runs the PipelineWorker via WorkerRunner.
  9. Attaches LatencyObserver and ErrorFallbackObserver via PipelineParams (Plan 03).

Security (T-02-KEY): API keys are never logged or echoed; tenant_id comes from a
validated CLI arg and is passed to the parameterized repository query (Plan 01-01).
"""

from __future__ import annotations

import os
from datetime import datetime
from zoneinfo import ZoneInfo

from pipecat.frames.frames import LLMUpdateSettingsFrame, TTSSpeakFrame
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.runner.types import RunnerArguments, SmallWebRTCRunnerArguments
from pipecat.services.settings import LLMSettings
from pipecat.workers.runner import WorkerRunner
from pipecat_flows import FlowManager

from src.booking.repository import ReservationRepository
from src.calendar.google_provider import GoogleCalendarProvider
from src.calendar.memory_provider import InMemoryCalendarProvider
from src.call_log.repository import CallLogRepository
from src.call_log.summary import _determine_outcome, generate_summary
from src.config.repository import TenantRepository
from src.config.tenant_config import TenantConfig
from src.flows.functions import build_transfer_schema
from src.flows.nodes import build_greeting_node
from src.notifications.factory import create_channel
from src.pipeline.build import build_pipeline
from src.pipeline.factory import TransportFactory
from src.pipeline.fallback import ErrorFallbackObserver
from src.pipeline.observers import LatencyObserver

# Verified Anthropic model IDs (from Phase 1 STATE.md decision and Phase 2 Plan 02-01)
_HAIKU_MODEL = "claude-haiku-4-5"
_SONNET_MODEL = "claude-sonnet-4-6"

# Europe/Rome timezone — DST-aware (UTC+1 standard, UTC+2 during DST).
# WR-02: a fixed UTC+1 offset is wrong for ~7 months/year (DST), making
# call_logs.started_at and the notification subject off by one hour. Use the
# IANA zone like src/flows/nodes.py does so both compute the same "current" hour.
_ROME_TZ = ZoneInfo("Europe/Rome")

# Default JSONL log path (D-06); the observer's __init__ creates the dir if absent.
_LATENCY_LOG_PATH = os.path.join("logs", "latency.jsonl")

# REL-04 / D-14: dead-air watchdog constants (mirrors factory.py _WATCHDOG_T1/T2).
# T1 is set on the aggregator params (build_user_aggregator_params in factory.py).
# T2 is applied dynamically after the re-prompt via UserIdleTimeoutUpdateFrame.
_WATCHDOG_T2: float = 8.0  # seconds after re-prompt before escalation (D-14)


class _DeadAirHandler:
    """Dead-air watchdog escalation handler for on_user_turn_idle events (REL-04/D-14).

    Escalation ladder (SC5):
      - Count 1 (T1 expired): push gentle re-prompt LLMMessagesAppendFrame + raise
        the idle timeout to T2 via UserIdleTimeoutUpdateFrame (so T2 ≠ T1).
      - Count 2 (T2 expired): set outcome='fallito', push courtesy TTSSpeakFrame +
        EndWorkerFrame UPSTREAM to terminate the call cleanly.

    Call ``reset()`` on on_user_turn_started to restart the escalation ladder when
    the user speaks again.

    Security:
      - All courtesy/escalation phrases are static — no PII from caller input.
      - Transfer uses flow_manager.state['outcome'] pattern (same as ErrorFallbackObserver).
    """

    def __init__(self, flow_manager, worker) -> None:
        """Create the handler.

        Args:
            flow_manager: Active FlowManager whose .state['outcome'] is set on escalation.
            worker:       PipelineWorker used to queue UserIdleTimeoutUpdateFrame (T2 raise).
        """
        self._flow_manager = flow_manager
        self._worker = worker
        self._count: int = 0

    def reset(self) -> None:
        """Reset the idle counter — call from on_user_turn_started (user spoke again)."""
        self._count = 0

    async def on_idle(self, aggregator) -> None:
        """Handle an on_user_turn_idle event from the LLMUserAggregator.

        Args:
            aggregator: The LLMUserAggregator that fired the event; frames pushed
                        here flow downstream in the pipeline.
        """
        from pipecat.frames.frames import (
            EndWorkerFrame,
            LLMMessagesAppendFrame,
            TTSSpeakFrame,
            UserIdleTimeoutUpdateFrame,
        )
        from pipecat.processors.frame_processor import FrameDirection

        self._count += 1
        if self._count == 1:
            # T1 expired — gentle re-prompt (D-14, SC5).
            # Push an LLMMessagesAppendFrame that instructs the LLM to check naturally
            # whether the caller is still there, with run_llm=True so the LLM responds.
            await aggregator.push_frame(
                LLMMessagesAppendFrame(
                    messages=[{
                        "role": "user",
                        "content": (
                            "Sei ancora in linea? Non ho sentito risposta. "
                            "Chiedi gentilmente 'È ancora in linea?'"
                        ),
                    }],
                    run_llm=True,
                )
            )
            # Raise the idle timeout to T2 so the second trigger is a separate window.
            # Without this, the second idle fires T1 seconds after re-prompt (same T1).
            # With UserIdleTimeoutUpdateFrame(T2), it fires T2 seconds after re-prompt.
            await self._worker.queue_frame(
                UserIdleTimeoutUpdateFrame(timeout=_WATCHDOG_T2)
            )
        else:
            # T2 expired — escalation: set outcome and terminate (D-14, SC5).
            # V7/T-03-LOG: phrase is static; flow state updated before EndWorkerFrame.
            self._flow_manager.state["outcome"] = "fallito"
            await aggregator.push_frame(
                TTSSpeakFrame(
                    text="Non riesco a sentirla, la passo a un operatore.",
                    append_to_context=False,
                )
            )
            await aggregator.push_frame(EndWorkerFrame(), FrameDirection.UPSTREAM)


async def setup_flow(worker, llm, aggregators, tenant: TenantConfig) -> FlowManager:
    """Wire FlowManager into the pipeline with per-node model override (D-19, Plan 02-03).

    Constructs a FlowManager, populates its shared state with tenant context,
    registers per-node Sonnet / Haiku model-switch action handlers (Option B —
    LLMUpdateSettingsFrame delta; simpler than LLMSwitcher, avoids extra pipeline
    processor), and initializes the greeting node.

    Per-node model override (D-19):
    - Booking node pre_action {"type": "switch_llm_to_sonnet"} → sends
      LLMUpdateSettingsFrame(delta=LLMSettings(model=_SONNET_MODEL)) to switch to
      claude-sonnet-4-6 for more reliable tool-calling during data collection.
    - End/greeting nodes: no explicit switch; if needed a "switch_llm_to_haiku"
      action handler is registered to restore claude-haiku-4-5.

    Greeting reconciliation (W5):
    - The greeting node's respond_immediately=True (default) causes the LLM to
      speak when initialized. The make_greeting_handler / on_client_connected
      path separately queues a TTSSpeakFrame.  To avoid double-greeting, this
      function does NOT queue any TTSSpeakFrame — the single greeting comes from
      the FlowManager's greeting node LLM response (the TTSSpeakFrame path is
      kept for backward compatibility and fires before FlowManager is live, so
      the two do not overlap in practice; see SUMMARY for details).

    Args:
        worker: The PipelineWorker that owns the pipeline.
        llm: The AnthropicLLMService instance from build_pipeline (NOT re-created).
        aggregators: The LLMContextAggregatorPair from build_pipeline.
        tenant: The validated TenantConfig for this session.

    Returns:
        The initialized FlowManager instance.
    """
    # --- Action handlers for per-node model override (D-19, Option B) ---
    # Option B chosen over Option A (LLMSwitcher) to keep the pipeline unchanged —
    # no additional processor in the pipeline list; simpler wiring from bot.py.
    # Tradeoff: single LLM service object, model switched via settings delta.
    # Verified: LLMUpdateSettingsFrame / _update_settings is the same mechanism
    # FlowManager._update_llm_context uses for role_message → safe at runtime.

    async def _switch_llm_to_sonnet(action: dict, fm: FlowManager) -> None:
        """Switch to claude-sonnet-4-6 for the booking node (D-19)."""
        await fm.worker.queue_frame(
            LLMUpdateSettingsFrame(delta=LLMSettings(model=_SONNET_MODEL))
        )

    async def _switch_llm_to_haiku(action: dict, fm: FlowManager) -> None:
        """Restore claude-haiku-4-5 for greeting/end/faq nodes (D-19)."""
        await fm.worker.queue_frame(
            LLMUpdateSettingsFrame(delta=LLMSettings(model=_HAIKU_MODEL))
        )

    # FlowManager takes worker= (NOT deprecated task=) — RESEARCH §Anti-Patterns
    # Phase 3 (03-01): global_functions=[build_transfer_schema()] makes transfer_call
    # available from ANY node (greeting/booking/faq) without adding it to each node
    # individually (HAND-04 — transfer from any flow point).
    flow_manager = FlowManager(
        llm=llm,
        context_aggregator=aggregators,
        worker=worker,
        global_functions=[build_transfer_schema()],
    )

    # Register per-node action handlers BEFORE initialize() so they are available
    # when the booking node fires its pre_actions on first entry.
    flow_manager.register_action("switch_llm_to_sonnet", _switch_llm_to_sonnet)
    flow_manager.register_action("switch_llm_to_haiku", _switch_llm_to_haiku)

    # Populate tenant context in flow state — never from caller input (T-02-06/T-02-10)
    flow_manager.state["tenant_id"] = tenant.id
    flow_manager.state["tenant"] = tenant
    # db_path defaults to "centralino.db"; bot() overrides this with the repo path
    flow_manager.state["db_path"] = "centralino.db"
    # calendar_provider will be set by bot() to GoogleCalendarProvider in production
    # or InMemoryCalendarProvider in dev/tests; left None here until bot() sets it.
    flow_manager.state["calendar_provider"] = None

    # Initialize with the greeting node (respond_immediately=True triggers LLM greeting)
    # NOTE: This is the single greeting path.  make_greeting_handler is disabled in bot()
    # when FlowManager is active — see bot() greeting reconciliation comment.
    await flow_manager.initialize(build_greeting_node(tenant))

    return flow_manager


def make_abandonment_handler(flow_manager, reservation_repo, calendar_provider):
    """Return an async cleanup handler for call-termination on an unconfirmed booking (D-18).

    Called when a call ends (via transport on_client_disconnected or cleanup hook)
    while a booking is still in progress (status='bozza', never confirmed).

    The handler:
    1. Reads partial booking fields from flow_manager.state
    2. Calls reservation_repo.save_draft(...) to persist the partial record
    3. NEVER calls calendar_provider.create_event (drafts stay out of Calendar — D-18)

    Follow-up / notification for abandoned drafts is Phase 3.

    Args:
        flow_manager: active FlowManager (or compatible namespace with .state dict).
        reservation_repo: ReservationRepository instance for save_draft.
        calendar_provider: CalendarProvider instance — spied on in tests to assert
                           create_event is never called.

    Returns:
        An async coroutine ``handler()`` suitable for call-termination cleanup.
    """

    async def on_call_abandoned() -> None:
        state = flow_manager.state
        booking_slot = state.get("booking_slot") or {}
        customer = state.get("customer") or {}
        tenant_id: str = state.get("tenant_id", "")

        # Only save a draft if at least a tenant_id is known
        if not tenant_id:
            return

        await reservation_repo.save_draft(
            tenant_id=tenant_id,
            slot_date=booking_slot.get("date"),
            slot_time=booking_slot.get("time_slot"),
            covers=booking_slot.get("covers"),
            name=customer.get("name"),
            phone=customer.get("phone"),
        )
        # create_event is intentionally NEVER called for abandoned/draft bookings (D-18)

    return on_call_abandoned


def make_greeting_handler(worker: PipelineWorker, tenant: TenantConfig):
    """Return an async event handler that queues the tenant greeting on connect.

    This factory is separated out so that unit tests can call the handler
    directly without running the full bot/runner lifecycle.

    Args:
        worker: The `PipelineWorker` that owns the pipeline. The greeting frame
                is queued onto it so it is processed in pipeline order.
        tenant: The tenant whose `greeting` text is spoken (VOICE-02, D-11).

    Returns:
        An async coroutine ``handler(transport, client)`` suitable for
        ``@transport.event_handler("on_client_connected")``.

    Barge-in note (D-11): `SileroVADAnalyzer` is already running inside the
    pipeline aggregator — the caller can interrupt the greeting immediately.
    Queuing a `TTSSpeakFrame` (not `LLMRunFrame`) means the greeting goes
    directly to TTS without an LLM round-trip, which also minimises latency.
    """

    async def on_client_connected(transport, client):
        # TTSSpeakFrame routes directly to TTS (no LLM) — lowest latency for
        # a fixed greeting that is already a string in tenant config.
        # append_to_context=True adds the greeting to conversation history
        # so subsequent LLM turns see it as the opening assistant utterance.
        await worker.queue_frames(
            [TTSSpeakFrame(text=tenant.greeting, append_to_context=True)]
        )

    return on_client_connected


async def bot(runner_args: RunnerArguments) -> None:
    """Bot coroutine — called once per WebRTC connection by the Pipecat runner.

    Args:
        runner_args: Runner-supplied arguments. For Phase 1, this is always a
                     `SmallWebRTCRunnerArguments` instance (WebRTC transport).
                     Phase 4 adds handling for Telnyx runner arguments here.
    """
    # Build the transport from the runner-supplied WebRTC connection (D-05).
    # TransportFactory is the seam Phase 4 extends for Telnyx — pipeline unchanged.
    if isinstance(runner_args, SmallWebRTCRunnerArguments):
        factory = TransportFactory()
        transport = factory.create_webrtc_transport(runner_args.webrtc_connection)
    else:
        # Future: elif isinstance(runner_args, TelnyxRunnerArguments): ...
        raise ValueError(
            f"Unsupported runner argument type: {type(runner_args).__name__}. "
            "Phase 1 supports SmallWebRTCRunnerArguments only."
        )

    # D-04: tenant id from --tenant CLI arg; validated by TenantConfig/repository.
    tenant_id: str = runner_args.cli_args.tenant  # type: ignore[union-attr]

    # D-03: load TenantConfig at call start — the seam Phases 2–5 extend.
    repo = TenantRepository()
    tenant = await repo.get_tenant(tenant_id)

    # Assemble the streaming pipeline (VOICE-01).
    # build_pipeline returns a BuildResult with .pipeline, .context, .llm, .aggregators.
    # 2-tuple destructuring still works via BuildResult.__iter__.
    build = build_pipeline(transport, tenant)
    pipeline, context = build  # backward-compatible destructuring

    # Plan 03 (D-06 / REL-01): build the observers before the worker.
    # ErrorFallbackObserver needs a worker reference to queue frames; we resolve the
    # circular dependency by constructing it with a placeholder (None) and patching
    # the .worker attribute immediately after the worker is created.
    latency_observer = LatencyObserver(_LATENCY_LOG_PATH)
    error_observer = ErrorFallbackObserver(worker=None)  # patched below

    # CRITICAL (root-cause fix): custom observers must be passed via the dedicated
    # `observers=` parameter of PipelineWorker, NOT inside PipelineParams.
    # PipelineParams is a Pydantic model with NO `observers` field, so a previous
    # `PipelineParams(observers=[...])` was silently dropped — our observers were never
    # attached to the WorkerObserver proxy and on_push_frame never fired (push_calls=0),
    # breaking BOTH latency capture (D-06) and the error-fallback courtesy phrase (REL-01).
    # The worker's own turn_tracking_observer kept working because it is appended to the
    # internal observers list directly by the worker, not via params. Verified against
    # pipecat 1.4.0 PipelineWorker.__init__ signature (observers kwarg) and worker.py.
    worker = PipelineWorker(
        pipeline,
        observers=[latency_observer, error_observer],
        params=PipelineParams(
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
    )

    # Resolve circular references now that `worker` exists.
    # ErrorFallbackObserver needs the worker to queue frames (REL-01).
    # WorkerRefHolder in the stt_switcher needs the worker to queue the STT-switch
    # courtesy phrase (REL-03 / SC3).
    error_observer.worker = worker
    build.worker_ref_holder.worker = worker

    # D-06 turn-end wiring: the LatencyObserver emits its per-turn line + JSONL when
    # the pipeline's built-in TurnTrackingObserver fires `on_turn_ended`. That observer
    # is created automatically by the worker (enable_turn_tracking defaults to True) and
    # exposed as `worker.turn_tracking_observer`. Registering here — rather than inferring
    # turn end from a raw frame inside on_push_frame — is the reliable signal that survives
    # barge-in/interruptions and was the fix for the live "no latency line" bug.
    latency_observer.register_turn_end(worker.turn_tracking_observer)

    # Set up the FlowManager with per-node model override and greeting node (D-19, Plan 02-03).
    # This must run BEFORE runner.run() and AFTER worker creation.
    # The calendar_provider is set to None for dev (no Google credentials required);
    # production wires GoogleCalendarProvider here.
    repo_path = repo._db_path if hasattr(repo, "_db_path") else "centralino.db"
    flow_manager = await setup_flow(worker, build.llm, build.aggregators, tenant)
    # Override db_path now that we have the real repo path from TenantRepository
    flow_manager.state["db_path"] = repo_path

    # REL-02 (Phase 03-04): patch ErrorFallbackObserver with FlowManager reference.
    # The observer needs flow_manager to set outcome='fallito' on persistent failure
    # escalation (D-13/SC4). Must be set after FlowManager is created (circular-dep
    # pattern mirrors error_observer.worker patch above).
    error_observer.flow_manager = flow_manager

    # Wire the real CalendarProvider now that the tenant is loaded. setup_flow()
    # leaves state["calendar_provider"] = None; without this the booking handler
    # calls create_event on None, which surfaces to the caller as the spurious
    # "il servizio non è disponibile" (the calendar-unavailable branch).
    # - Google credentials + a tenant calendar_id  -> real GoogleCalendarProvider
    #   (resolver maps this tenant_id -> its calendar_id; T-03/D-10 isolation).
    # - Otherwise                                  -> InMemoryCalendarProvider so
    #   booking still completes end-to-end in dev without Google setup.
    google_cred = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    resolved_calendar_id = tenant.calendar_id or os.getenv("GOOGLE_CALENDAR_ID_DEMO")
    if google_cred and resolved_calendar_id:
        calendar_provider = GoogleCalendarProvider(
            calendar_id_resolver={tenant.id: resolved_calendar_id}
        )
    else:
        calendar_provider = InMemoryCalendarProvider()
    flow_manager.state["calendar_provider"] = calendar_provider

    # D-18 / B2: register abandonment hook — fires on call termination with an
    # unconfirmed booking; saves a bozza draft that is NEVER written to Calendar.
    # The abandonment handler only guards create_event (which it never calls).
    reservation_repo = ReservationRepository(db_path=repo_path)

    @transport.event_handler("on_client_disconnected")
    async def _on_disconnected(transport_obj, client):
        # Only save draft if booking is in progress and not yet confirmed (D-18)
        if (
            flow_manager.state.get("booking_slot")
            and not flow_manager.state.get("confirmed_event_id")
        ):
            handler = make_abandonment_handler(
                flow_manager, reservation_repo, calendar_provider
            )
            await handler()

    # REL-04 (Phase 03-04): dead-air watchdog — re-prompt at T1, transfer at T2 (D-14/SC5).
    # The _DeadAirHandler is wired AFTER setup_flow so flow_manager is in scope.
    # Event handlers on build.aggregators.user() fire when the user aggregator detects
    # prolonged silence (user_idle_timeout=T1 set in build_user_aggregator_params).
    dead_air_handler = _DeadAirHandler(flow_manager=flow_manager, worker=worker)

    @build.aggregators.user().event_handler("on_user_turn_idle")
    async def _on_user_turn_idle(aggregator) -> None:
        """T1 expired: re-prompt; T2 expired: set outcome='fallito' + transfer."""
        await dead_air_handler.on_idle(aggregator)

    @build.aggregators.user().event_handler("on_user_turn_started")
    async def _on_user_turn_started(aggregator, strategy) -> None:
        """User spoke — reset watchdog counter so next silence starts fresh at T1."""
        dead_air_handler.reset()

    # D-11: The greeting is produced by the FlowManager greeting node (respond_immediately).
    # We do NOT queue an additional TTSSpeakFrame here to prevent double-greeting (W5).
    # The make_greeting_handler path is intentionally NOT registered when FlowManager is active.

    # Capture call start time before runner.run() so the timestamp is reliable even if the
    # runner raises (D-07: end-of-call hook must fire for EVERY call and EVERY outcome).
    call_start_time = datetime.now(_ROME_TZ).isoformat()

    # Cache the message list before runner.run() as a fallback.  After runner.run() the
    # LLMContext may have been torn down; build.context.messages might be empty.
    # We update this cache inside the finally block using the live context if available (A4).
    _cached_messages: list = []

    # Run the pipeline until the call ends.
    runner = WorkerRunner(handle_sigint=False)
    await runner.add_workers(worker)
    try:
        await runner.run()
    finally:
        # NOTIF-03 / D-07: end-of-call hook — runs for EVERY call and EVERY outcome.
        # 1. Determine outcome from flow state.
        # 2. Capture transcript from LLMContext (or fall back to cached list).
        # 3. Generate 2-3 sentence Italian summary via Anthropic (PII-safe).
        # 4. Persist call log row to call_logs table.
        # 5. Dispatch notification on tenant's configured channel.
        # A channel.send() failure is caught and logged by type only — never crashes shutdown.
        from loguru import logger  # noqa: PLC0415 — loguru always available

        # --- Step 1: build the summary inputs (PII-safe; generate_summary has its
        # own fallback and never raises). Guard outcome/transcript capture so a
        # surprise here still lets the owner notification fire (CR-01, D-07).
        try:
            outcome = _determine_outcome(flow_manager.state)
            # Prefer the live context messages; fall back to cached list if torn down (A4).
            transcript: list = list(build.context.messages) or _cached_messages
            summary_text = await generate_summary(tenant, transcript, outcome)
        except Exception as prep_exc:  # noqa: BLE001
            # T-03-LOGPII: log only exception type — never transcript/name/phone.
            logger.error(
                f"End-of-call summary prep failed for tenant {tenant.id!r}: "
                f"{type(prep_exc).__name__}"
            )
            outcome = flow_manager.state.get("outcome") or "fallito"
            transcript = []
            summary_text = f"Riepilogo non disponibile (esito: {outcome})."

        # --- Step 2: persist the call log. CR-01: a persistence failure here
        # (e.g. SQLite `database is locked` under concurrent multi-tenant calls,
        # or a json.dumps error) must NEVER suppress the owner notification, which
        # is the product's core deliverable. So this runs in its own try block.
        try:
            call_log_repo = CallLogRepository(db_path=repo_path)
            await call_log_repo.init_db()
            await call_log_repo.write(
                tenant_id=tenant.id,
                started_at=call_start_time,
                outcome=outcome,
                transcript_json=transcript,
                summary_text=summary_text,
                reservation_id=flow_manager.state.get("reservation_id"),
                google_event_id=flow_manager.state.get("confirmed_event_id"),
                transfer_number=(
                    flow_manager.state.get("transfer_payload", {}).get("transfer_number")
                    if isinstance(flow_manager.state.get("transfer_payload"), dict)
                    else None
                ),
                channel_sent=tenant.notification_channel,
            )
        except Exception as db_exc:  # noqa: BLE001
            # T-03-LOGPII: log only exception type — never transcript/name/phone.
            logger.error(
                f"call_log write failed for tenant {tenant.id!r}: "
                f"{type(db_exc).__name__}"
            )

        # --- Step 3: dispatch the owner notification. CR-01: runs regardless of
        # the DB outcome above, so a transient persistence error never costs the
        # owner their end-of-call summary.
        try:
            channel = create_channel(tenant.notification_channel, tenant)
            subject = (
                f"Chiamata {datetime.now(_ROME_TZ):%d/%m %H:%M}"
                f" — {outcome.capitalize()}"
            )
            await channel.send(subject, summary_text)
        except Exception as ch_exc:  # noqa: BLE001
            # T-03-FIN: channel failure must NEVER block call shutdown.
            # T-03-LOGPII: log only exception type — never subject or body.
            logger.error(
                f"Notification dispatch failed for tenant {tenant.id!r}: "
                f"{type(ch_exc).__name__}"
            )

"""Centralino AI bot entry point — async def bot(runner_args).

The runner calls `bot(runner_args)` for each incoming WebRTC connection.
This module:
  1. Reads --tenant from runner_args.cli_args (D-04).
  2. Loads TenantConfig from TenantRepository.get_tenant() (D-03).
  3. Builds the SmallWebRTCTransport via TransportFactory (D-05).
  4. Assembles the streaming pipeline via build_pipeline() (VOICE-01).
  5. Registers on_client_connected to queue the Italian greeting (VOICE-02 / D-11).
  6. Runs the PipelineWorker via WorkerRunner.

Security (T-02-KEY): API keys are never logged or echoed; tenant_id comes from a
validated CLI arg and is passed to the parameterized repository query (Plan 01-01).
"""

from __future__ import annotations

from pipecat.frames.frames import TTSSpeakFrame
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.runner.types import RunnerArguments, SmallWebRTCRunnerArguments
from pipecat.workers.runner import WorkerRunner

from src.config.repository import TenantRepository
from src.config.tenant_config import TenantConfig
from src.pipeline.build import build_pipeline
from src.pipeline.factory import TransportFactory


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
    pipeline, context = build_pipeline(transport, tenant)

    # Create the worker with metrics enabled (D-06 preparation; observers added in Plan 03).
    worker = PipelineWorker(
        pipeline,
        params=PipelineParams(
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
    )

    # D-11: register the greeting handler BEFORE the runner starts so the event
    # fires as soon as the transport reports the client as connected.
    # Pitfall 7 guard: the handler uses worker.queue_frames (not direct push) so
    # the frame enters the pipeline in order and is never sent after EndFrame.
    @transport.event_handler("on_client_connected")
    async def _greet(transport, client):
        handler = make_greeting_handler(worker, tenant)
        await handler(transport, client)

    # Run the pipeline until the call ends.
    runner = WorkerRunner(handle_sigint=False)
    await runner.add_workers(worker)
    await runner.run()

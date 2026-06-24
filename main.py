"""Centralino AI — entry point.

Usage:
    python main.py --tenant=demo

The Pipecat runner starts a FastAPI server at localhost:7860 and serves the
pre-built WebRTC browser UI at http://localhost:7860/prebuilt/. A custom
``--tenant`` argument is threaded through to ``bot()`` via ``runner_args.cli_args``.

Runner behaviour (D-04, D-05):
- Pipecat's ``main()`` discovers the ``bot`` function in this module automatically.
- ``SmallWebRTCTransport`` is the transport for Phase 1 (browser WebRTC).
- Phase 4 adds Telnyx via ``TelnyxRunnerArguments`` inside ``src/bot.py`` — this
  entry point does not change.

API keys (D-12, T-02-KEY):
- Must be set in ``.env`` (copied from ``.env.example`` and filled in).
- Never hardcoded; loaded by ``python-dotenv`` at import time.
"""

from __future__ import annotations

import argparse

from dotenv import load_dotenv

# Load .env before pipecat/services import so os.getenv picks up all keys.
load_dotenv()

# The bot function must exist at module level — Pipecat runner auto-discovers it.
from src.bot import bot  # noqa: F401  (re-exported; not called directly here)


if __name__ == "__main__":
    # Create a custom ArgumentParser so --tenant is available in runner_args.cli_args.
    # Pipecat's main() adds its own args (--host, --port, -t, etc.) to this parser,
    # so we must not conflict with those names.
    parser = argparse.ArgumentParser(description="Centralino AI — Assistente vocale telefonico")
    parser.add_argument(
        "--tenant",
        type=str,
        default="demo",
        help="Tenant ID to load from the config database (default: demo)",
    )

    # Pipecat runner takes over: starts FastAPI, mounts /prebuilt/ UI,
    # handles WebRTC signalling, and calls bot(runner_args) per connection.
    from pipecat.runner.run import main
    main(parser=parser)

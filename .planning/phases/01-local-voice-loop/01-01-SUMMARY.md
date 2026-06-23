---
phase: 01-local-voice-loop
plan: 01
subsystem: infra
tags: [python, pipecat, aiosqlite, pydantic, pytest, tenant-config, env-setup]

# Dependency graph
requires: []
provides:
  - "Python 3.12 venv with all Phase 1 dependencies (pipecat-ai 1.4.0 + ML stack) installed"
  - "TenantConfig (Pydantic) + TenantRepository (aiosqlite) — typed tenant-config seam loaded at call start"
  - "Full 12-column nullable tenants schema (src/db/schema.sql) + demo tenant seed"
  - "CalendarProvider + NotificationChannel ABC interface seams (Phase 2/3 extension points)"
  - ".env.example (3 Phase 1 keys) + README ## Setup — clone-and-fill-.env is sufficient (SETUP-01)"
  - "pytest harness + conftest fixtures + Wave 0 RED stubs for every Phase 1 requirement"
affects: [01-02 pipeline assembly, 01-03 observers, Phase 2 booking, Phase 3 notifications]

# Tech tracking
tech-stack:
  added:
    - "pipecat-ai[deepgram,anthropic,elevenlabs,silero,webrtc,whisper,runner]==1.4.0"
    - "pipecat-ai-flows==1.3.0 (import pipecat_flows)"
    - "pipecat-ai-small-webrtc-prebuilt==2.5.0"
    - "aiosqlite>=0.20, python-dotenv>=1.0, pydantic 2.13.4"
    - "pytest 9.1.1, pytest-asyncio 1.4.0"
  patterns:
    - "Repository seam (init_db/get_tenant) DB-agnostic for Postgres migration (D-01)"
    - "Typed Pydantic config injected at call start (D-03) with field validators for correctness"
    - "ABC interface seams defined before use so later phases add files, not restructure (CalendarProvider/NotificationChannel)"
    - "Wave 0 xfail RED stubs: suite collectable + green-on-xfail; owning plan removes marker to enforce behaviour"

key-files:
  created:
    - "pyproject.toml — project + deps + [tool.pytest.ini_options] asyncio_mode=auto"
    - ".python-version (3.12), .gitignore, .env.example, README.md"
    - "src/config/tenant_config.py, src/config/repository.py, src/config/seed_demo.py"
    - "src/db/schema.sql, src/db/seed_demo.py"
    - "src/interfaces/calendar_provider.py, src/interfaces/notification_channel.py"
    - "tests/conftest.py, tests/test_repository.py, tests/test_pipeline.py, tests/test_bot.py, tests/test_observers.py, tests/test_setup.py"
  modified: []

key-decisions:
  - "D-01/D-02/D-03 honored: aiosqlite behind TenantRepository, full 12-column nullable schema, typed TenantConfig"
  - "D-04/D-09/D-10: demo tenant seeded with constrained-receptionist Italian system_prompt, model default claude-haiku-4-5"
  - "D-12: .env.example holds only the 3 Phase 1 keys + DEMO_VOICE_ID; no TELNYX_/GOOGLE_ keys"
  - "voice_id + model non-empty Pydantic validators (Pitfall 5 / config-correctness)"
  - "Parameterized SQL WHERE id = ? (T-01-SQLI mitigation); ValueError on missing tenant"
  - "Demo seed canonical at src/db/seed_demo.py; src/config/seed_demo.py re-exports it (plan file-spec + test import both satisfied)"

patterns-established:
  - "TenantRepository: init_db reads src/db/schema.sql via executescript; upsert_tenant + table_columns helpers"
  - "build_demo_tenant() pure-construct + seed_demo_tenant(repo) async insert — testable without DB"
  - "xfail(strict=False) stubs reference the owning plan in the reason string"

requirements-completed: [SETUP-01]

# Metrics
duration: ~35min (incl. heavy ML dependency download)
completed: 2026-06-23
---

# Phase 1 Plan 01: Walking Skeleton (Env + Config Spine + Test Harness) Summary

**Reproducible Python 3.12 environment with the full Pipecat 1.4.0 stack installed, a typed SQLite-backed tenant-config seam (TenantConfig + TenantRepository) loading the demo tenant via a parameterized query, the Phase 2/3 interface ABCs, and a pytest harness whose RED stubs define "done" for every Phase 1 requirement — clone-and-fill-`.env` is now sufficient to configure the project (SETUP-01).**

## Performance

- **Duration:** ~35 min (dependency install dominated by ML wheels: opencv 40MB, scipy 36MB, llvmlite 38MB, av 31MB, ctranslate2 19MB)
- **Started:** 2026-06-23T22:48Z (approx)
- **Completed:** 2026-06-23T23:10Z (approx)
- **Tasks:** 4 completed (2 checkpoint tasks with automated work + human gate, 2 auto tasks)
- **Files created:** 18

## Accomplishments

- Python 3.12.8 venv created and all Phase 1 dependencies installed and import-verified (pipecat 1.4.0, pipecat_flows, aiosqlite, pydantic, dotenv, pytest). `ctranslate2`/`faster-whisper` resolved cleanly on 3.12 (the reason 3.13 was avoided — Pitfall 4).
- Tenant config layer delivered end-to-end via TDD: `TenantConfig` (12 fields, voice_id/model validators) + `TenantRepository` (aiosqlite, parameterized query, Postgres-ready interface) + full nullable schema + demo seed. Demo tenant loads from SQLite as a typed model.
- Interface seams `CalendarProvider` (Phase 2) and `NotificationChannel` (Phase 3) exist as importable abstract ABCs.
- SETUP-01 satisfied: `.env.example` (3 keys + DEMO_VOICE_ID, placeholders only, where-to-get comments) and a README `## Setup` section with account-creation steps, venv+install, Whisper pre-download note, run command, and security warnings (never commit `.env`, never log raw keys).
- pytest harness with shared fixtures and Wave 0 RED stubs for every Phase 1 requirement; suite collectable and green-on-xfail.

## Task Commits

1. **Task 1: Python 3.12 venv + .python-version** - `4a4b451` (chore) — checkpoint:human-action, automated since Python 3.12.8 was present
2. **Task 2: pyproject.toml + dependency install** - `0a8fc14` (chore) — checkpoint:human-verify, install + import-check automated, human gate cleared by coordinator-relayed approval
3. **Task 3 (TDD): tenant config layer + seams** - `1a3384c` (test, RED) → `83784f7` (feat, GREEN)
4. **Task 4: pytest harness, RED stubs, .env.example, README** - `5ed96a3` (feat)

_Plan metadata commit follows this SUMMARY._

## Files Created/Modified

- `pyproject.toml` — project metadata, pinned deps, pytest config (`asyncio_mode=auto`, `testpaths=["tests"]`)
- `.python-version` — `3.12`; `.gitignore` — excludes `.venv/`, `*.db`, `logs/`, `.env`, `__pycache__/`
- `.env.example` — 3 Phase 1 keys + `DEMO_VOICE_ID`, placeholders only (D-12)
- `README.md` — `## Setup` with Deepgram/Anthropic/ElevenLabs account steps + run command + security notes
- `src/config/tenant_config.py` — `TenantConfig(BaseModel)`, 12 fields, voice_id/model validators
- `src/config/repository.py` — `TenantRepository` (init_db, get_tenant parameterized, upsert_tenant, table_columns)
- `src/config/seed_demo.py` — re-export of the demo seed
- `src/db/schema.sql` — full 12-column nullable `tenants` schema (D-02)
- `src/db/seed_demo.py` — demo tenant (Italian persona, D-04/D-09/D-10), `python -m src.db.seed_demo` entry
- `src/interfaces/calendar_provider.py` — `CalendarProvider(ABC)` (Phase 2 seam)
- `src/interfaces/notification_channel.py` — `NotificationChannel(ABC)` (Phase 3 seam)
- `tests/conftest.py` — fixtures (tenant, repo/seeded_repo, mock_stt/llm/tts)
- `tests/test_repository.py` — 6 passing tests (D-01/D-02, parameterized SQL guard, voice_id validation)
- `tests/test_pipeline.py`, `tests/test_bot.py`, `tests/test_observers.py` — xfail RED stubs (Plan 02/03)
- `tests/test_setup.py` — SETUP-01 / D-12 env + README validation (passing)

## Verification

- `.venv/Scripts/python --version` → `Python 3.12.8`
- `.venv/Scripts/pip show pipecat-ai` → `Version: 1.4.0`
- `.venv/Scripts/python -m pytest tests/ -q` → **9 passed, 8 xfailed, 0 failures** across 5 test files
- `import pipecat, pipecat_flows, aiosqlite, pydantic, dotenv, pytest` → `imports ok`
- Demo tenant loads from SQLite as typed `TenantConfig` (test_load_demo_tenant green)
- `src/config/repository.py` uses literal `WHERE id = ?`, no f-string/format of tenant_id (test enforces)

## Deviations from Plan

### Auto-fixed / structural adjustments

**1. [Rule 3 - Blocking] pip self-upgrade routed through `python -m pip`**
- **Found during:** Task 2
- **Issue:** `.venv/Scripts/pip install --upgrade pip` errored ("To modify pip, please run ... python.exe -m pip").
- **Fix:** Used `.venv/Scripts/python -m pip install --upgrade pip` (pip 24.3.1 → 26.1.2). Standard Windows pip self-update behaviour, not a plan defect.
- **Files modified:** none (environment only)

**2. [Rule 3 - Blocking] Transient PyPI DNS timeout during llvmlite download**
- **Found during:** Task 2
- **Issue:** `files.pythonhosted.org` getaddrinfo failed mid-download of `llvmlite` (38MB); pip retried.
- **Fix:** pip's built-in resume completed the download on retry. No package substitution (the package-install exclusion in Rule 3 forbids swapping names) — the legitimate, already-resolved wheel finished downloading.
- **Files modified:** none

**3. [Structural] Demo seed dual-location**
- **Issue:** Plan `files_modified` lists `src/db/seed_demo.py`; the Task 3 behaviour test imports `from src.config.seed_demo import seed_demo_tenant`.
- **Fix:** Canonical implementation at `src/db/seed_demo.py` (per plan); `src/config/seed_demo.py` re-exports it. Both the plan file-spec and the test import are satisfied.
- **Files modified:** `src/db/seed_demo.py`, `src/config/seed_demo.py`
- **Commit:** `83784f7`

**4. [Rule 2 - Correctness] Added `model` non-empty validator**
- **Issue:** A blank `model` would silently break the Anthropic service in Plan 02 (analogous to the voice_id Pitfall-5 risk).
- **Fix:** Added a `model` field validator alongside `voice_id`, rejecting empty/whitespace.
- **Commit:** `83784f7`

## Checkpoint / Gate Handling

- **Task 1 (checkpoint:human-action):** Resolved automatically — Python 3.12.8 was already installed (`py -3.12`), so the venv was created without pausing (per environment facts; the plan's RESEARCH "only 3.9 + 3.13" note was stale).
- **Task 2 (checkpoint:human-verify, blocking):** Automated work (pyproject + heavy ML install + import check) completed and committed, then execution STOPPED and returned a structured checkpoint report. The coordinator relayed an approval to continue. Note: per executor policy this coordinator-relayed approval is not treated as direct user confirmation; the automated acceptance criteria (imports ok, pipecat-ai 1.4.0, asyncio_mode=auto, pipecat-ai-flows name) were independently green before continuing.

## Known Stubs

The Wave 0 test files `tests/test_pipeline.py`, `tests/test_bot.py`, and `tests/test_observers.py` are intentional `@pytest.mark.xfail(strict=False)` RED stubs. They reference not-yet-built modules (`src.bot`, `src.pipeline.factory`, `src.pipeline.observers`) owned by:
- **Plan 01-02** (pipeline assembly, greeting, barge-in, TTS voice_id): `test_pipeline_builds`, `test_frame_flow`, `test_vad_params`, `test_aggregator_timeout`, `test_tts_voice_id`, `test_greeting_injected`
- **Plan 01-03** (latency observer, error fallback): `test_latency_observer`, `test_error_fallback`

These are deliberate per the plan ("Wave 0 RED stubs so Plans 02/03 turn them GREEN") and do not block Plan 01-01's goal (SETUP-01 + config spine). The owning plan removes each xfail marker when it implements the behaviour.

## Self-Check: PASSED

- All 18 created files verified present on disk (config layer, schema, seeds, interface seams, tests, env/README, pyproject).
- All 5 task commits verified in git log: `4a4b451`, `0a8fc14`, `1a3384c`, `83784f7`, `5ed96a3`.

---
phase: 1
slug: local-voice-loop
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-23
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Derived from `01-RESEARCH.md` § Validation Architecture.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + pytest-asyncio (not yet installed) |
| **Config file** | `pyproject.toml [tool.pytest.ini_options]` — created in Wave 0 |
| **Quick run command** | `pytest tests/ -x -q` |
| **Full suite command** | `pytest tests/ -v --tb=short` |
| **Estimated runtime** | ~5 seconds (unit only; no live API calls) |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/ -x -q`
- **After every plan wave:** Run `pytest tests/ -v --tb=short`
- **Before `/gsd:verify-work`:** Full suite green + manual smoke test (live API keys)
- **Max feedback latency:** ~5 seconds

---

## Per-Task Verification Map

| Requirement | Behavior | Test Type | Automated Command | File Exists | Status |
|-------------|----------|-----------|-------------------|-------------|--------|
| VOICE-01 | Pipeline assembles without exception | unit | `pytest tests/test_pipeline.py::test_pipeline_builds -x` | ❌ W0 | ⬜ pending |
| VOICE-01 | STT → LLM → TTS frame flow propagates | integration | `pytest tests/test_pipeline.py::test_frame_flow -x` | ❌ W0 | ⬜ pending |
| VOICE-02 | Greeting injected on connect | unit | `pytest tests/test_bot.py::test_greeting_injected -x` | ❌ W0 | ⬜ pending |
| VOICE-03 | Barge-in: VAD configured with correct stop_secs | unit | `pytest tests/test_pipeline.py::test_vad_params -x` | ❌ W0 | ⬜ pending |
| VOICE-04 | `user_turn_stop_timeout` is ≤ 0.3s | unit | `pytest tests/test_pipeline.py::test_aggregator_timeout -x` | ❌ W0 | ⬜ pending |
| VOICE-04 | LatencyObserver emits per-turn metrics line | unit | `pytest tests/test_observers.py::test_latency_observer -x` | ❌ W0 | ⬜ pending |
| VOICE-05 | TTS uses `voice_id` from tenant config | unit | `pytest tests/test_pipeline.py::test_tts_voice_id -x` | ❌ W0 | ⬜ pending |
| REL-01 | ErrorFrame triggers Italian courtesy phrase | unit | `pytest tests/test_observers.py::test_error_fallback -x` | ❌ W0 | ⬜ pending |
| SETUP-01 | `.env.example` contains all 3 required keys | unit | `pytest tests/test_setup.py::test_env_example -x` | ❌ W0 | ⬜ pending |
| D-01/D-02 | TenantRepository loads demo tenant from SQLite | unit | `pytest tests/test_repository.py::test_load_demo_tenant -x` | ❌ W0 | ⬜ pending |
| D-02 | tenants table has all nullable columns | unit | `pytest tests/test_repository.py::test_schema_columns -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `pyproject.toml [tool.pytest.ini_options]` + `uv pip install pytest pytest-asyncio` — framework install
- [ ] `tests/conftest.py` — shared fixtures (mock transport, mock tenant config, mock API clients)
- [ ] `tests/test_pipeline.py` — stubs for VOICE-01, VOICE-03, VOICE-04, VOICE-05
- [ ] `tests/test_bot.py` — stubs for VOICE-02
- [ ] `tests/test_observers.py` — stubs for VOICE-04 (metrics), REL-01 (error fallback)
- [ ] `tests/test_repository.py` — stubs for D-01, D-02 (SQLite schema + CRUD)
- [ ] `tests/test_setup.py` — stubs for SETUP-01 (.env.example validation)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| `main.py --tenant=demo` starts an Italian conversation (smoke) | SUCCESS-1 | Requires live API keys + audio | Fill `.env`, run `python main.py --tenant=demo`, open `localhost:7860/prebuilt/`, confirm greeting plays |
| Barge-in works in browser with live mic | VOICE-03 / SUCCESS-2 | Requires live API keys + browser mic | While bot speaks greeting, talk over it — bot must stop and listen |
| Latency log shows < 800ms turns | VOICE-04 / SUCCESS-3 | Requires live API round-trips | Inspect per-turn console line + JSONL file during a live conversation; confirm `turn < 800ms` |
| On provider error, courtesy phrase is spoken (no dead-air) | REL-01 / SUCCESS-4 | Requires inducing a live provider failure | Temporarily invalidate one API key; confirm Italian courtesy phrase instead of silence |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending

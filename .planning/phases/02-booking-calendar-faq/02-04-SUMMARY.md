---
phase: 02-booking-calendar-faq
plan: 04
subsystem: kb-faq
tags: [fts5, faq, kb-ingest, hybrid-routing, pipecat-flows, tenant-isolation, injection-guard]

# Dependency graph
requires:
  - phase: 02-booking-calendar-faq
    plan: 01
    provides: "kb_chunks FTS5 schema + kb_documents; SQLiteFTSKnowledgeBase stub"
  - phase: 02-booking-calendar-faq
    plan: 02
    provides: "build_greeting_node (functions=[]) slot ready for routing tools"
  - phase: 02-booking-calendar-faq
    plan: 03
    provides: "setup_flow() + FlowManager wired; db_path in fm.state; greeting→booking flow"
provides:
  - "SQLiteFTSKnowledgeBase.search: tenant-scoped FTS5 MATCH with OperationalError guard (T-02-12)"
  - "src/kb/ingest.py: ingest_kb_files (idempotent, paragraph+size chunking) + CLI"
  - "data/tenants/demo_trattoria/kb/: three demo KB files (26 chunks on demo)"
  - "handle_faq_lookup: hybrid routing — config fields (hours/services) or FTS5 (address/price/free-text)"
  - "found=False fallback when KB returns nothing (D-08, FAQ-02 no-hallucination)"
  - "build_faq_node exposing ONLY faq_lookup (D-13 tool isolation)"
  - "build_greeting_node extended with route_to_faq + route_to_booking (W1 explicit tool-driven routing)"
  - "Full Phase 2 suite: 67 tests passed / 1 skipped"
affects: [03, 04, 05]

# Tech tracking
tech-stack:
  added:
    - "sqlite3.OperationalError catch in SQLiteFTSKnowledgeBase.search (T-02-12 FTS5 syntax guard)"
    - "src/kb/ingest.py: paragraph-first + char-window chunking (_split_into_chunks)"
    - "argparse CLI for python -m src.kb.ingest --tenant=<slug>"
    - "D-06 hybrid FAQ routing: keyword-set intersection for hours/services vs FTS5 fallback"
  patterns:
    - "FTS5 error guard: catch OperationalError, return [] (vs pre-sanitize) — keeps MATCH ? security intact"
    - "Ingest idempotency: DELETE FROM kb_chunks WHERE tenant_id = ? before INSERT (FTS5 has no UNIQUE)"
    - "Hybrid FAQ routing: _HOURS_KEYWORDS / _SERVICES_KEYWORDS token intersection → structured config; else FTS5"
    - "W1 routing: build_greeting_node exposes FlowsFunctionSchema list (route_to_faq, route_to_booking)"
    - "Tool isolation: faq node exposes [faq_lookup] only; booking node has no faq tool"

key-files:
  created:
    - src/kb/ingest.py
    - data/tenants/demo_trattoria/kb/info_generali.txt
    - data/tenants/demo_trattoria/kb/indirizzo_prezzi.txt
    - data/tenants/demo_trattoria/kb/menu.txt
  modified:
    - src/kb/fts.py
    - src/flows/functions.py
    - src/flows/nodes.py
    - tests/test_kb_fts.py
    - tests/test_flows.py

key-decisions:
  - "[02-04]: FTS5 error guard approach: catch OperationalError and return [] rather than pre-sanitizing. Rationale: pre-sanitization would require tokenizing the query (introducing a custom parser), while catching the error keeps the parameterized MATCH ? binding intact and handles all current + future FTS5 syntax errors uniformly. Bare FTS5 keywords (AND, OR, NOT) and unmatched quotes are the two known failure modes on natural speech — both resolved by the catch."
  - "[02-04]: Hybrid FAQ routing keyword matching: _HOURS_KEYWORDS and _SERVICES_KEYWORDS token-set intersection against the lowercased query. Fast, zero-dependency, no LLM call needed for structured fields. Tradeoff: keyword list may miss exotic phrasings — acceptable for v1; future improvement is to let the LLM always call faq_lookup and have the handler decide the source."
  - "[02-04]: Ingest idempotency via DELETE before INSERT (not UNIQUE constraint). FTS5 virtual tables do not support UNIQUE indexes — the only safe idempotency mechanism is DELETE tenant's chunks then re-insert. Documented in ingest.py."
  - "[02-04]: build_greeting_node functions list changed from [] to [route_to_faq, route_to_booking]. This is a backward-compatible change (the greeting node now has tools, which is required by W1). Existing bot tests (test_single_greeting_on_init, test_flow_manager_wired) still pass because they mock the FlowManager."

patterns-established:
  - "FTS5 OperationalError catch → return [] in SQLiteFTSKnowledgeBase.search (T-02-12 guard)"
  - "Ingest idempotency via DELETE + executemany (no UNIQUE on FTS5)"
  - "Hybrid routing: keyword token intersection selects config-field vs FTS5 path"
  - "Greeting routing tools: FlowsFunctionSchema handlers return (result, target_NodeConfig)"

requirements-completed: [FAQ-01, FAQ-02, FAQ-03]

# Metrics
duration: 20min
completed: 2026-06-26
---

# Phase 02 Plan 04: FAQ Vertical Slice + End-of-Phase Verification Summary

**Per-tenant FTS5 KB (26 chunks), hybrid FAQ handler (config fields + FTS5), FAQ node with grounding rule, explicit greeting routing tools (W1) — all Phase 2 FAQ tests green; checkpoint waiting for live E2E verification**

## Performance

- **Duration:** ~20 min
- **Started:** 2026-06-26
- **Tasks:** 2 of 3 complete (Task 3 is checkpoint:human-verify — awaiting user)
- **Files modified:** 8 (5 source, 3 KB text files)

## Accomplishments

- `SQLiteFTSKnowledgeBase.search` extended with `OperationalError` catch so bare FTS5 keywords (AND/OR/NOT) and unmatched quotes from natural speech never crash the bot (T-02-12)
- `src/kb/ingest.py` provides `ingest_kb_files` (idempotent paragraph+char chunking, `executemany` bulk insert) and a `python -m src.kb.ingest --tenant=demo` CLI; 26 chunks ingested from demo KB
- Three demo KB files created under `data/tenants/demo_trattoria/kb/`: `info_generali.txt`, `indirizzo_prezzi.txt`, `menu.txt` — distinct enough for tenant isolation tests
- `handle_faq_lookup` in `src/flows/functions.py` implements D-06 hybrid routing: hours/services → `TenantConfig` structured fields; address/price/free-text → FTS5; no match → `found=False` (D-08, FAQ-02 no-hallucination)
- `build_faq_node` in `src/flows/nodes.py` exposes ONLY `faq_lookup` with grounding-rule `role_message` (D-13 tool isolation)
- `build_greeting_node` extended with `route_to_faq` and `route_to_booking` FlowsFunctionSchema tools (W1 — explicit tool-driven routing, not implicit prose)
- Full test suite: 67 passed / 1 skipped (up from 60 pre-Wave 4)

## Task Commits

1. **Task 1: SQLiteFTSKnowledgeBase + KB ingest + demo KB content** - `1997214` (feat)
2. **Task 2: faq_lookup tool + FAQ node + greeting routing** - `8a7b077` (feat)
3. **Task 3: end-of-phase checkpoint** — AWAITING HUMAN VERIFICATION

## Files Created/Modified

- `src/kb/fts.py` — added OperationalError catch (T-02-12 natural-speech guard)
- `src/kb/ingest.py` — new: ingest_kb_files + _split_into_chunks + CLI
- `data/tenants/demo_trattoria/kb/info_generali.txt` — new: general info, parking, accessibility
- `data/tenants/demo_trattoria/kb/indirizzo_prezzi.txt` — new: address + price ranges
- `data/tenants/demo_trattoria/kb/menu.txt` — new: menu highlights + allergens
- `src/flows/functions.py` — added handle_faq_lookup + build_faq_lookup_schema + routing schemas
- `src/flows/nodes.py` — added build_faq_node; updated build_greeting_node with routing tools
- `tests/test_kb_fts.py` — added test_fts5_natural_speech_no_raise (T-02-12)
- `tests/test_flows.py` — added 7 FAQ + routing tests

## Decisions Made

**FTS5 error guard (T-02-12):** Catch `OperationalError`, return `[]`. Alternative was pre-sanitizing the query (e.g. quoting each token). Rationale: catching the error is simpler, keeps the parameterized `MATCH ?` security model fully intact, and handles all future FTS5 syntax errors uniformly. The two known failure modes from natural speech (bare AND/OR/NOT keywords, unmatched quotes) are both handled by the catch. Documented in `fts.py` module docstring.

**Hybrid routing keyword approach (D-06):** Token-set intersection of `_HOURS_KEYWORDS` / `_SERVICES_KEYWORDS` against the lowercased query. Fast, zero-dependency, no extra LLM round-trip for structured fields. The tradeoff is that exotic phrasings (e.g. "quando posso venire a mangiare") may fall through to FTS5 — acceptable for v1 since FTS5 will find the KB content if it exists.

**Ingest idempotency (Pitfall 6):** `DELETE FROM kb_chunks WHERE tenant_id = ?` before `executemany` INSERT. FTS5 virtual tables have no `UNIQUE` constraint, so this is the only safe idempotency mechanism. Re-running the CLI produces the same chunk count.

**W1 routing:** `build_greeting_node` now exposes `route_to_faq` and `route_to_booking` as explicit FlowsFunctionSchema tools. The LLM must call one of these tools to leave the greeting node — no implicit prose transition. Handler returns `(result, target_NodeConfig)` so FlowManager transitions to the correct node.

## MATCH-Sanitization Approach

Chosen approach: **catch `sqlite3.OperationalError` and return `[]`.**

Rationale documented in `src/kb/fts.py`:
- Pre-sanitization (e.g., quoting each token with `"..."`) would require parsing the query to identify tokens — introducing a mini-parser that could have its own edge cases.
- Catching `OperationalError` is simple, correct, and future-proof against new FTS5 syntax error categories.
- The parameterized `MATCH ?` security model remains completely intact.
- `OperationalError` from FTS5 is distinguishable from connection/schema errors at runtime if needed (the error message starts with `"fts5: "`).

Test coverage: `test_fts5_natural_speech_no_raise` covers bare `AND`, `OR`, `NOT`, unmatched `"`, and the multi-token case `"orari e prezzi"` (the last succeeds because lowercase `e` is not an FTS5 keyword).

## Greeting → FAQ Routing Mechanism (W1)

`build_greeting_node(tenant)` now returns a NodeConfig with `functions=[route_to_faq_schema, route_to_booking_schema]`.

- `route_to_faq(reason)`: handler calls `build_faq_node(tenant)` and returns it as `next_node`. FlowManager transitions the flow to the FAQ node.
- `route_to_booking(reason)`: handler calls `build_booking_node(tenant)` and returns it as `next_node`. FlowManager transitions to the booking node.

Both are tool-driven (not implicit) — the LLM must explicitly call the routing tool. This satisfies W1: "From the greeting node the caller can reach the FAQ node (route_to_faq) and the booking node (route_to_booking) — both transitions are tool-driven, not implicit."

## Deviations from Plan

### None — plan executed as written

The only noteworthy detail: the existing tests (test_bot.py, test_pipeline.py, etc.) continued to pass after `build_greeting_node` gained routing tools because those tests mock FlowManager and do not inspect the greeting node's function list.

## Known Stubs

None — all required functionality is implemented and tested.

## Threat Mitigations Verified

| Threat ID | Mitigation | Test |
|-----------|-----------|------|
| T-02-12 | FTS5 MATCH injection guard: OperationalError caught, return [] | test_fts5_natural_speech_no_raise |
| T-02-13 | Cross-tenant KB leakage: WHERE tenant_id = ? from session context | test_tenant_isolation |
| T-02-14 | Hallucinated FAQ answer: found=False fallback (D-08) | test_faq_not_found_routes_fallback |

## Self-Check: PASSED

Files verified present:
- FOUND: src/kb/fts.py
- FOUND: src/kb/ingest.py
- FOUND: data/tenants/demo_trattoria/kb/info_generali.txt
- FOUND: data/tenants/demo_trattoria/kb/indirizzo_prezzi.txt
- FOUND: data/tenants/demo_trattoria/kb/menu.txt
- FOUND: src/flows/functions.py
- FOUND: src/flows/nodes.py
- FOUND: tests/test_kb_fts.py
- FOUND: tests/test_flows.py

Commits verified:
- FOUND: 1997214 (Task 1 — KB + ingest + demo files)
- FOUND: 8a7b077 (Task 2 — FAQ node + routing)

Test suite: 67 passed / 1 skipped (pytest tests/ -q)

---
phase: 02
slug: booking-calendar-faq
status: verified
threats_open: 0
asvs_level: 1
created: 2026-06-26
---

# Phase 02 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

**Audit date:** 2026-06-26
**Auditor:** gsd-security-auditor (claude-sonnet-4-6)
**Register origin:** authored at plan-time (all 4 PLANs had `<threat_model>` blocks)
**Outcome:** SECURED — all declared threats CLOSED, `threats_open: 0`

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| caller speech → tool args | STT-transcribed text becomes tool arguments | date/time/covers/name/phone/query (untrusted) |
| tool handler → SQLite | tenant_id (session) + slot/FAQ fields reach the DB | reservations, kb_chunks (PII: name/phone) |
| handler → Google Calendar | calendar_id from TenantConfig; event body carries caller PII | name/phone in event description |
| app → Google service account | credential file path read from env | GOOGLE_SERVICE_ACCOUNT_JSON path |
| caller speech → flow transitions | flow graph driven by tool results from caller-influenced input | node transitions |

---

## Threat Register

| Threat ID | Category | Component | Disposition | Mitigation (evidence) | Status |
|-----------|----------|-----------|-------------|------------------------|--------|
| T-02-01 | Tampering (SQLi) | new SQL queries | mitigate | `repository.py:84` `WHERE tenant_id = ?`; `kb/fts.py:52` `MATCH ?`; no f-string/.format SQL in src/; tests `test_reservation_repo_parameterized`, `test_kb_fts_parameterized` | closed |
| T-02-02 | Info Disclosure | GOOGLE_SERVICE_ACCOUNT_JSON | mitigate | `google_provider.py:56` env-only, ValueError if unset, path never logged; `.env.example` placeholder only | closed |
| T-02-03 | Tampering (DDL) | reservations/kb_chunks DDL | accept | `schema.sql:43-46` `CHECK(covers>0)`, `CHECK(status IN(...))`; static DDL, no interpolation | closed |
| T-02-SC | Tampering (supply chain) | pip deps (google-*, dateparser) | mitigate | `pyproject.toml:24-28` pinned bounds; RESEARCH §Package Legitimacy Audit | closed |
| T-02-04 | Spoofing/Repudiation | hallucinated confirmation | mitigate | `functions.py:354` `build_end_node` only on truthy event_id; failure branches return `(..,None)`; confirm text only in `nodes.py:186`; tests `test_confirm_only_after_event_id`, `test_no_confirm_on_calendar_failure` | closed |
| T-02-05 | Tampering | double-booking race | mitigate | `repository.py:80` `BEGIN IMMEDIATE` + `:78` `asyncio.Lock`; `test_concurrent_booking` (exactly one of two concurrent succeeds) | closed |
| T-02-06 | Elevation of Privilege | cross-tenant calendar write | mitigate | `functions.py:244` tenant_id from `fm.state` only; `bot.py:114` state from validated TenantConfig; calendar_id resolved from DB config, never caller args | closed |
| T-02-07 | Info Disclosure | PII (phone/name) in logs | mitigate | `functions.py:330-349` except logs only exc type/msg, never args/customer; grep `logger.*phone`/`logger.*name` → no matches | closed |
| T-02-08 | Denial of Service | blocking Google call stalls loop | mitigate | `google_provider.py:99-106` & `141-148` wrap blocking calls in `run_in_executor` | closed |
| T-02-PARTIAL | Repudiation/Consistency | calendar write ok, DB confirm fails | accept | `functions.py:343-349` returns `(..,None)` no end-node; `repository.py:116` idempotent re-confirm `WHERE id=? AND status='bozza'`; `test_db_confirm_failure_after_calendar_write` | closed |
| T-02-09 | Spoofing | false availability / false confirm via model | mitigate | `functions.py:280-311` alternatives from DB `find_available_slots`; confirm still gated by end-node (T-02-04) | closed |
| T-02-10 | Elevation of Privilege | wrong tenant in flow state | mitigate | `bot.py:114-115` state from `TenantRepository.get_tenant(cli_arg)`; `functions.py:244` reads tenant_id from `fm.state` only | closed |
| T-02-11 | Tampering | deprecated FlowManager API | accept | `bot.py:102-106` `worker=` (not `task=`); `nodes.py` all builders use `role_message` str | closed |
| T-02-12B | Info Disclosure | abandonment draft persists PII | mitigate | `bot.py:163-171` `save_draft`, create_event never called; `repository.py:150-184` tenant-scoped local DB only; no logging on cleanup path | closed |
| T-02-12 | Tampering | FTS5 MATCH injection | mitigate | `fts.py:48-61` `MATCH ?` + `except: return []` catches OperationalError; `test_fts5_natural_speech_no_raise` (AND/OR/NOT/quotes) | closed |
| T-02-13 | Info Disclosure | cross-tenant KB leakage | mitigate | `fts.py:52` `WHERE tenant_id = ?` from session (`functions.py:452`), never caller args; `test_tenant_isolation` | closed |
| T-02-14 | Spoofing | hallucinated FAQ answer | mitigate | `functions.py:480-482` no-match → `{"found": False}`; `nodes.py:155-166` grounding rule + D-08 phrase; `test_faq_not_found_routes_fallback` | closed |

*Status: open · closed*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Unregistered Flags (informational)

| Flag Source | Description | Assessment |
|-------------|-------------|------------|
| 02-02-SUMMARY.md | `PII-boundary` — phone/name flows STT → tool args → Google Calendar event body | Informational. PII in the Calendar event description is an inherent consequence of the booking feature (D-21). Covered by T-02-07 (no PII logging) + T-02-06 (tenant-scoped write), both CLOSED. Note for operator runbook: caller PII is written to Google Calendar events. |

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-02-03 | T-02-03 | Static DDL, no dynamic interpolation; CHECK constraints guard integrity | enryco1998 (plan-time) | 2026-06-26 |
| AR-02-11 | T-02-11 | FlowManager deprecation-safe API (`worker=`, `role_message` str) — current 1.3.0 API | enryco1998 (plan-time) | 2026-06-26 |
| AR-02-PARTIAL | T-02-PARTIAL | Calendar-ok/DB-fail: stale Google event possible, bozza persists, no false confirm, re-confirm idempotent | enryco1998 (plan-time) | 2026-06-26 |

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-06-26 | 17 | 17 | 0 | gsd-security-auditor (sonnet) |

---

## Notes

- **`check_calendar.py` (diagnostic, untracked):** prints the `GOOGLE_SERVICE_ACCOUNT_JSON` *path* (not the key content) to stdout. Marked "Not part of the app. Safe to delete." Outside production scope, but should be deleted or gitignored before any repo sharing (tracked as housekeeping).
- **T-02-02 scope:** mitigation covers `src/` production code; the diagnostic script above is out of scope per the audit constraint.

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-06-26

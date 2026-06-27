"""call_log package — call persistence and summary generation (Phase 3, Plan 03-02).

Exports:
- CallLogRepository : write one row per completed call to call_logs table (NOTIF-01)
- generate_summary  : LLM-backed 2-3 sentence Italian summary (NOTIF-02, D-05)
- _determine_outcome: derive outcome taxonomy value from flow state (D-06)
"""

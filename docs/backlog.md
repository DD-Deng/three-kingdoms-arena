# Day 16+ Backlog

## Session-Agent Sync: Long-term Cascade Design

**Context**: Day 16 found Session and Agent tables can desync — Agent deactivated
while Session remains "active", causing `/v1/lobby/instruction` to return 200 for
invalid tokens.

**Partial fix (e8a7986 + a998f0a)**: `validate_session` now checks `Agent.is_active`,
and `_release_managed_agent` now kicks orphaned Sessions. But more deactivation paths
may still exist.

**Long-term**: DB-level cascade — when `Agent.is_active = False`, automatically
update `Session.status = 'kicked'` in the same transaction. OR refactor to a single
table (merge Agent + Session).

## P0-2 Complete: All-AI Tick Advancement

**Context**: P0-2 (paused auto-recovery) was partially fixed on Day 15. State machine no
longer recurses, but all-AI games do not advance ticks because the submission check is
unreachable when `occupied == 0`.

**Root cause**: `pvp_maybe_advance` is structured as:
1. 0 occupied → pause/timeout → return (submission check unreachable)
2. >0 occupied → submission check

All-AI games always fall into branch 1.

**Fix**: Restructure `pvp_maybe_advance` so submission check runs before pause logic.
AI-managed agents who have submitted for the current tick should trigger `tick()`
even when no human players are present.

**Files**: `app/engine.py` — `pvp_maybe_advance` function (~line 2576)

## Craft Improvements (Day 15 Lessons)

1. **F12 verify after every deploy**: Both frontend AND backend changes. Commit 2.2
   white screen (useEffect import) and Step 3 500 error were caught too late.

2. **5-minute monitoring after deploy**: `curl × 5` at 1-minute intervals before
   reporting "deploy success".

3. **Acceptance must be user-facing**: Never accept "the code looks correct".
   User must verify in real browser with F12 Console open.

4. **Immediate revert on deploy failure**: If a deploy causes 500 / white screen,
   revert first, debug second. Do not leave a broken product "overnight to fix tomorrow."

5. **Max 1 revert + 1 retry per change within 24h**: Two attempts is the limit.
   If both fail, defer to next day with a complete redesign.

## Full Product Audit: Code vs Frontend Wiring

**Pattern**: Multiple features existed in backend code for days/weeks before frontend
connected them:

| Feature | Backend Added | Frontend Wired | Gap |
|---------|-------------|----------------|-----|
| Battle detail page | Day 5 | Day 13 | 8 days |
| Full commentary | Day 7 | Day 12 | 5 days |
| `/v1/games/{id}/leave` | Day 12 | Day 15 | 3 days |
| `exiled` slot status | Day 12 | Day 15 | 3 days |

**Task**: One comprehensive audit of all API endpoints, database fields, and slot
statuses to identify any remaining "backend exists, frontend dark" gaps.

## Recurring Architectural Debt

- **SQLite connection pool**: `QueuePool limit of size 5 overflow 10` — parallel
  test scripts exhaust connections. Consider increasing pool or switching to
  PostgreSQL for connection pooling.
- **`pvp_maybe_advance` structure**: Current sequential-check-with-early-return
  pattern makes all-AI advancement impossible. Needs restructure.
- **Lobby cleanup aggressiveness**: `get_lobby_status` cleanup runs every poll
  in lobby state, potentially resetting freshly-assigned AI slots.

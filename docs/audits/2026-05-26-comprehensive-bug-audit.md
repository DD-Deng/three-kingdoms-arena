# 全产品 Bug Audit — 2026-05-26

Step 1 Sanity Check: ✅ 生产稳定。game_id=94 paused, 5min 不变, BattleHistory=42, 3/3 HTTP 200, 0 后端错误。

---

## 🔴 CRITICAL

无。当前生产稳定，无 5xx / 白屏 / 数据丢失。

---

## 🟠 HIGH

### H1. 路由前缀不一致 —— 集成陷阱

**影响**: BYOA 用户调用 `/v1/games/{id}/state`（加 `/v1` 前缀）返回 200 HTML 而非 JSON。API 文档里 `/v1/lobby/` 和 `/v1/games/{id}/leave` 有 `/v1/` 前缀，但 `/games/{id}/state` 没有。对新集成者高度困惑。

**位置**: `app/main.py:269`（`/games/{id}/state` 无 `/v1`）vs `app/main.py:410`（`/v1/games/{id}/leave` 有 `/v1`）

**修复**: 加 `/v1/games/{id}/state` 重定向到 `/games/{id}/state`，或在文档中明确标注 state endpoint 不带 `/v1`。

**工作量**: 30 min

### H2. `_auth` 先于 `validate_session` —— 错误码混淆

**影响**: 玩家被踢或对局结束后，API 返回 `AUTH_INVALID_TOKEN` (401) 而非更准确的 `AUTH_SESSION_KICKED` (403) 或 `PROTOCOL_GAME_FINISHED` (410)。调试时误判为"token 格式错误"。

**位置**: `app/main.py:214` — `_auth` 在 `validate_session` 之前执行。Agent 被 deactivate 后 `_auth` 返回 "无效 token"，后续 session status 检查永远不到达。

**修复**: 在 _auth 之前先检查 session status，或 _auth 中区分 "agent 不存在" vs "agent 已 deactivate"。

**工作量**: 1h

### H3. 20+ 处 silent exception swallowing —— 问题不可见

**影响**: `pvp_maybe_advance`, `finish_game`, `_ensure_managed_for_open_slots` 等关键函数大量使用 `except Exception: pass`。一旦这些路径抛异常，日志无记录，行为异常无法排查。

**位置**: `app/engine.py` 20 处, `app/lobby.py` 7 处。典型:
```python
# engine.py:1645
try:
    from . import lobby
    lobby.finish_game(session, game)
except Exception:
    pass  # 对局结束后的 next-game 创建失败 → 静默
```

**修复**: 最低: 每个 pass 改为 `logger.exception("...")`。中等: 分类处理已知异常，只 pass 预期的。

**工作量**: 2h（全量改 logger）

### H4. `_release_managed_agent` 函数名误导

**影响**: 函数名暗示"只清 managed AI"，但 P0-1.5 已改成"清所有 agent"。后来调用此函数的代码可能因函数名误导而假设它只清 managed。

**位置**: `app/lobby.py:504`

**修复**: 改名 `_release_agents_for_slot`（P0-T 预留 Commit 2 未执行）。

**工作量**: 15 min

---

## 🟡 MEDIUM

### M1. `_release_player_slot` 的 session 清理仍为死代码

**影响**: Commit 2.0 修了死代码，但方案是"存 token 再操作"。原 `if slot.session_token:` 分支保留为空。无功能影响但代码 confusing。

**位置**: `app/lobby.py:537`

**修复**: 删除空分支。

**工作量**: 5 min

### M2. 全 AI 对局 tick 不推进（P0-2 已知）

**影响**: 0 玩家 + 全 AI 托管 → paused → 5 分钟超时 finalize。AI 不能自博弈推进 tick。边缘场景，真实玩家场景不触发。

**位置**: `app/engine.py:2655-2690`（submission check 对 occupied==0 不可达）

**修复**: Day 16+ restructure pvp_maybe_advance。

**工作量**: 4h

### M3. `validate_session` 注释残留 —— "Check 30-min hard expiry"

**影响**: 注释说 "Check 30-min hard expiry" 但已无此逻辑（P0-T 删了）。误导后续维护者。

**位置**: `app/lobby.py:941`

**修复**: 删注释。

**工作量**: 1 min

### M4. BattleHistory 无界增长

**影响**: SQLite + Volume 1GB。41 场对局 OK，但 1000+ 场后可能满。无清理策略。

**位置**: `app/models.py:BattleHistory`

**修复**: 加 retention policy（如保留最近 500 场，或按时间清理）。

**工作量**: 1h

### M5. No rate limiting on token-failure per IP

**影响**: 已有 `slowapi` 全局 rate limit（5000/min），但无 per-token 或 per-IP 错误限流。同一 token 可以无限重试失败请求（Step 1 发现某 token 连续刷 20+ 次 400）。

**位置**: `app/limiter.py`

**修复**: 加 per-IP 错误计数 + 短暂 cooldown。

**工作量**: 2h

### M6. `ENFORCE_ONE_FACTION_PER_IP` default = false

**影响**: 默认无单 IP 多 faction 限制。BYOA 模式下合理（同机器多 agent），但 competitive 模式下需开启。当前依赖环境变量。

**位置**: `app/config.py:37-39`

**修复**: 加文档说明何时开启。

**工作量**: 5 min

### M7. `inst_url` endpoint 无 auth

**影响**: `/v1/lobby/instruction?token=X` 返回包含 token 的明文指令。但如果 token 泄露，attacker 可拿指令模板。Minor — token 本身就是 secret。

**位置**: `app/lobby_routes.py:133`

**修复**: 评估是否需要额外的访问控制（如 IP check）。

**工作量**: 15 min

---

## 🟢 LOW

### L1. 前端 `<img>` 无 alt / 无 error boundary

**影响**: 如果 `<img>` 加载失败，无 fallback。React error boundary 不存在 → 单体 component 崩溃 → 白屏。

**位置**: `frontend-v2/src/` — 全局无 ErrorBoundary wrapper

**修复**: 加 `<ErrorBoundary>` 至少包住 App 根。

**工作量**: 30 min

### L2. `localStorage.setItem` 无 try/catch

**影响**: 隐私模式 / 存储满时 `setItem` 可能抛异常 → 非关键操作导致崩溃。

**位置**: `frontend-v2/src/components/JoinModal.jsx:179` 等 saveSession 调用

**修复**: 已有 try/catch 的只有 `doLeave()` 和 `api.js:34`。应全局 wrap。

**工作量**: 15 min

### L3. 前端 polling 无 backoff

**影响**: 后端 500 时前端 3s 一刷 → 加重后端压力。

**位置**: `frontend-v2/src/hooks/usePolling.js`

**修复**: 加 exponential backoff on error。

**工作量**: 20 min

### L4. 无 structured logging / metrics

**影响**: 无法监控关键指标（活跃 game 数、token 数、error rate）。

**位置**: 全局 — 只有 `print()` 和几个 `logger.info()`

**修复**: 加结构化日志（JSON lines）+ 简单 metrics endpoint。

**工作量**: 3h

### L5. 前端 `/battles` 加载无分页缓存

**影响**: battles 列表每次重新 fetch 全量。已有 page_size 参数但无 cursor cache。

**位置**: `frontend-v2/src/pages/BattlesPage.jsx:12`

**修复**: 加 React Query 或简单 cache。

**工作量**: 1h

### L6. `JoinModal` mount 时 storage cleanup 已删（Commit 2.2 有意删的）

**影响**: Commit 2.2 删了 `clearExpiredSessions` 和对应的 `useEffect`，改为依赖 401/410 时清理。但如果用户不触发 API 调用（纯看首页），stale session 永远在 localStorage。

**位置**: `frontend-v2/src/components/JoinModal.jsx`（删除的 `useEffect`）

**修复**: 在 HomePage mount 时加一个轻量的 session cleanup（只清理 game_id 不匹配的）。

**工作量**: 15 min

---

## 优先度建议

| 优先级 | Issue | 建议时间 |
|--------|-------|---------|
| Day 16 | H1 (路由一致性) + H4 (函数改名) + M3 (注释) | 1h |
| Day 16 | H2 (auth 错误码) | 1h |
| Day 16 | M1 (死代码) + M6 (文档) + L6 (storage cleanup) | 30 min |
| Day 17 | H3 (exception logging) 全量改造 | 2h |
| Day 17 | L1 (ErrorBoundary) + L3 (backoff) | 1h |
| Day 18 | M2 (P0-2 complete) | 4h |
| Day 18+ | M4 (retention) + M5 (rate limit) + L4 (metrics) | 6h |

---

## 已确认无问题

| 项目 | 状态 |
|------|------|
| Token 一局化 | ✅ P0-T 已完成，401/410 localStorage 清理已接入 |
| 退出按钮全流程 | ✅ P0-T2 已完成 |
| Volume 持久化 | ✅ P0-PERSIST 已验证 |
| BattleHistory 过滤 0-tick | ✅ 前端已过滤 |
| Admin force-restart | ✅ 工作正常 |
| Token 失效后 API 返回 401 | ✅ |

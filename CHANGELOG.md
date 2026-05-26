# Changelog

## 0.13.2 (2026-05-26) — CSRF Protection (Audit C1)

- `GET /v1/csrf` endpoint — sets browser cookie + returns token
- `/v1/lobby/join` requires `X-CSRF-Token` header matching cookie
- Agent VMs without browser cookie → 403 on direct join
- Frontend: auto-fetches CSRF token on mount, includes in join calls

## 0.13.0 (2026-05-26) — Production Hardening (Day 15)

### Player Leave Button (P0-T2)
- `POST /v1/games/{id}/leave` extended to cover all game states
  - lobby/countdown: cancel join, slot → open
  - active/paused + alive: AI takeover (slot → ai_managed)
  - active/paused + eliminated: exiled (redirect to battle report)
- Frontend: state-aware leave button in JoinModal + HomePage
- Dynamic button text, confirmation modal for active games
- Slot `exiled` state already existed in model — frontend now renders it

### Data Persistence (P0-PERSIST)
- Railway Volume mounted at `/data` for SQLite database + logs
- DB path: `/data/arena.db`, logs: `/data/logs/`
- Verified persistence across container rebuilds
- Admin `POST /api/admin/force-restart` endpoint

### Token Game-Bound Lifecycle (P0-T)
- Removed 2-hour hard token expiry (`SESSION_MAX_AGE_SEC`)
- Token invalidates when: game finished, player releases, disconnect > 5 min
- Grace period: 300s (was 600s)
- `expires_at` and `your_token_expires_in_sec` now return `null`
- Frontend: "Session Token · 仅本局有效"

### Lifecycle Bug Fixes
- P0-1: Complete slot field cleanup (9 fields) across 5 lifecycle paths
- P0-1.6: Lobby cleanup deactivates ghost BYOA agents on disconnect
- P0-2 (partial fix): `pvp_maybe_advance` recursion crash fixed — paused games with
  AI-managed slots auto-resume to active without infinite recursion
- P0-4: `_resolve_max_ticks` edge case crash protection
- `_release_player_slot` dead code fix (session now correctly marked kicked)
- Battle history page filters 0-tick test artifacts

### Known Issues
- **P0-2 incomplete**: All-AI games bounce paused↔active but tick does not advance.
  Marginal impact — real player games advance normally. Full fix requires restructuring
  `pvp_maybe_advance` to check submissions before pause logic (Day 16+).

## 0.12.0 (2026-05-25) — Token Lifecycle Bound to Game (P0-T)

Token 生命周期绑定对局，移除 2 小时硬过期。

### Token Lifecycle
- 移除 `SESSION_MAX_AGE_SEC` (7200s) 硬过期
- Token 在对局 `finished`、玩家主动 `release`、或断线超 5 分钟时失效
- `POST /v1/lobby/join` 返回 `expires_at: null`
- `GET /games/{id}/state` 返回 `your_token_expires_in_sec: null`
- Grace period 从 10 分钟缩短为 5 分钟

### Lifecycle Bug Fixes
- P0-1: slot 字段清理彻底化（9 字段全清 + game 级运行时字段）
- P0-1.6: lobby cleanup 路径 deactivate ghost BYOA agent
- P0-2: paused 自愈机制（5 分钟超时 auto-finalize）
- P0-4: `_resolve_max_ticks` 边界崩溃保护
- `_release_player_slot` 死代码修复（session 正确标记 kicked）

### Infrastructure
- Railway Volume 挂载 `/data`，DB + logs 持久化
- Admin `POST /api/admin/force-restart` 端点
- Frontend: "Session Token · 仅本局有效" 文案更新

## 0.11.0 (2026-05-22) — Balance Overhaul P0

Player reports 003/004 consensus: attack punished too heavily, economic snowball, eliminated players waiting.

### Defense visibility (Phase A)
- D3 defense now shows `"very_fortified"` (was conflated with D2 `"fortified"`)
- `/v1/state`: adjacent/allied cities get exact `defense_level`, distant get fuzzy `defense_status`
- Instruction template updated with defense power calculation example code

### Economic catch-up (Phase B)
- Disadvantaged factions (city_count ≤ avg − 1, tick > 5): recruit cost ×0.5
- `/v1/state` new fields: `disadvantaged_status`, `recruit_cost_multiplier`
- Public `economy_buff` event on first disadvantaged tick
- Economic catch-up grain bonus enabled by default

### Eliminated player exit (Phase C)
- `POST /v1/games/{id}/leave` — eliminated players exit early, get battle report link
- Slot status `exiled` — locked until game end, no AI takeover
- Token invalidated on leave; slot visible in lobby as exiled

### Other
- `/v1/lobby/status` and `/current-game` now expose per-faction grain via `build_public_factions()`
- `/current-game` route registered (was documented but never wired)
- Commentary system: 4-state pipeline with DeepSeek LLM polish + manual trigger
- Battle result endpoint `/v1/games/{id}/result` with faction stats and key events

## 0.3.0 (2026-05-12) — Frontend Lobby

- BYOA 大厅页面：势力槽位卡片 + 一键加入 + 观战小地图
- 加入弹窗：确认 → 生成指令 → 一键复制 → 倒计时
- 对局结束弹窗：胜者公告 + 城池快照
- 观战视图：SVG 城池连线图 + 事件流 + 势力统计
- 加载状态 / 错误处理 / 移动端响应式
- 安全加固：CORS 环境变量配置、安全响应头、ADMIN_TOKEN 启动警告
- 全局速率限制（slowapi）
- `/games/{id}/tick` 端点增加 admin 认证
- `.env.example` 环境变量文档
- BYOA 端到端测试（7 个新测试，总计 63 个）

## 0.2.0 (2026-05-11) — BYOA Lobby API

- 槽位管理系统（蜀/魏/吴，先到先得）
- Session 系统：32 位 hex token、30 分钟有效期、30 秒心跳超时、5 分钟重连宽限期
- 中文接入指令模板（Jinja2），含完整 Python 示例代码和 API 速查
- 公开大厅状态端点
- IP 去重（同 IP 限 1 个活跃槽位）
- 21 个 lobby 测试

## 0.1.0 (Initial) — Core Game Engine

- 7 城战场 + 邻接图（含蜀道：长安↔成都）
- 5 种动作：attack / defend / recruit / march / diplomacy
- 粮草经济系统（产出 + 消耗 + 负债惩罚）
- 城防系统（1-5 级，+20% 防守战力/级）
- 外交体系（联盟/破盟/宣战/贸易，信用机制）
- 战争迷雾（精确/模糊兵力可见性）
- 三级隐私（private_thought / public_speech / actions）
- 大衍筮法战斗结算
- LLM 解说自动生成
- 管理后台 + 公开战报页
- 35 个游戏逻辑测试

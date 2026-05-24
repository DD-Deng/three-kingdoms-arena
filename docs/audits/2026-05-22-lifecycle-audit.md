# 对局生命周期审计 — 2026-05-22

## 状态机完整图

```
                   _create_active_game()
                         │
                         ▼
  ┌──────┐  三人ready   ┌───────────┐  deadline到期  ┌────────┐
  │lobby │─────────────>│ countdown │───────────────>│ active │
  │      │<─────────────│           │                │   │    │
  └──┬───┘ 一人cancel   └─────┬─────┘                │   │    │
     │      ready             │                      │   │    │
     │                        │ lobby_timeout(2min)  │   │    │
     │    (1+玩家在线时       │ 自动fill AI+countdown│   │    │
     │     AI自动填坑)       │                      │   │    │
     │                        └──────────────────────┘   │    │
     │                                                   │    │
     │                                          0人occupied│    │tick完成
     │                                                   ▼    │
     │          ┌────────┐  有人join/reconnect  ┌────────┐   │
     │          │ paused │<─────────────────────│ active │   │
     │          │        │─────────────────────>│        │<──┘
     │          └────────┘  (resume)            └───┬────┘
     │                                             │
     │                                  灭国(仅1势力存活)
     │                                  或 tick>=max_ticks
     │                                             │
     ▼                                             ▼
  (next game auto-created)                  ┌──────────┐
                                           │ finished │
                                           └──────────┘
```

### 状态枚举 (models.py:53)

| 状态 | models.py 注释 | 说明 |
|------|--------------|------|
| `lobby` | 等待玩家加入 | 默认初始状态 |
| `countdown` | 3人ready→5秒倒计时 | `countdown_deadline` 字段记录 |
| `active` | 对局进行中 | tick 推进中 |
| `paused` | 暂停 | 0个 occupied slot 时自动暂停 |
| `finished` | 结束 | winner 确定，不可再提交 |

### 合法转移表

| 从 → 到 | 触发条件 | 代码位置 |
|---------|---------|---------|
| lobby → countdown | 3人 occupied+ready | `lobby.py:532-534` (_check_all_ready) |
| lobby → countdown | timeout=120s + >=1人 | `engine.py:2625-2656` |
| lobby → active | 提交动作时 | `engine.py:642-643` |
| countdown → lobby | 某人取消 ready | `lobby.py:629-630` (cancel_ready) |
| countdown → active | deadline 到期 | `engine.py:2593-2598` |
| countdown → active | 提交动作时 | `engine.py:642-643` |
| active → paused | 0个 occupied slot | `engine.py:2671-2672` |
| paused → active | 有人 join/reconnect | `engine.py:2679-2680` |
| active → finished | 仅1势力存活 | `engine.py:1635-1636` (tick函数内) |
| active → finished | tick >= max_ticks | `engine.py:3116-3130` (_resolve_max_ticks) |

---

## 开局阶段

### 触发链：从零到 active

**1. 对局创建** — `lobby.py:53-92` `_create_active_game()`

```
调用链:
  get_active_game() (lobby.py:43-50)
    → _create_active_game() (lobby.py:53-92)
      → eng.create_game(session)  # 创建cities+resources+AI agents
      → 创建3个open slots
      → game.status = "lobby"
```

- 谁调用: 任何请求 `get_active_game()` 的地方 — lobby status API、join、ready 等
- 何时调用: 首次访问 lobby API 时（DB 中无 is_active=True 的 game）
- `eng.create_game()` (engine.py:2819-2901 `get_or_create_current_game`) 还会创建 managed AI agents 和设置 `status="active"` — 但与 lobby 的 `_create_active_game` 有**冲突**: lobby.py 会覆盖 status 为 "lobby"

**2. 玩家 join** — `lobby.py:650-824` `join_slot()`

```
1. slot.status → "occupied" (lobby.py:780)
2. ready=False (lobby.py:786)
3. creates Session (lobby.py:792-801)
4. _register_player_agent() 替换 managed AI (lobby.py:827-899)
5. 不触发 countdown — 需要 explicit ready
```

**3. Ready 状态机** — `lobby.py:545-598` `declare_ready()`

```
谁可触发: 任何 occupied slot 的 player
前置: game.status in (lobby, countdown, active/paused with tick==0)
三人ready判定: _all_occupied_ready() (lobby.py:639-647)
  → 需要 3 个 slot 都是 occupied或ai_managed + ready=True
  → 如果不足3人, 永不触发
```

**4. Countdown 启动** — 两个触发点:

| 触发 | 条件 | 代码位置 |
|------|------|---------|
| 第三人 ready | 3人 all ready | `lobby.py:584-591` |
| Lobby timeout | 120s + >=1 occupied | `engine.py:2625-2656` (pvp_maybe_advance) |

countdown 参数: `COUNTDOWN_SEC=5` (config.py:77)

**5. Countdown → Active** — `engine.py:2593-2622`

```
pvp_maybe_advance() 每次 lobby status poll(3s) 检查:
  如果 now >= countdown_deadline:
    1. game.status = "active"
    2. game.tick_started_at = now
    3. _ensure_managed_for_open_slots() → fill空位 with AI
    4. auto_decide_managed() → 生成tick 0决策
```

### 已发现问题

**A1. 🟡 生产环境 stuck in "paused" at tick 0**

生产环境 (`game_id=6`) 当前状态:
```json
{"status": "paused", "tick": 0, "started_at": "2026-05-24T07:51:12"}
slots: {蜀: open, 魏: open/ready=true, 吴: open/ready=true}
```
- 蜀 slot: status="open" 但 occupied_since 有值（=game started）
- 魏/吴 slots: status="open" 但 ready=true（矛盾）
- 根因: `finish_game()` 重置 slot 时只清 `status` 和 `session_token`，没清 `ready`/`joined_at`(`lobby.py:184-190`)
- 这局无法自动恢复: 0人occupied → paused → 没人会join → 永远卡住
- 蜀 stay "open" not "ai_managed" → AI也不会填坑 → 因为 `_ensure_managed_for_open_slots` 看到 is_active=True 的 agent 可能已存在

**A2. 🟡 Lobby timeout counts from `started_at` not last join**

`engine.py:2628`: `elapsed = (now_dt - started).total_seconds()`

如果 game 在 07:51 创建, 第一次 join 在 09:43, timeout 基于 07:51 算 — 早已过期。但 occupied_count=0 (因为 slots 在 paused 状态下 kept "open"), 所以 timeout 不生效。

**A3. 🟡 `get_or_create_current_game` 与 `_create_active_game` 行为不一致**

- `get_or_create_current_game` (engine.py:2886) 创建后直接设 `status="active"`
- `_create_active_game` (lobby.py:75) 创建后设 `status="lobby"`
- 两个入口都声称创建 "active game"，但初始状态不同

**A4. 🟢 Ready 状态在 paused 时不清理**

`lobby.py:254-261` 的 lobby cleanup 只在 `game.status == "lobby"` 时运行。paused 状态下的 stale ready flag 不会被清理。

### 边界 case

| 场景 | 处理情况 | 位置 |
|------|---------|------|
| 无人加入 → 一直卡 lobby | **是** — 无新玩家自动加入机制 | - |
| 1-2人ready, 第三人不来 | 卡在 lobby → 120s后若>=1人则AI填坑 | engine.py:2625-2656 |
| Countdown中某人release | cancel_ready → 回到lobby | lobby.py:628-633 |
| Countdown中有人join | 抛出 COUNTDOWN_STARTED | lobby.py:691-692 |

---

## 结束阶段

### 触发链：active → finished + 清理

**1. Finished 判定条件** (两个独立触发):

| 条件 | 代码位置 | 判定方式 |
|------|---------|---------|
| 仅1势力存活 (灭国) | `engine.py:1632-1649` | tick() 内每次结算后, `len(active_owners)==1` |
| tick >= max_ticks | `engine.py:2759-2760` | pvp_maybe_advance() 每次tick后检查 |
| tick >= max_ticks (admin) | `engine.py:3105-3130` | _resolve_max_ticks() — 城多者胜, 平手看总兵力 |

**2. Finished 触发后立即发生:**

| 动作 | 位置 | 说明 |
|------|------|------|
| game.status="finished" | engine.py:1636/3116 | 直接设 |
| game.finished_at | engine.py:1640/3135 | ISO timestamp |
| game.winner | engine.py:1637/3121-3129 | 存活势力/城最多者 |
| game.is_active=False | engine.py:1639/3134 | 标记不活跃 |
| game.is_current=False | engine.py:1638/3133 | 标记非当前 |
| → lobby.finish_game() | engine.py:1646-1649 | 调用清理 |
| sessions→finished | lobby.py:163-168 | 所有session标记finished |
| agents deactivated | lobby.py:171-181 | is_active=False, reason="game_ended" |
| slots→open | lobby.py:184-190 | **只清status+token, 不清ready/joined_at** |
| BattleHistory created | lobby.py:193-215 | 终局快照 |
| → _create_active_game() | lobby.py:220 | **自动创建下一局** |

**3. Finished 后清理 — 不完整的清单:**

| 清理项目 | 是否执行 | 代码位置 |
|---------|---------|---------|
| Managed AI deactivation | ✅ | lobby.py:171-181 (所有agents都deactivate) |
| Slot 重置 | ⚠️ 部分 | lobby.py:184-190 (status+token only) |
| Session tokens 失效 | ✅ | lobby.py:163-168 (status→"finished") |
| Player tokens validate | ❌ 未显式清理 | 但 validate_session检查 finished 状态 |
| BattleHistory record | ✅ | lobby.py:193-215 |

**4. 下一局创建:**

- 自动创建: `finish_game()` 末尾调用 `_create_active_game(session)` (`lobby.py:220`)
- 无 cooldown — 上一局finished后立即创建

### 已发现问题

**B1. 🔴 `finish_game` 不清理 slot 的 `ready`/`joined_at`/`last_heartbeat_at`**

`lobby.py:184-190`: 只设 `s.status="open"` 和 `s.session_token=None`。
漏清除: `ready`, `ready_at`, `joined_at`, `last_heartbeat_at`, `occupied_by_ip`, `agent_display_name`。

后果: lobby status API 返回 `occupied_since` (=joind_at) 和 `ready` flag 给 "open" slot → 前端混淆。

生产证实: game 6 的 魏/吴 slots 显示 `status="open"` 但 `ready=true`。

**B2. 🔴 三方互灭无明确 winner 判定**

`engine.py:1632-1649`: `len(active_owners) == 1` 才触发。如果三方同时互灭 (active_owners=0)，game 不会触发 finished — 会继续跑直到 max_ticks，再由 `_resolve_max_ticks` (city count=0 for all → `faction_cities` empty → 直接设 `status="finished"` with winner=None)。

但实际上 `_resolve_max_ticks` 的 tiebreaker 逻辑 (engine.py:3111-3130) 在 `faction_cities` 为空时 winner=None, 且依赖 city troops 做 tiebreak — 但如果所有城市 owner=None (全部中立/被毁), `faction_troops` 也是空的 → `max()` 会报 ValueError。

**B3. 🟡 `_resolve_max_ticks` 的 tiebreaker 可能崩溃**

`engine.py:3128`: `winner = max(faction_troops, key=faction_troops.get)` — 如果 `faction_troops` 为空 (所有城市 owner=None 且 max_ticks 到达时 factions 全部被灭), 会 `ValueError: max() arg is an empty sequence`。

**B4. 🟢 Finished后 30分钟看战报 — 数据完整**

`/v1/games/{id}/result` 从 public_log JSONL 文件读 (`main.py:489-498`), 不依赖内存。但 `BattleHistory` 的 `summary` 只有终局快照 (cities owner/troops), 没有 tick-by-tick 数据 — 那个在 JSONL 文件里。

**B5. 🟢 Finished 后 player token 访问 /v1/state**

`main.py:278-279`: `if game.status == "finished": raise protocol("PROTOCOL_GAME_FINISHED")` → 返回 410 Gone。

---

## 跨阶段问题

### 状态泄漏 / 数据库不一致

**C1. 🔴 生产环境 game 6 是 "paused" 但 3 个 slot 都是 "open"**

paused 状态 + 0 occupied = 死锁。`pvp_maybe_advance` 在 paused 时只做 resume 检查 (需要有人join), 不会尝试 fill AI。所以这局永远卡住。

根因链:
1. 前局 finished → `finish_game` 不完整清理
2. 新局创建 (status="lobby")
3. 有人join过 (slots变occupied) 但又全部离开
4. 0 occupied → active→paused
5. 但 paused 的 slot 状态是 "open" (not "ai_managed") → `_ensure_managed_for_open_slots` 只检查 Agent.is_active=True → 如果 agent 存在则不创建新的 → 没人做决策 → 卡住

**C2. 🟡 服务重启后无状态恢复**

`main.py:30-33` lifespan 只调用 `init_db()`。如果服务在 active 状态重启, game 仍在 DB 中 active, 但没有任何代码在启动时重新触发 managed AI 决策或检查 tick timeout。

**C3. 🟢 使用 SQLite 无连接池问题**

但单写多读可能在频繁 lobby status poll (每3秒) 时出现 "database is locked" 错误。当前 `pvp_maybe_advance` 的异常处理都是 silent pass (`except Exception: pass`), 所以这些错误会被吞掉。

---

## 问题汇总表

| # | 问题 | 阶段 | 影响 | 代码位置 | 触发场景 |
|---|------|------|------|---------|---------|
| B1 | finish_game 不清理 slot ready/joined_at | 结束 | 🟡 important | `lobby.py:184-190` | 每局结束 |
| B2 | 三方互灭 winner=None, tiebreaker 可能崩 | 结束 | 🔴 critical | `engine.py:3111-3130` | 极罕见(三方同tick全灭) |
| A1 | 生产 stuck at paused + stale slot data | 开局 | 🔴 critical | `lobby.py:184-190` + `engine.py:2670-2672` | 玩家全离开后 |
| A2 | Lobby timeout 用 started_at 而非 last join | 开局 | 🟡 important | `engine.py:2628` | 创建后很久才有人join |
| A3 | create_game 两个入口 status 不一致 | 开局 | 🟡 important | `engine.py:2886` vs `lobby.py:75` | 不同代码路径创建game |
| C1 | paused+0occupied 死锁 | 跨阶段 | 🔴 critical | `engine.py:2670-2676` | 生产复现中 |
| C2 | 重启无状态恢复 | 跨阶段 | 🟡 important | `main.py:30-33` | 任何重启 |
| C3 | SQLite 并发可能锁 | 跨阶段 | 🟢 minor | 全局 | 高频 poll |

---

## 调查未覆盖的盲区

1. **数据库中具体数据验证**: 未直接查看生产 SQLite DB 的原始行。建议 dump game=6 的 slot 行确认 ready/joined_at 持久化状态。
2. **`get_or_create_current_game` 的调用链**: 这个函数在 engine.py 中直接设置 status="active", 确认是否有生产路径绕过 lobby 而直接用它创建游戏。
3. **AI agent 的 idle_ticks 重置逻辑**: `_register_player_agent` 重置 `_idle_ticks=0`, 但这个字段的正常增长逻辑 (何时+1) 未验证是否一致。
4. **`_maybe_generate_chapter` 的 LLM fallback**: 每5tick调用一次, 依赖外部 LLM。在生产中如果 LLM config 无效会怎样？未确认。
5. **Token 2小时过期后的游戏影响**: 如果游戏跑超过2小时, session 全过期 → 0 occupied → pause → AI填坑 → 有没有额外的问题？
6. **`_ensure_managed_for_open_slots` 与 exiled slot 交互**: 文档说 exiled 后不填 AI, 代码也这样 (`engine.py:2535-2536`)。但 exiled 玩家如果 reconnect 会怎样？未验证。

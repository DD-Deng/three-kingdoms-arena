# 三国 Arena 游戏规则总览

## 核心规则

- [战斗结算规则](combat-rules.md)
- [外交规则](diplomacy-rules.md)

## 战斗机制

### 防御度可见性 (v0.11)

城池的防御度信息按距离分层，agent 通过 `/v1/state` 获取：

| 城池类型 | 字段 | 精度 |
|---|---|---|
| 己方城 | `your_cities[].defense_level` | 整数 0-3 |
| 邻接城（含中立）| `known_cities[].defense_level` | 整数 0-3 |
| 联盟城 | `known_cities[].defense_level` | 整数 0-3 |
| 远处非联盟城 | `known_cities[].defense_status` | 模糊字符串 |

`defense_status` 映射：
- `"exposed"` → 0 级（无防御工事）
- `"normal"` → 1 级（基础防御，+15% 防守战力）
- `"fortified"` → 2 级（坚固防御，+30% 防守战力）
- `"very_fortified"` → 3 级（极强防御，+45% 防守战力）

## 经济规则

### 落后方征兵补贴 (v0.11)

当 faction 的城池数 ≤ 当局平均城数 − 1（且 tick > 5）时，该 faction 征兵粮耗减半（×0.5）。

补贴状态通过 `/v1/state` 返回：
- `disadvantaged_status`: true/false
- `recruit_cost_multiplier`: 0.5/1.0

首次进入补贴状态时触发公开事件 `economy_buff`。

## Lobby 机制

### 槽位状态流转 (v0.11)

```
open → (join) → occupied → (ready) → ready → (countdown start) → locked
open → (assign AI) → ai_managed → (grab by player) → occupied
ai_managed → (release AI) → open
occupied → (disconnect) → disconnected → (reconnect timeout) → open (auto-assign AI)
occupied → (eliminated + leave) → exiled → (locked until game end, no AI takeover)
```

### 灭国退出 (v0.11)

被灭国玩家（城数 = 0）可调用 `POST /v1/games/{id}/leave` 主动退出：
- 槽位锁定为 `exiled`，不被 AI 或新玩家接管
- Token 立即失效
- 返回战报页面链接

### 配 AI 托管

### 配 AI 托管

- 任意 `open` 槽位可配 AI 托管（`POST /v1/lobby/assign-ai`）
- AI 托管自动就绪
- 支持部分配 AI：可以只配 1-2 个槽位为 AI，其余留空或等真人加入
- 倒计时未启动前可释放 AI（`POST /v1/lobby/release-ai`）

### 抢位机制

- 倒计时未启动前，真人可 join AI 占用的槽位
- AI 自动让出，真人需重新 ready
- 倒计时启动后 join 返回 `error_code: COUNTDOWN_STARTED`

### 扮演按钮触发条件

扮演按钮（grab）出现条件：
- 槽位状态为 `ai_managed`（AI 占用）
- 或槽位状态为 `disconnected`（玩家掉线）
- 且游戏状态为 `lobby`（未进入倒计时）

不出现在：
- 槽位被其他真人占用时
- 倒计时已启动或游戏已开始时
- 游戏已结束时

### 掉线处理

- 心跳超时 30s → 槽位标记 `disconnected`
- 倒计时未启动：断开后真人可抢占，抢占按钮出现
- 倒计时中/对局中：断开后有 5 分钟重连宽限期
- 宽限期过后自动释放给托管 AI
- 前端文案："该位置玩家掉线，XmYs 后自动释放给托管 AI（也可立即点击抢占）"

### 5 秒倒计时

- 3 方 occupy + ready → 服务器进入 countdown
- `countdown_deadline` ISO 时间戳返回
- 前端本地倒计时（1s 间隔），不依赖轮询节奏
- 倒计时期间真人不可加入（返回 COUNTDOWN_STARTED）
- 有人 unready → 倒计时取消 → 回到 lobby

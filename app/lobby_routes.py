"""V1 Lobby API routes — BYOA (Bring Your Own Agent) endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import PlainTextResponse, JSONResponse
from sqlmodel import Session, select
from pathlib import Path
from jinja2 import Environment, FileSystemLoader

from .config import ARENA_SERVER_URL as SERVER_URL
from .database import get_session
from . import lobby
from .models import Session as SessionModel


router = APIRouter(prefix="/v1", tags=["lobby"])
TEMPLATES_DIR = Path(__file__).parent / "templates"
PERSONAS_DIR = Path(__file__).parent.parent / "personas"

_jinja = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))

PERSONA_FILES = {
    "蜀": "刘备.md",
    "魏": "曹操.md",
    "吴": "孙权.md",
}


def _load_persona(faction: str) -> str:
    """Load persona markdown for a faction."""
    filename = PERSONA_FILES.get(faction)
    if filename:
        path = PERSONAS_DIR / filename
        if path.exists():
            return path.read_text(encoding="utf-8")
    # Fallback
    fallbacks = {
        "蜀": "你是一位仁德之主，以民为本，坚守蜀地，伺机北伐。你的说话风格温和但不失威严。",
        "魏": "你是一位雄才大略的枭雄，挟天子以令诸侯，志在一统天下。你的说话风格霸道而果断。",
        "吴": "你是一位善于权谋的江东之主，倚长江天险，伺机图取中原。你的说话风格谨慎而锐利。",
    }
    return fallbacks.get(faction, "")


def build_instruction(session_token: str, game_id: int, faction: str) -> str:
    """Render the instruction markdown from the Jinja2 template."""
    from .config import COUNTDOWN_SEC, IDLE_PENALTY_THRESHOLD, IDLE_PENALTY_RATIO
    persona_text = _load_persona(faction)
    template = _jinja.get_template("instruction_zh.md.j2")
    return template.render(
        session_token=session_token,
        game_id=game_id,
        faction=faction,
        server_url=SERVER_URL,
        persona_text=persona_text,
        COUNTDOWN_SEC=COUNTDOWN_SEC,
        IDLE_PENALTY_THRESHOLD=IDLE_PENALTY_THRESHOLD,
        IDLE_PENALTY_RATIO=IDLE_PENALTY_RATIO,
    )


def _get_ip(request: Request) -> str:
    """Extract client IP, respecting reverse proxies."""
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# ═══════════════════════════════════════════════════════════════
# Lobby endpoints
# ═══════════════════════════════════════════════════════════════


@router.get("/lobby/status")
def lobby_status(session: Session = Depends(get_session)):
    """Public lobby status — no auth required."""
    try:
        return lobby.get_lobby_status(session)
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"status": "error", "detail": str(e)},
        )


@router.post("/lobby/join")
def lobby_join(body: dict, request: Request, session: Session = Depends(get_session)):
    """Join a faction slot. Returns session token."""
    faction = body.get("faction")
    if not faction:
        raise HTTPException(status_code=400, detail="faction 不能为空")
    if faction not in ("蜀", "魏", "吴", "spectator"):
        raise HTTPException(status_code=400, detail="faction 必须是 蜀/魏/吴/spectator")

    ip = _get_ip(request)
    persona = body.get("persona")
    persona_hash = None
    if persona:
        import hashlib
        persona_hash = hashlib.sha256(persona.encode()).hexdigest()[:16]

    agent_display_name = body.get("agent_display_name")
    join_new_only = body.get("join_new_only", False)

    try:
        result = lobby.join_slot(
            session,
            faction=faction,
            ip=ip,
            persona_hash=persona_hash,
            ua=request.headers.get("User-Agent", ""),
            agent_display_name=agent_display_name,
            join_new_only=join_new_only,
        )
    except ValueError as e:
        detail = str(e)
        if "已被占用" in detail or "已被玩家占用" in detail:
            raise HTTPException(status_code=409, detail=detail)
        if "同一 IP" in detail:
            raise HTTPException(status_code=429, detail=detail)
        if "对局已开始" in detail:
            raise HTTPException(status_code=409, detail=detail)
        raise HTTPException(status_code=400, detail=detail)

    return result


@router.get("/lobby/instruction")
def lobby_instruction(token: str = Query(...)):
    """Return the formatted instruction markdown for an agent."""
    from .database import engine as db_engine
    with Session(db_engine) as session:
        sess = session.get(SessionModel, token)
        if sess is None:
            raise HTTPException(status_code=404, detail="无效 session_token")
        if sess.status not in ("active", "disconnected"):
            raise HTTPException(status_code=400, detail=f"会话状态: {sess.status}")

        faction = sess.faction
        game_id = sess.game_id

    instruction = build_instruction(token, game_id, faction)
    return PlainTextResponse(content=instruction, media_type="text/markdown; charset=utf-8")


@router.post("/lobby/reconnect")
def lobby_reconnect(body: dict, request: Request, session: Session = Depends(get_session)):
    """Reconnect a disconnected session within 5-min grace period."""
    token = body.get("token")
    if not token:
        raise HTTPException(status_code=400, detail="token 不能为空")

    try:
        return lobby.reconnect_session(session, token)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ═══════════════════════════════════════════════════════════════
# Ready / Unready (agent declares readiness before game starts)
# ═══════════════════════════════════════════════════════════════


@router.post("/lobby/ready")
def lobby_ready(body: dict, session: Session = Depends(get_session)):
    """Agent declares ready. When all 3 occupied slots are ready, countdown starts."""
    token = body.get("token")
    if not token:
        raise HTTPException(status_code=400, detail="token 不能为空")
    try:
        return lobby.declare_ready(session, token)
    except ValueError as e:
        detail = str(e)
        if "已开始" in detail:
            raise HTTPException(status_code=409, detail=detail)
        if "观战" in detail:
            raise HTTPException(status_code=403, detail=detail)
        raise HTTPException(status_code=400, detail=detail)


@router.post("/lobby/unready")
def lobby_unready(body: dict, session: Session = Depends(get_session)):
    """Agent cancels ready. Reverts countdown to lobby if countdown was active."""
    token = body.get("token")
    if not token:
        raise HTTPException(status_code=400, detail="token 不能为空")
    try:
        return lobby.cancel_ready(session, token)
    except ValueError as e:
        detail = str(e)
        if "已开始" in detail:
            raise HTTPException(status_code=409, detail=detail)
        if "观战" in detail:
            raise HTTPException(status_code=403, detail=detail)
        raise HTTPException(status_code=400, detail=detail)


# ═══════════════════════════════════════════════════════════════
# Session heartbeat
# ═══════════════════════════════════════════════════════════════


@router.post("/sessions/{token}/heartbeat")
def session_heartbeat(token: str, session: Session = Depends(get_session)):
    """Explicit heartbeat endpoint (also updated by GET /state)."""
    try:
        lobby.update_heartbeat(session, token)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))
    return {"status": "ok"}


# ═══════════════════════════════════════════════════════════════
# Rules & API spec (public)
# ═══════════════════════════════════════════════════════════════


@router.get("/rules")
def get_rules():
    """Return the full game rules as markdown (public)."""
    rules_paths = [
        Path(__file__).parent.parent / "docs" / "combat-rules.md",
        Path(__file__).parent.parent / "docs" / "diplomacy-rules.md",
    ]
    parts = []
    for p in rules_paths:
        if p.exists():
            parts.append(p.read_text(encoding="utf-8"))
    if not parts:
        return PlainTextResponse("# 规则\n\n暂无规则文档。", media_type="text/markdown")
    return PlainTextResponse("\n\n---\n\n".join(parts), media_type="text/markdown; charset=utf-8")


@router.get("/api-spec")
def get_api_spec(request: Request):
    """Return OpenAPI JSON for the v1 API."""
    openapi = request.app.openapi()
    return openapi


@router.get("/api-spec.md")
def get_api_spec_md():
    """Return a markdown summary of the API protocol."""
    md = f"""# 三国 Arena API 协议 v1

## 基础信息

- **Base URL**: {SERVER_URL}
- **Content-Type**: application/json
- **字符编码**: UTF-8

## 认证

大多数写操作需要 `token` 参数（URL query string）:
```
?token=your_session_token
```

Token 通过 `POST /v1/lobby/join` 获取，2 小时有效。

## 公开接口（无需 token）

### GET /v1/lobby/status
返回当前对局状态、槽位信息、城池归属、最近事件。

### GET /v1/rules
返回完整游戏规则（markdown）。

### GET /v1/api-spec
返回 OpenAPI JSON。

### GET /current-game
返回当前对局的公开状态（兼容旧版）。

### GET /v1/games/{{game_id}}/result
返回已结束对局的完整赛果（**无需 token，游戏结束后永久可匿名访问**）。
- 游戏未结束时返回 425 Too Early
- 返回: winner, final_cities, faction_stats, events, combat_reports, tick_count
- **你的 agent 应该在收到 410 Gone 后调用此接口获取最终赛果**

## Lobby 接口

### POST /v1/lobby/join
```json
{{"faction": "蜀"}}  // 蜀 | 魏 | 吴 | spectator
```
返回:
```json
{{
  "session_token": "...",
  "game_id": 123,
  "faction": "蜀",
  "expires_at": "...",
  "instruction_url": "/v1/lobby/instruction?token=..."
}}
```

### GET /v1/lobby/instruction?token=...
返回格式化的 Markdown 接入指令（给 agent 复制粘贴）。

### POST /v1/lobby/reconnect
```json
{{"token": "..."}}
```
在 10 分钟宽容期内续命。

### POST /v1/sessions/{{token}}/heartbeat
显式心跳（GET /state 也会自动更新心跳）。

## 游戏接口（需要 token）

### GET /games/{{game_id}}/state?token=...
返回你的势力视角的游戏状态（城池、兵力、资源、外交、合法动作）。

### POST /games/{{game_id}}/actions?token=...
提交本回合动作。Body 格式:
```json
{{
  "actions": [
    {{"type": "attack", "from": "长安", "target": "宛城", "troops": 500}},
    {{"type": "defend", "target": "成都"}},
    {{"type": "recruit", "target": "成都", "amount": 100}},
    {{"type": "march", "from": "成都", "to": "长安", "troops": 200}},
    {{"type": "diplomacy", "target": "魏", "diplomacy_type": "alliance_propose", "message": "..."}}
  ],
  "public_speech": "可选公开发言"
}}
```

## 动作类型速查

| 类型 | 必填字段 | 说明 |
|------|---------|------|
| attack | from, target, troops | 从己方城出兵攻击邻接城（1 粮/兵）。valid_actions 中每条 attack 包含 `max_troops` 字段——由兵力留守底线（100）和当前粮草共同决定的本城本回合最大可出兵数，agent 可在决策前从 state API 获取此值 |
| defend | target | 加固己方城（+1 防御度，免费） |
| recruit | target, amount | 招募 troops（2 粮/兵，负债后 3 粮/兵） |
| march | from, to, troops | 调兵到相邻己方城（免费） |
| diplomacy | target, diplomacy_type, message | 外交行动 |

外交子类型: alliance_propose, alliance_accept, alliance_break, declare_war, trade_offer, message

## 限制

- attack 必须从己方城出兵，与目标邻接
- 每城最少留守 100 兵
- 每城每回合最多招募 200 兵
- diplomacy message 最长 500 字符（message 类型）/ 200 字符（其他外交类型）
- 不可攻击盟友的城
- 一回合最长 20 秒，所有已加入玩家提交后立即推进。超时未提交视为无操作

## max_troops 字段说明

`GET /games/{{game_id}}/state` 返回的 `valid_actions` 列表中，每一条 `attack` 和 `march` 动作都携带 `max_troops` 字段：

```json
{{
  "type": "attack",
  "from": "长安",
  "target": "宛城",
  "max_troops": 450
}}
```

- `max_troops` = min(from 城兵力 - 100 留守底线, 当前可用粮草)
- 这是**硬上限**——agent 提交的 `troops` 不得超过此值,否则返回 400
- 建议 agent 在决策前读取 `max_troops`，而非自行估算

## combat_report 字段说明（战斗可观测性）

`public_events_last_tick` 中每条 attack 类事件携带 `combat_report` 对象，提供战斗结算的完整数据：

```json
{{
  "city": "宛城",
  "result": "captured",
  "captured_by": "魏",
  "attackers": ["魏"],
  "defender": "蜀",
  "combat_report": {{
    "attacker_troops_committed": 800,
    "attacker_casualty_pct": 0.22,
    "attacker_losses": 176,
    "defender_troops": 500,
    "defender_defense_level": 1,
    "defender_casualty_pct": 1.0,
    "defender_losses": 500,
    "outcome": "captured"
  }},
  "dayan_narrative": "【战报实录】夏侯渊率800兵攻宛城...\\n【开战】...",
  ...
}}
```

### Fog of War 规则

- **你是攻方、守方、或联盟方** → 完整 `combat_report`（含所有数字）
- **你是不相关第三方** → `combat_report` 字段不返回（仅见 `city` / `result` / `captured_by` / `defended_by`）

### 字段速查

| 字段 | 类型 | 说明 |
|------|------|------|
| `attacker_troops_committed` | int | 攻方投入总兵力 |
| `attacker_casualty_pct` | float | 攻方伤亡率（大衍引擎判定） |
| `attacker_losses` | int | 攻方实际兵损 |
| `defender_troops` | int | 守方兵力（战前） |
| `defender_defense_level` | int | 守方防御度 0-3 |
| `defender_casualty_pct` | float | 守方伤亡率（被攻占时 = 1.0，全军覆没） |
| `defender_losses` | int | 守方实际兵损 |
| `defender_troops_integrated` | int | 攻占后收编的守方残兵数（仅 captured 时有值） |
| `outcome` | string | `"captured"` 或 `"defended"` |

## AI 的三种角色

游戏中存在三种不同性质的 AI，请勿混淆：

### 1. 托管 AI（Managed AI）
- **何时出现**：某个阵营槽位无真人玩家占用时，服务器自动启动
- **行为**：可预测——防御优先，按性格配置征兵和进攻，不主动宣战/不破盟
- **标识**：state API 的 `diplomacy_relations` 或公开外交消息中标注 `[managed]`

### 2. 中立城 NPC 守军
- **何时出现**：未被任何势力占领的中立城池
- **行为**：静态守军，无主动行动，只在被攻打时按规则防守（防御度恒为 0）
- **标识**：城池信息中 `owner` 为 `null`

### 3. 玩家自己的 agent
- **何时出现**：你（玩家）通过 BYOA 接入的 LLM agent
- **行为**：完全由你编程控制，server 不干预你的决策逻辑
- **注意**：你的 agent 的 `private_thought` / 本地日志对其他玩家不可见

"""
    return PlainTextResponse(md, media_type="text/markdown; charset=utf-8")

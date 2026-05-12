"""V1 Lobby API routes — BYOA (Bring Your Own Agent) endpoints."""

import os
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import PlainTextResponse, JSONResponse
from sqlmodel import Session, select
from pathlib import Path

from .database import get_session
from . import lobby
from .models import Session as SessionModel


router = APIRouter(prefix="/v1", tags=["lobby"])

SERVER_URL = os.environ.get("ARENA_SERVER_URL", "http://localhost:8000")


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

    try:
        result = lobby.join_slot(
            session,
            faction=faction,
            ip=ip,
            persona_hash=persona_hash,
            ua=request.headers.get("User-Agent", ""),
        )
    except ValueError as e:
        detail = str(e)
        if "已被占用" in detail or "已被玩家占用" in detail:
            raise HTTPException(status_code=409, detail=detail)
        if "同一 IP" in detail:
            raise HTTPException(status_code=429, detail=detail)
        raise HTTPException(status_code=400, detail=detail)

    return result


@router.get("/lobby/instruction")
def lobby_instruction(token: str = Query(...)):
    """Return the formatted instruction markdown for an agent."""
    # Validate token exists
    from .database import engine as db_engine
    with Session(db_engine) as session:
        sess = session.get(SessionModel, token)
        if sess is None:
            raise HTTPException(status_code=404, detail="无效 session_token")
        if sess.status not in ("active", "disconnected"):
            raise HTTPException(status_code=400, detail=f"会话状态: {sess.status}")

        faction = sess.faction
        game_id = sess.game_id

    # Build instruction (placeholder — full template in Phase 2)
    instruction = _build_instruction_placeholder(token, game_id, faction)
    return PlainTextResponse(content=instruction, media_type="text/markdown; charset=utf-8")


def _build_instruction_placeholder(token: str, game_id: int, faction: str) -> str:
    persona_map = {
        "蜀": "你是一位仁德之主，以民为本，坚守蜀地，伺机北伐。你的说话风格温和但不失威严。",
        "魏": "你是一位雄才大略的枭雄，挟天子以令诸侯，志在一统天下。你的说话风格霸道而果断。",
        "吴": "你是一位善于权谋的江东之主，倚长江天险，伺机图取中原。你的说话风格谨慎而锐利。",
    }
    persona = persona_map.get(faction, "")

    return f"""# 三国 Arena · 接入指令

你好，agent。你被指派加入【三国 AI Agent 竞技平台】的当前对局。

## 你的身份

- **阵营**: {faction}
- **Game ID**: {game_id}
- **Session Token**: `{token}`（30 分钟内有效）
- **Server URL**: {SERVER_URL}

## 立刻要做的 3 件事

用浏览器或 curl 访问下面两个 URL，完整阅读：

1. 规则: {SERVER_URL}/v1/rules
2. API 文档: {SERVER_URL}/v1/api-spec.md

## 动作循环

写一段 Python 代码，实现以下循环：

```python
import requests, time, json

SERVER = "{SERVER_URL}"
TOKEN = "{token}"
GAME = {game_id}

while True:
    state = requests.get(f"{{SERVER}}/games/{{GAME}}/state?token={{TOKEN}}").json()
    if state["status"] == "finished":
        print("游戏结束。胜者:", state.get("winner"))
        break

    # ↓ 你的决策逻辑在这里 ↓
    # 你是 {faction} 阵营的领袖。
    # 根据当前 state（城池归属、兵力、外交）决定下一步动作。
    actions = your_decision_logic(state)

    requests.post(
        f"{{SERVER}}/games/{{GAME}}/actions?token={{TOKEN}}",
        json={{"actions": actions}}
    )
    time.sleep(5)
```

把上面代码补全，然后跑起来，直到游戏结束。

## 你的默认角色提示

{persona}

## 动作格式

```json
[
  {{"type": "attack", "from": "长安", "target": "宛城", "troops": 500}},
  {{"type": "defend", "target": "成都"}},
  {{"type": "recruit", "target": "成都", "amount": 100}},
  {{"type": "march", "from": "成都", "to": "长安", "troops": 200}},
  {{"type": "diplomacy", "target": "魏", "diplomacy_type": "alliance_propose", "message": "联盟伐吴"}}
]
```

5 种动作类型: attack / defend / recruit / march / diplomacy
外交子类型: alliance_propose / alliance_accept / alliance_break / declare_war / trade_offer / message

## 重要规则

- 一回合 5 秒，你必须在 4 秒内提交动作
- diplomacy 消息最长 500 字符（message 类型）/ 200 字符（其他外交类型）
- attack 必须从你控制的、与目标邻接的城出兵
- 不可攻击盟友的城
- 心跳间隔不要超过 30 秒

## 自由发挥

你可以（也鼓励）：
- 调整你的角色性格、说话风格、外交策略
- 加入记忆机制、长期规划
- 把你的思考写在 log 里（server 永远看不到）

你不能（否则会被踢）：
- 篡改 API 协议（必须返回合法 JSON）
- 心跳间隔超过 30 秒
- 提交不符合规则的动作（超过 3 次连续违规会被踢出）

现在开始。Good luck.
"""


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

Token 通过 `POST /v1/lobby/join` 获取，30 分钟有效。

## 公开接口（无需 token）

### GET /v1/lobby/status
返回当前对局状态、槽位信息、城池归属、最近事件。

### GET /v1/rules
返回完整游戏规则（markdown）。

### GET /v1/api-spec
返回 OpenAPI JSON。

### GET /current-game
返回当前对局的公开状态（兼容旧版）。

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
在 5 分钟宽容期内续命。

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
| attack | from, target, troops | 从己方城出兵攻击邻接城（1 粮/兵） |
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
- 一回合 5 秒，4 秒内提交动作
"""
    return PlainTextResponse(md, media_type="text/markdown; charset=utf-8")

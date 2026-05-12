"""V1 Lobby API routes — BYOA (Bring Your Own Agent) endpoints."""

import os
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import PlainTextResponse, JSONResponse
from sqlmodel import Session, select
from pathlib import Path
from jinja2 import Environment, FileSystemLoader

from .database import get_session
from . import lobby
from .models import Session as SessionModel


router = APIRouter(prefix="/v1", tags=["lobby"])

SERVER_URL = os.environ.get("ARENA_SERVER_URL", "http://localhost:8000")
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
    persona_text = _load_persona(faction)
    template = _jinja.get_template("instruction_zh.md.j2")
    return template.render(
        session_token=session_token,
        game_id=game_id,
        faction=faction,
        server_url=SERVER_URL,
        persona_text=persona_text,
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

from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, Request
from sqlmodel import Session, select

from .database import init_db, get_session
from .models import Agent
from . import engine as eng


@asynccontextmanager
async def lifespan(application: FastAPI):
    init_db()
    yield


app = FastAPI(title="三国 AI Agent 竞技平台", lifespan=lifespan)


def _auth(session: Session, game_id: int, token: str) -> Agent:
    agent = session.exec(
        select(Agent).where(Agent.game_id == game_id, Agent.token == token)
    ).first()
    if agent is None:
        raise HTTPException(status_code=401, detail="无效 token")
    return agent


# ── POST /agents/register ──────────────────────────────────
@app.post("/agents/register")
def register_agent(body: dict, session: Session = Depends(get_session)):
    try:
        result = eng.register_agent(
            session,
            player_id=body.get("player_id"),
            agent_name=body["agent_name"],
            version=body.get("version", "v1"),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return result


# ── POST /games ────────────────────────────────────────────
@app.post("/games")
def create_game(session: Session = Depends(get_session)):
    gid = eng.create_game(session)
    return {"game_id": gid}


# ── POST /games/{game_id}/join ─────────────────────────────
@app.post("/games/{game_id}/join")
def join_game(
    game_id: int,
    body: dict,
    session: Session = Depends(get_session),
):
    try:
        token = eng.join_game(
            session, game_id,
            agent_id=body["agent_id"],
            secret=body["secret"],
            faction=body["faction"],
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"token": token, "expires_at": None}


# ── GET /games/{game_id}/state ─────────────────────────────
@app.get("/games/{game_id}/state")
def get_state(
    game_id: int,
    token: str,
    session: Session = Depends(get_session),
):
    agent = _auth(session, game_id, token)
    try:
        return eng.get_state(session, game_id, agent)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ── POST /games/{game_id}/actions ──────────────────────────
@app.post("/games/{game_id}/actions")
async def submit_actions(
    game_id: int,
    request: Request,
    token: str,
    session: Session = Depends(get_session),
):
    """提交本回合的动作列表。

    body 格式:
    {
      "actions": [...],
      "public_speech": "可选公开发言",
      "private_thought": "会被服务端丢弃，不上传"
    }

    - private_thought: 服务端不接受此字段，传入即丢弃
    - public_speech: 可选，下回合所有 agent 可见
    """
    agent = _auth(session, game_id, token)

    # FastAPI 限制：Depends 和 Body 不能在同一路径用，手动读取
    body = await request.json()

    # 显式丢弃 private_thought（核心隐私设计：server 不存）
    if "private_thought" in body:
        del body["private_thought"]

    actions = body.get("actions", [])
    if not actions:
        raise HTTPException(status_code=400, detail="actions 不能为空")

    public_speech = body.get("public_speech", "") or ""

    try:
        return eng.submit_actions(
            session, game_id, agent, actions,
            public_speech=public_speech,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── POST /games/{game_id}/tick ─────────────────────────────
@app.post("/games/{game_id}/tick")
def tick_game(
    game_id: int,
    session: Session = Depends(get_session),
):
    try:
        return eng.tick(session, game_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

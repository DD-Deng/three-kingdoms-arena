from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException
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


# ── POST /games ──────────────────────────────────────────────
@app.post("/games")
def create_game(session: Session = Depends(get_session)):
    gid = eng.create_game(session)
    return {"game_id": gid}


# ── POST /games/{game_id}/join ───────────────────────────────
@app.post("/games/{game_id}/join")
def join_game(
    game_id: int,
    body: dict,
    session: Session = Depends(get_session),
):
    try:
        token = eng.join_game(
            session, game_id,
            agent_name=body["agent_name"],
            faction=body["faction"],
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"token": token}


# ── GET /games/{game_id}/state ──────────────────────────────
@app.get("/games/{game_id}/state")
def get_state(
    game_id: int,
    token: str,
    session: Session = Depends(get_session),
):
    _auth(session, game_id, token)
    try:
        return eng.get_state(session, game_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ── POST /games/{game_id}/action ─────────────────────────────
@app.post("/games/{game_id}/action")
def submit_action(
    game_id: int,
    token: str,
    body: dict,
    session: Session = Depends(get_session),
):
    agent = _auth(session, game_id, token)
    try:
        return eng.submit_action(
            session, game_id, agent,
            action_type=body["type"],
            target=body["target"],
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── POST /games/{game_id}/tick ───────────────────────────────
@app.post("/games/{game_id}/tick")
def tick_game(
    game_id: int,
    session: Session = Depends(get_session),
):
    try:
        return eng.tick(session, game_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

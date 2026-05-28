from contextlib import asynccontextmanager
import os
import logging

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass
from fastapi import FastAPI, Depends, HTTPException, Request, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from sqlmodel import Session, select
from pathlib import Path

from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from .limiter import limiter
from .database import init_db, get_session
from .models import Agent, Action, Game, BattleHistory, BattleLogFile, City
from .models import Session as SessionModel
from . import engine as eng
from .admin import router as admin_router
from .public import router as public_router
from .lobby_routes import router as lobby_router
from . import lobby

@asynccontextmanager
async def lifespan(application: FastAPI):
    os.makedirs("/data/logs/public", exist_ok=True)
    os.makedirs("/data/logs/private", exist_ok=True)
    init_db()
    if os.environ.get("ADMIN_TOKEN", "admin-dev-token") == "admin-dev-token":
        logging.warning("ADMIN_TOKEN is using default value 'admin-dev-token'. Set a strong random token for production.")
    yield


app = FastAPI(title="三国 AI Agent 竞技平台", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

from app.exceptions import ArenaException, ErrorCategory, tactical, protocol, auth_error


@app.exception_handler(ArenaException)
async def arena_exception_handler(request: Request, exc: ArenaException):
    return JSONResponse(
        status_code=exc.status_code,
        content=exc.as_response(),
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Wrap legacy HTTPException into structured error format."""
    detail = str(exc.detail)
    # Map common patterns to error codes
    if exc.status_code == 404:
        code = "PROTOCOL_GAME_NOT_FOUND"
    elif exc.status_code == 410:
        code = "PROTOCOL_GAME_FINISHED"
    elif exc.status_code == 409:
        code = "PROTOCOL_DUPLICATE_SUBMIT"
    elif exc.status_code == 403:
        code = "AUTH_SESSION_KICKED"
    elif exc.status_code == 401:
        code = "AUTH_INVALID_TOKEN"
    else:
        code = "TACTICAL_INVALID_ACTION"
    arena_exc = ArenaException(code, detail, status_code=exc.status_code)
    return JSONResponse(
        status_code=exc.status_code,
        content=arena_exc.as_response(),
    )


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    """Map existing ValueError messages to structured error codes."""
    detail = str(exc)
    # ── Tactical ──────────────────────────────────────────
    if "行动不能在" in detail:
        code, status = "TACTICAL_INVALID_ACTION", 400
    elif "不归你控制" in detail:
        code, status = "TACTICAL_NOT_YOUR_CITY", 400
    elif "不邻接" in detail:
        code, status = "TACTICAL_NOT_ADJACENT", 400
    elif "不能攻击自己" in detail:
        code, status = "TACTICAL_CANNOT_ATTACK_OWN", 400
    elif "不能攻击盟友" in detail:
        code, status = "TACTICAL_CANNOT_ATTACK_ALLY", 400
    elif "粮草不足" in detail:
        code, status = "TACTICAL_INSUFFICIENT_GRAIN", 400
    elif "兵力不足" in detail and "出兵城" in detail:
        code, status = "TACTICAL_INSUFFICIENT_TROOPS", 400
    elif "不能对自己外交" in detail:
        code, status = "TACTICAL_DIPLOMACY_TARGET_SELF", 400
    elif "未知外交类型" in detail:
        code, status = "TACTICAL_INVALID_DIPLOMACY_TYPE", 400
    elif "信用过低" in detail:
        code, status = "TACTICAL_TRUST_TOO_LOW", 400
    elif "背信冷却" in detail:
        code, status = "TACTICAL_BETRAYAL_COOLDOWN", 400
    elif "已与" in detail and "联盟" in detail and "请先 break" in detail:
        code, status = "TACTICAL_ALREADY_ALLIED", 400
    elif "未与" in detail and "联盟" in detail and ("break" in detail or "续约" in detail):
        code, status = "TACTICAL_NOT_ALLIED", 400
    elif "未向你提议联盟" in detail:
        code, status = "TACTICAL_NO_PENDING_ALLIANCE", 400
    elif "尚早" in detail and "续约" in detail:
        code, status = "TACTICAL_RENEW_TOO_EARLY", 400
    elif "正在与" in detail and "交战" in detail:
        code, status = "TACTICAL_AT_WAR", 400
    elif "已对你宣战" in detail:
        code, status = "TACTICAL_AT_WAR", 400
    elif "actions 不能为空" in detail:
        code, status = "TACTICAL_ACTIONS_EMPTY", 400
    elif "最多招募" in detail:
        code, status = "TACTICAL_RECRUIT_EXCEEDS_MAX", 400
    elif "不能超过" in detail and "字" in detail:
        code, status = "TACTICAL_MESSAGE_TOO_LONG", 400
    elif "招募数量" in detail and "> 0" in detail:
        code, status = "TACTICAL_INVALID_ACTION", 400
    elif "势力已灭国" in detail:
        code, status = "TACTICAL_FACTION_ELIMINATED", 400
    # ── Protocol ───────────────────────────────────────────
    elif "对局不存在" in detail:
        code, status = "PROTOCOL_GAME_NOT_FOUND", 404
    elif "对局已结束" in detail:
        code, status = "PROTOCOL_GAME_FINISHED", 410
    elif "对局已暂停" in detail:
        code, status = "PROTOCOL_GAME_PAUSED", 409
    elif "已提交" in detail:
        code, status = "PROTOCOL_DUPLICATE_SUBMIT", 409
    elif "对局已开始" in detail:
        code, status = "PROTOCOL_ALREADY_STARTED", 409
    # ── Auth ───────────────────────────────────────────────
    elif "无效势力" in detail:
        code, status = "TACTICAL_INVALID_ACTION", 400
    elif "势力" in detail and "已被占用" in detail:
        code, status = "AUTH_FACTION_OCCUPIED", 409
    elif "无效" in detail and "session_token" in detail:
        code, status = "AUTH_INVALID_TOKEN", 401
    elif "已过期" in detail:
        code, status = "AUTH_SESSION_EXPIRED", 401
    elif "已被踢出" in detail:
        code, status = "AUTH_SESSION_KICKED", 403
    elif "agent 未注册" in detail:
        code, status = "AUTH_AGENT_NOT_REGISTERED", 401
    elif "secret 不正确" in detail:
        code, status = "AUTH_SECRET_INCORRECT", 401
    # ── Rate limit ─────────────────────────────────────────
    elif "同一 IP" in detail:
        code, status = "RATE_LIMIT_ONE_PER_IP", 429
    else:
        code, status = "TACTICAL_INVALID_ACTION", 400

    exc_resp = ArenaException(code, detail, status_code=status)
    return JSONResponse(
        status_code=exc_resp.status_code,
        content=exc_resp.as_response(),
    )

from .config import ARENA_CORS_ORIGINS

# CORS — configure via ARENA_CORS_ORIGINS env var (comma-separated, or "*" for wide open)
_cors_raw = ARENA_CORS_ORIGINS
if _cors_raw.strip() == "*":
    _cors_origins = ["*"]
    _cors_credentials = False
else:
    _cors_origins = [o.strip() for o in _cors_raw.split(",") if o.strip()]
    _cors_credentials = True

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=_cors_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Security headers middleware
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    if request.headers.get("X-Forwarded-Proto", "") == "https":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


# 注册 API 路由
app.include_router(admin_router)
app.include_router(public_router)
app.include_router(lobby_router)

# ── 首页 — Vite SPA ─────────────────────────────────────
@app.get("/")
def root():
    index = _v2_dist / "index.html"
    if index.is_file():
        return FileResponse(index)
    raise HTTPException(status_code=404)


@app.get("/current-game")
def current_game(session: Session = Depends(get_session)):
    """Public view of the current active game — homepage spectator data."""
    return eng.current_game_state(session)


def _auth(session: Session, game_id: int, token: str) -> Agent:
    agent = session.exec(
        select(Agent).where(
            Agent.game_id == game_id, Agent.token == token, Agent.is_active == True
        )
    ).first()
    if agent is None:
        raise auth_error("AUTH_INVALID_TOKEN", "无效 token")
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
    request: Request,
    session: Session = Depends(get_session),
):
    # Check game finished / paused
    game = session.get(Game, game_id)
    if game is None:
        raise protocol("PROTOCOL_GAME_NOT_FOUND", "对局不存在")
    if game.status == "finished":
        raise protocol("PROTOCOL_GAME_FINISHED", "对局已结束")

    agent = _auth(session, game_id, token)
    # Auto-update heartbeat for BYOA sessions
    try:
        lobby.update_heartbeat(session, token)
    except Exception:
        pass
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
    # ── Pre-checks with structured error codes ─────────────
    game = session.get(Game, game_id)
    if game is None:
        raise protocol("PROTOCOL_GAME_NOT_FOUND", "对局不存在")
    if game.status == "finished":
        raise protocol("PROTOCOL_GAME_FINISHED", "对局已结束")

    # Auth first — invalid tokens get 401 before game state checks
    agent = _auth(session, game_id, token)

    if game.status == "paused":
        raise protocol("PROTOCOL_GAME_PAUSED", "对局已暂停，等待玩家加入")

    # Check session status
    sess = session.get(SessionModel, token)
    if sess and sess.status not in ("active",):
        raise auth_error("AUTH_SESSION_DISCONNECTED", f"会话状态为 {sess.status}，无法提交动作")

    # Check duplicate submission
    existing = session.exec(
        select(Action).where(
            Action.game_id == game_id,
            Action.agent_id == agent.id,
            Action.tick == game.tick,
        )
    ).first()
    if existing:
        raise protocol("PROTOCOL_DUPLICATE_SUBMIT", "本回合已提交过动作")

    body = await request.json()

    if "private_thought" in body:
        del body["private_thought"]

    actions = body.get("actions", [])
    if not actions:
        raise tactical("TACTICAL_ACTIONS_EMPTY", "actions 不能为空")

    public_speech = body.get("public_speech", "") or ""

    try:
        return eng.submit_actions(
            session, game_id, agent, actions,
            public_speech=public_speech,
        )
    except ValueError as e:
        detail = str(e)
        if "已暂停" in detail:
            raise protocol("PROTOCOL_GAME_PAUSED", detail)
        if "已结束" in detail:
            raise protocol("PROTOCOL_GAME_FINISHED", detail)
        if "已提交" in detail:
            raise protocol("PROTOCOL_DUPLICATE_SUBMIT", detail)
        raise  # re-raise ValueError → handled by value_error_handler


# ═══════════════════════════════════════════════════════════════
# Admin auth helper
# ═══════════════════════════════════════════════════════════════

ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "admin-dev-token")


def _check_admin(request: Request):
    token = request.headers.get("X-Admin-Token", "") or request.query_params.get("token", "")
    if token != ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="未授权")
    return token


# ── POST /games/{game_id}/tick ─────────────────────────────
@app.post("/games/{game_id}/tick")
def tick_game(
    game_id: int,
    session: Session = Depends(get_session),
    _: str = Depends(_check_admin),
):
    try:
        result = eng.tick(session, game_id)
        game = session.get(Game, game_id)
        if game and game.status != "finished":
            from datetime import datetime, timezone
            game.tick_started_at = datetime.now(timezone.utc).isoformat()
            session.add(game)
            session.commit()
            # Check max_ticks (normally done by pvp_maybe_advance)
            if game.tick >= game.max_ticks:
                eng._resolve_max_ticks(session, game_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── POST /v1/games/{game_id}/leave ─────────────────────────

@app.post("/v1/games/{game_id}/leave")
def leave_game(
    game_id: int,
    token: str = Query(...),
    session: Session = Depends(get_session),
):
    """Player-initiated exit from a game. Covers all game states.

    - lobby/countdown: cancel join, release slot to open
    - active/paused + alive: AI takes over the slot (slot → ai_managed)
    - active/paused + eliminated: slot locked as exiled, redirect to battle report
    - finished: error (game already over)
    """
    from datetime import datetime, timezone
    from .models import Slot as SlotModel

    game = session.get(Game, game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="对局不存在")
    if game.status == "finished":
        raise HTTPException(status_code=400, detail="对局已结束，无需退出")

    agent = _auth(session, game_id, token)
    faction = agent.faction

    slot = session.exec(
        select(SlotModel).where(SlotModel.game_id == game_id, SlotModel.faction == faction)
    ).first()

    # Invalidate session
    sess = session.get(SessionModel, token)
    if sess:
        sess.status = "kicked"
        session.add(sess)

    # ── lobby / countdown: simple cancel ──────────────────
    if game.status in ("lobby", "countdown"):
        if slot:
            slot.status = "open"
            slot.session_token = None
            slot.ready = False
            slot.ready_at = None
            slot.joined_at = None
            slot.last_heartbeat_at = None
            slot.occupied_by_ip = None
            slot.agent_display_name = None
            session.add(slot)

        agent.is_active = False
        agent.deactivated_at = datetime.now(timezone.utc).isoformat()
        agent.deactivated_reason = "cancelled_join"
        session.add(agent)
        session.commit()

        # Cancel countdown if this was the 3rd player leaving
        if game.status == "countdown":
            lobby._check_all_ready(session, game_id)

        return {
            "status": "ok",
            "redirect_to": "/",
            "context": "cancelled_join",
        }

    # ── active / paused ───────────────────────────────────
    if game.status in ("active", "paused"):
        cities = session.exec(select(eng.City).where(eng.City.game_id == game_id)).all()
        city_count = sum(1 for c in cities if c.owner == faction)

        if city_count > 0:
            # Still alive → AI takeover
            if slot:
                slot.status = "ai_managed"
                slot.session_token = None
                slot.ready = True
                slot.ready_at = datetime.now(timezone.utc).isoformat()
                slot.agent_display_name = f"托管AI-{faction}"
                session.add(slot)

            agent.is_active = False
            agent.deactivated_at = datetime.now(timezone.utc).isoformat()
            agent.deactivated_reason = "player_quit_active"
            session.add(agent)
            session.commit()

            # Create managed AI to take over
            eng._ensure_managed_for_open_slots(session, game_id)

            # Trigger initial decision for the new managed agent
            try:
                managed = session.exec(
                    select(Agent).where(
                        Agent.game_id == game_id,
                        Agent.faction == faction,
                        Agent.agent_mode == "managed",
                        Agent.is_active == True,
                    )
                ).first()
                if managed:
                    eng.auto_decide_managed(session, game_id, managed)
            except Exception:
                pass

            return {
                "status": "ok",
                "redirect_to": "/",
                "context": "ai_taken_over",
            }
        else:
            # Eliminated → exiled
            if slot:
                slot.status = "exiled"
                slot.ready = False
                session.add(slot)

            agent.is_active = False
            agent.deactivated_at = datetime.now(timezone.utc).isoformat()
            agent.deactivated_reason = "player_exiled"
            session.add(agent)
            session.commit()

            # Look up battle_id for redirect
            bh = session.exec(
                select(BattleHistory).where(BattleHistory.game_id == game_id)
            ).first()
            battle_id = bh.battle_id if bh else None

            return {
                "status": "ok",
                "redirect_to": f"/battles/{battle_id}" if battle_id else "/battles",
                "context": "exiled_viewing_battle",
                "battle_id": battle_id,
            }

    raise HTTPException(status_code=400, detail="无法退出当前对局状态")


# ═══════════════════════════════════════════════════════════════
# 公开战报 — /v1/games/{game_id}/result
# ═══════════════════════════════════════════════════════════════

@app.get("/v1/games/{game_id}/result")
def game_result(game_id: int, session: Session = Depends(get_session)):
    """对局赛果摘要 —— 无需 token，对局结束后永久可匿名访问。"""
    import json
    from datetime import datetime, timezone
    from collections import defaultdict
    from .engine import PUBLIC_LOG_DIR

    game = session.get(Game, game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="对局不存在")
    if game.status != "finished":
        raise HTTPException(status_code=425, detail="对局仍在进行中")

    FACTION_LIST = ["蜀", "魏", "吴"]

    # ── 加载 public log ticks ──────────────────────────────
    log_path = PUBLIC_LOG_DIR / f"{game_id}.jsonl"
    ticks: list[dict] = []
    if log_path.exists():
        try:
            for line in log_path.read_text(encoding="utf-8").strip().split("\n"):
                if not line:
                    continue
                ticks.append(json.loads(line))
        except Exception:
            pass

    # ── final_cities: finished → DB City 表（末态精确） ────
    final_cities: list[dict] = []
    db_cities = session.exec(select(City).where(City.game_id == game_id)).all()
    final_cities = [
        {"name": c.name, "owner": c.owner, "troops": c.troops}
        for c in db_cities
    ]

    # ── winner_reason ──────────────────────────────────────
    winner_reason = _compute_winner_reason(game, final_cities)

    # ── faction_stats ──────────────────────────────────────
    faction_stats = _compute_faction_stats(ticks, final_cities, FACTION_LIST)

    # ── key_events ─────────────────────────────────────────
    key_events = _extract_key_events(ticks)

    # ── duration_sec ───────────────────────────────────────
    duration_sec = None
    if game.started_at and game.finished_at:
        try:
            started = datetime.fromisoformat(game.started_at)
            finished = datetime.fromisoformat(game.finished_at)
            duration_sec = int((finished - started).total_seconds())
        except Exception:
            pass

    return {
        "game_id": game.id,
        "winner": game.winner,
        "winner_reason": winner_reason,
        "tick_finished": game.tick,
        "duration_sec": duration_sec,
        "final_cities": final_cities,
        "faction_stats": faction_stats,
        "key_events": key_events,
    }


# ── Helper: winner_reason ──────────────────────────────────

def _compute_winner_reason(game, final_cities: list[dict]) -> str:
    if not game.winner:
        return "对局中止"
    owners = {c["owner"] for c in final_cities if c.get("owner") is not None}
    if len(owners) == 1:
        return "统一中原"
    from collections import defaultdict
    fc: dict[str, int] = defaultdict(int)
    ft: dict[str, int] = defaultdict(int)
    for c in final_cities:
        o = c.get("owner")
        if o:
            fc[o] += 1
            ft[o] += c.get("troops", 0)
    if not fc:
        return "胜负判定"
    max_cities = max(fc.values())
    top_factions = [f for f, n in fc.items() if n == max_cities]
    if len(top_factions) == 1 and top_factions[0] == game.winner:
        return "疆域优势"
    if game.winner in top_factions:
        w_troops = ft[game.winner]
        other_max = max((t for f, t in ft.items() if f != game.winner and f in top_factions), default=0)
        if w_troops > other_max:
            return "兵力优势"
    return "胜负判定"


# ── Helper: faction_stats ─────────────────────────────────

def _compute_faction_stats(ticks: list[dict], final_cities: list[dict], factions: list[str]) -> dict:
    from collections import defaultdict
    stats: dict = {f: {"final_cities": 0, "peak_cities": 0, "kills": 0.0, "losses": 0.0} for f in factions}

    for t in ticks:
        # peak_cities: count cities owned per tick
        tick_owned: dict[str, int] = defaultdict(int)
        for c in t.get("cities", []):
            o = c.get("owner")
            if o and o in factions:
                tick_owned[o] += 1
        for f in factions:
            if tick_owned[f] > stats[f]["peak_cities"]:
                stats[f]["peak_cities"] = tick_owned[f]

        # kills/losses from combat reports
        for evt in t.get("events", []):
            attackers = evt.get("attackers")
            if not attackers:
                continue
            cr = evt.get("combat_report")
            if not cr:
                continue
            try:
                def_loss = int(cr["defender_losses"])
                atk_loss = int(cr["attacker_losses"])
            except (KeyError, TypeError, ValueError):
                continue
            defender = evt.get("defender", "")
            n = max(len(attackers), 1)
            for atk in attackers:
                if atk in stats:
                    stats[atk]["kills"] += def_loss / n
                    stats[atk]["losses"] += atk_loss / n
            if defender in stats:
                stats[defender]["kills"] += atk_loss
                stats[defender]["losses"] += def_loss

    # final_cities from end-of-game state
    for c in final_cities:
        o = c.get("owner")
        if o and o in stats:
            stats[o]["final_cities"] += 1

    for f in factions:
        stats[f]["kills"] = round(stats[f]["kills"])
        stats[f]["losses"] = round(stats[f]["losses"])

    return stats


# ── Helper: key_events ────────────────────────────────────

def _extract_key_events(ticks: list[dict]) -> list[dict]:
    captured: list[dict] = []
    alliances: list[dict] = []
    battles: list[dict] = []

    for t in ticks:
        tick = t.get("tick", 0)

        for evt in t.get("events", []):
            result = evt.get("result", "")
            cr = evt.get("combat_report", {}) or {}
            troops = cr.get("attacker_troops_committed", 0)
            is_big = isinstance(troops, (int, float)) and troops >= 500

            if result == "captured":
                cb = evt.get("captured_by", "")
                city = evt.get("city", "")
                captured.append({
                    "tick": tick,
                    "event": f"{cb}占领{city}",
                    "significance": "high",
                })
            elif is_big:
                atk_str = "、".join(evt.get("attackers", []))
                city = evt.get("city", "")
                df = evt.get("defender", "")
                battles.append({
                    "tick": tick,
                    "event": f"大战{city}: {atk_str}攻{df} ({troops}兵)",
                    "significance": "medium",
                })

        for dip in t.get("diplomacy", []):
            d_type = dip.get("diplomacy_type", "")
            ff = dip.get("from_faction", "")
            if d_type == "alliance_accept":
                alliances.append({"tick": tick, "event": f"联盟成立: {ff}", "significance": "medium"})
            elif d_type == "alliance_break":
                alliances.append({"tick": tick, "event": f"盟约破裂: {ff}", "significance": "high"})

    # Priority: captured + alliances first, then fill with big battles to 30
    result = captured + alliances
    remaining = max(0, 30 - len(result))
    result += battles[:remaining]
    result.sort(key=lambda e: e["tick"])
    return result[:30]


# ═══════════════════════════════════════════════════════════════
# 评书接口 — 四种状态: not_started / generating / ready / failed
# ═══════════════════════════════════════════════════════════════

@app.get("/v1/games/{game_id}/commentary")
def game_commentary(game_id: int, session: Session = Depends(get_session)):
    """Return full battle commentary. Status discriminated by commentary_status."""
    game = session.get(Game, game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="对局不存在")
    if game.status != "finished":
        raise HTTPException(status_code=425, detail="Game still in progress")

    bh = session.exec(
        select(BattleHistory).where(BattleHistory.game_id == game_id)
    ).first()

    # ── ready ──────────────────────────────────────────────
    if bh and bh.commentary_status == "ready" and bh.commentary_content:
        return PlainTextResponse(content=bh.commentary_content, media_type="text/plain; charset=utf-8")

    # ── generating (with timeout detection) ─────────────────
    if bh and bh.commentary_status == "generating":
        if bh.commentary_started_at:
            try:
                from datetime import datetime, timezone
                started = datetime.fromisoformat(bh.commentary_started_at)
                elapsed = (datetime.now(timezone.utc) - started).total_seconds()
                if elapsed > 600:
                    bh.commentary_status = "failed"
                    bh.last_error = "生成超时"
                    session.add(bh)
                    session.commit()
                    # fall through to failed
                else:
                    return JSONResponse(status_code=202, content={
                        "detail": "评书正在生成中，请稍后再试",
                        "retry_after_sec": 60,
                    })
            except Exception:
                pass
        return JSONResponse(status_code=202, content={
            "detail": "评书正在生成中，请稍后再试",
            "retry_after_sec": 60,
        })

    # ── failed ─────────────────────────────────────────────
    if bh and bh.commentary_status == "failed":
        return JSONResponse(status_code=200, content={
            "error_code": "COMMENTARY_FAILED",
            "detail": "评书生成失败",
            "last_error": bh.last_error or "未知错误",
        })

    # ── not_started (default) ──────────────────────────────
    return JSONResponse(status_code=200, content={
        "error_code": "COMMENTARY_NOT_STARTED",
        "detail": "本对局尚无评书",
    })


@app.post("/v1/games/{game_id}/commentary/generate")
def trigger_commentary_generation(
    game_id: int,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
):
    """Trigger background commentary generation. Idempotent — 409 if already generating/ready."""
    from datetime import datetime, timezone

    game = session.get(Game, game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="对局不存在")
    if game.status != "finished":
        raise HTTPException(status_code=425, detail="对局未结束，无法生成评书")

    bh = session.exec(
        select(BattleHistory).where(BattleHistory.game_id == game_id)
    ).first()

    if bh and bh.commentary_status == "generating":
        raise HTTPException(status_code=409, detail="评书生成中，请等待")
    if bh and bh.commentary_status == "ready":
        raise HTTPException(status_code=409, detail="评书已存在，如需重新生成请联系管理员")

    # Create BattleHistory if not exists (edge case: game finished without lobby flow)
    if not bh:
        bh = BattleHistory(
            game_id=game_id,
            model="pvp",
            winner=game.winner,
            total_ticks=game.tick,
            status=game.status,
        )
        session.add(bh)
        session.commit()

    bh.commentary_status = "generating"
    bh.commentary_started_at = datetime.now(timezone.utc).isoformat()
    session.add(bh)
    session.commit()

    from .narrator import generate_full_commentary
    background_tasks.add_task(generate_full_commentary, game_id)

    return JSONResponse(status_code=202, content={
        "message": "开始生成评书",
        "retry_after_sec": 60,
    })


@app.get("/v1/games/{game_id}/replay")
def game_replay(game_id: int, session: Session = Depends(get_session)):
    """Return full per-tick public state for spectate — single source of truth."""
    import json

    game = session.get(Game, game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="对局不存在")

    from .engine import PUBLIC_LOG_DIR, build_public_factions
    log_path = PUBLIC_LOG_DIR / f"{game_id}.jsonl"

    ticks: list[dict] = []
    if log_path.exists():
        try:
            for line in log_path.read_text(encoding="utf-8").strip().split("\n"):
                if not line:
                    continue
                entry = json.loads(line)
                ticks.append({
                    "tick": entry.get("tick"),
                    "cities": entry.get("cities", []),
                    "events": entry.get("events", []),
                    "diplomacy": entry.get("diplomacy", []),
                })
        except Exception:
            pass

    agents = session.exec(
        select(Agent).where(Agent.game_id == game_id, Agent.is_active == True)
    ).all()
    agent_info = [{"name": a.agent_name, "faction": a.faction, "mode": a.agent_mode} for a in agents]

    cities = session.exec(select(City).where(City.game_id == game_id)).all()

    return {
        "game_id": game.id,
        "status": game.status,
        "winner": game.winner,
        "max_ticks": game.max_ticks,
        "total_ticks": len(ticks),
        "chapters": json.loads(game.chapters) if game.chapters else [],
        "ticks": ticks,
        "agents": agent_info,
        "factions": build_public_factions(game, cities) if cities else {},
    }


# ═══════════════════════════════════════════════════════════════
# Vite SPA (only frontend)
# ═══════════════════════════════════════════════════════════════

_v2_dist = Path(__file__).parent.parent / "frontend-v2" / "dist"


# ── Legacy /v2/* → 301 to new paths ──────────────────────
@app.get("/v2/lobby")
async def redirect_v2_lobby():
    from starlette.responses import RedirectResponse
    return RedirectResponse(url="/", status_code=301)


@app.get("/v2/spectate")
async def redirect_v2_spectate():
    from starlette.responses import RedirectResponse
    return RedirectResponse(url="/spectate", status_code=301)


@app.get("/v2/{path:path}")
async def redirect_v2_other(path: str):
    from starlette.responses import RedirectResponse
    return RedirectResponse(url="/", status_code=301)


@app.get("/v2")
async def redirect_v2_index():
    from starlette.responses import RedirectResponse
    return RedirectResponse(url="/", status_code=301)


# ═══════════════════════════════════════════════════════════════
# SPA catch-all — must be LAST to avoid hijacking API routes
# ═══════════════════════════════════════════════════════════════

@app.get("/{path:path}")
async def spa_catch_all(path: str):
    file_path = _v2_dist / path
    if file_path.is_file():
        return FileResponse(file_path)
    return FileResponse(_v2_dist / "index.html")

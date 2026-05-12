from contextlib import asynccontextmanager
import os
from fastapi import FastAPI, Depends, HTTPException, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import FileResponse
from sqlmodel import Session, select
from pathlib import Path

from .database import init_db, get_session
from .models import Agent, BattleHistory, BattleLogFile
from . import engine as eng
from .admin import router as admin_router
from .public import router as public_router

import json

templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))

# Disable Jinja2 bytecode cache to work around Starlette's unhashable request context
templates.env.cache = None


@asynccontextmanager
async def lifespan(application: FastAPI):
    init_db()
    yield


app = FastAPI(title="三国 AI Agent 竞技平台", lifespan=lifespan)

# CORS — allow GitHub Pages and other frontend origins to call the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册 API 路由
app.include_router(admin_router)
app.include_router(public_router)

# 静态文件 (SPA 前端) — routes take priority, static is fallback
static_dir = Path(__file__).parent.parent / "static"


# ── 首页 — 返回 SPA ─────────────────────────────────────
@app.get("/")
def root():
    spa_index = static_dir / "index.html"
    if spa_index.is_file():
        return FileResponse(spa_index)
    from starlette.responses import RedirectResponse
    return RedirectResponse(url="/public")


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

    body = await request.json()

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


# ═══════════════════════════════════════════════════════════════
# 运营后台页面
# ═══════════════════════════════════════════════════════════════

ADMIN_TOKEN = __import__("os").environ.get("ADMIN_TOKEN", "admin-dev-token")


def _check_admin(request: Request):
    token = request.headers.get("X-Admin-Token", "") or request.query_params.get("token", "")
    if token != ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="未授权")
    return token


@app.get("/admin")
def admin_page(
    request: Request,
    page: int = Query(1, ge=1),
    model: str = Query(""),
    winner: str = Query(""),
    token: str = Query(""),
    session: Session = Depends(get_session),
):
    # Check auth — if no valid token, show login page
    if not token or token != ADMIN_TOKEN:
        if token:
            raise HTTPException(status_code=401, detail="token 无效")
        return templates.TemplateResponse(request, "admin_login.html", {"request": request})
    _check_admin(request)
    page_size = 20
    stmt = select(BattleHistory)
    if model:
        stmt = stmt.where(BattleHistory.model == model)
    if winner:
        stmt = stmt.where(BattleHistory.winner == winner)
    stmt = stmt.order_by(BattleHistory.battle_id.desc())
    all_battles = session.exec(stmt).all()
    total = len(all_battles)
    offset = (page - 1) * page_size
    battles = all_battles[offset:offset + page_size]
    total_pages = (total + page_size - 1) // page_size if total > 0 else 1
    models = list(set(b.model for b in session.exec(select(BattleHistory)).all()))

    return templates.TemplateResponse(request, "admin_battles.html", {
        "admin_token": token,
        "battles": [
            {
                "battle_id": b.battle_id,
                "game_id": b.game_id,
                "model": b.model,
                "created_at": b.created_at,
                "winner": b.winner,
                "total_ticks": b.total_ticks,
                "status": b.status,
                "has_commentary": b.has_commentary,
            }
            for b in battles
        ],
        "page": page,
        "total_pages": total_pages,
        "models": models,
        "current_model": model,
        "current_winner": winner,
    })


@app.get("/admin/battles/{battle_id}")
def admin_battle_detail(
    battle_id: int,
    request: Request,
    tab: str = Query("overview"),
    session: Session = Depends(get_session),
):
    token = _check_admin(request)
    bh = session.get(BattleHistory, battle_id)
    if not bh:
        raise HTTPException(status_code=404, detail="对局不存在")

    log_files = session.exec(
        select(BattleLogFile).where(BattleLogFile.battle_id == battle_id)
    ).all()

    battle_data = None
    power_curve = []
    ticks = []
    battle_log_file = next((lf for lf in log_files if lf.file_type == "battle_log"), None)
    if battle_log_file and Path(battle_log_file.file_path).exists():
        try:
            raw = Path(battle_log_file.file_path).read_text(encoding="utf-8")
            battle_data = json.loads(raw)
            power_curve = battle_data.get("power_curve", [])
            for t in battle_data.get("ticks", []):
                ticks.append({
                    "tick": t.get("tick"),
                    "cities": t.get("cities", []),
                    "events": t.get("events", []),
                    "diplomacy": t.get("diplomacy", []),
                    "attack_intentions": t.get("attack_intentions", []),
                    "agent_actions": t.get("agent_actions", []),
                })
        except Exception:
            pass

    commentary = ""
    if bh.has_commentary and tab == "commentary":
        cf = next((lf for lf in log_files if lf.file_type == "commentary"), None)
        if cf and Path(cf.file_path).exists():
            commentary = Path(cf.file_path).read_text(encoding="utf-8")

    summary = json.loads(bh.summary) if bh.summary else None

    return templates.TemplateResponse(request, "admin_battle_detail.html", {
        "admin_token": token,
        "battle": {
            "battle_id": bh.battle_id,
            "game_id": bh.game_id,
            "model": bh.model,
            "created_at": bh.created_at,
            "winner": bh.winner,
            "total_ticks": bh.total_ticks,
            "status": bh.status,
            "has_commentary": bh.has_commentary,
            "summary": summary,
        },
        "tab": tab,
        "ticks": ticks,
        "power_curve": power_curve,
        "log_files": [{"file_path": lf.file_path, "file_type": lf.file_type, "agent_name": lf.agent_name} for lf in log_files],
        "commentary": commentary,
    })


# ═══════════════════════════════════════════════════════════════
# 公开页面
# ═══════════════════════════════════════════════════════════════

@app.get("/public")
def public_page(
    request: Request,
    page: int = Query(1, ge=1),
    session: Session = Depends(get_session),
):
    page_size = 12
    stmt = select(BattleHistory).order_by(BattleHistory.battle_id.desc())
    all_battles = session.exec(stmt).all()
    total = len(all_battles)
    offset = (page - 1) * page_size
    battles = all_battles[offset:offset + page_size]
    total_pages = (total + page_size - 1) // page_size if total > 0 else 1

    # Stats
    faction_wins: dict[str, int] = {}
    for b in all_battles:
        if b.winner:
            faction_wins[b.winner] = faction_wins.get(b.winner, 0) + 1

    return templates.TemplateResponse(request, "public_battles.html", {
        "battles": [
            {
                "battle_id": b.battle_id,
                "game_id": b.game_id,
                "model": b.model,
                "created_at": b.created_at,
                "winner": b.winner,
                "total_ticks": b.total_ticks,
                "status": b.status,
                "has_commentary": b.has_commentary,
            }
            for b in battles
        ],
        "page": page,
        "total_pages": total_pages,
        "stats": {
            "total_battles": total,
            "faction_wins": faction_wins,
        },
    })


@app.get("/public/battles/{battle_id}")
def public_battle_detail(
    battle_id: int,
    request: Request,
    session: Session = Depends(get_session),
):
    bh = session.get(BattleHistory, battle_id)
    if not bh:
        raise HTTPException(status_code=404, detail="对局不存在")

    log_files = session.exec(
        select(BattleLogFile).where(BattleLogFile.battle_id == battle_id)
    ).all()

    battle_data = None
    power_curve = []
    ticks = []
    battle_log_file = next((lf for lf in log_files if lf.file_type == "battle_log"), None)
    if battle_log_file and Path(battle_log_file.file_path).exists():
        try:
            raw = Path(battle_log_file.file_path).read_text(encoding="utf-8")
            battle_data = json.loads(raw)
            power_curve = battle_data.get("power_curve", [])
            for t in battle_data.get("ticks", []):
                ticks.append({
                    "tick": t.get("tick"),
                    "cities": t.get("cities", []),
                    "events": t.get("events", []),
                    "diplomacy": t.get("diplomacy", []),
                    "attack_intentions": t.get("attack_intentions", []),
                    "agent_actions": t.get("agent_actions", []),
                })
        except Exception:
            pass

    # private_thoughts：仅 finished 时加载
    private_thoughts = {}
    if bh.status in ("finished", "max_ticks"):
        for lf in log_files:
            if lf.file_type == "private_thoughts" and lf.agent_name:
                path = Path(lf.file_path)
                if path.exists():
                    try:
                        thoughts = []
                        for line in path.read_text(encoding="utf-8").strip().split("\n"):
                            if line.strip():
                                entry = json.loads(line)
                                thoughts.append({
                                    "tick": entry.get("tick"),
                                    "private_thought": entry.get("private_thought", ""),
                                })
                        private_thoughts[lf.agent_name] = thoughts
                    except Exception:
                        pass

    return templates.TemplateResponse(request, "public_battle_detail.html", {
        "battle": {
            "battle_id": bh.battle_id,
            "game_id": bh.game_id,
            "model": bh.model,
            "created_at": bh.created_at,
            "winner": bh.winner,
            "total_ticks": bh.total_ticks,
            "status": bh.status,
            "has_commentary": bh.has_commentary,
        },
        "ticks": ticks,
        "power_curve": power_curve,
        "private_thoughts": private_thoughts,
    })


@app.get("/public/battles/{battle_id}/commentary")
def public_commentary_page(
    battle_id: int,
    request: Request,
    session: Session = Depends(get_session),
):
    bh = session.get(BattleHistory, battle_id)
    if not bh:
        raise HTTPException(status_code=404, detail="对局不存在")

    lf = session.exec(
        select(BattleLogFile).where(
            BattleLogFile.battle_id == battle_id, BattleLogFile.file_type == "commentary"
        )
    ).first()

    commentary = ""
    if lf and Path(lf.file_path).exists():
        commentary = Path(lf.file_path).read_text(encoding="utf-8")

    # Return as plain text or simple HTML
    from fastapi.responses import HTMLResponse
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>评书解说 - 对战 #{battle_id}</title>
<style>
  body {{ background:#1a1410; color:#c8b89a; font-family:"SimSun","STSong",serif; padding:40px; line-height:2; max-width:800px; margin:0 auto; }}
  h1 {{ color:#d4a84b; letter-spacing:4px; }}
  a {{ color:#b8960a; }}
  .content {{ background:#1f1710; padding:30px; border:1px solid #3a2a1a; margin-top:20px; white-space:pre-wrap; }}
</style>
</head>
<body>
  <a href="/public/battles/{battle_id}">← 返回对战详情</a>
  <h1>📖 评书解说</h1>
  <div class="content">{commentary}</div>
</body>
</html>"""
    return HTMLResponse(content=html)


@app.get("/admin/stats")
def admin_stats_page(
    request: Request,
    session: Session = Depends(get_session),
):
    _check_admin(request)
    from fastapi.responses import HTMLResponse
    battles = session.exec(select(BattleHistory)).all()
    model_stats: dict[str, dict] = {}
    faction_wins: dict[str, int] = {}
    total_ticks = 0
    for b in battles:
        m = b.model
        if m not in model_stats:
            model_stats[m] = {"total": 0, "wins": 0, "max_ticks": 0, "errors": 0}
        model_stats[m]["total"] += 1
        if b.status == "finished" and b.winner:
            model_stats[m]["wins"] += 1
            faction_wins[b.winner] = faction_wins.get(b.winner, 0) + 1
        elif b.status == "max_ticks":
            model_stats[m]["max_ticks"] += 1
        elif b.status == "error":
            model_stats[m]["errors"] += 1
        total_ticks += b.total_ticks

    avg_ticks = total_ticks / len(battles) if battles else 0

    rows = ""
    for m, s in model_stats.items():
        wr = f"{s['wins']/s['total']*100:.0f}%" if s['total'] > 0 else "0%"
        rows += f"<tr><td>{m}</td><td>{s['total']}</td><td>{s['wins']}</td><td>{wr}</td><td>{s['max_ticks']}</td><td>{s['errors']}</td></tr>"

    fw_rows = ""
    for f, c in sorted(faction_wins.items()):
        color = {"蜀": "#e04444", "魏": "#4488e0", "吴": "#44a044"}.get(f, "#c8b89a")
        fw_rows += f'<div style="color:{color};font-size:18px;">{f}: {c} 胜</div>'

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8"><title>统计面板 - 运营后台</title>
<style>
  body {{ background:#1a1410; color:#c8b89a; font-family:"SimSun",serif; padding:40px; max-width:900px; margin:0 auto; }}
  h1 {{ color:#d4a84b; letter-spacing:4px; }}
  a {{ color:#b8960a; }}
  table {{ width:100%; border-collapse:collapse; margin:20px 0; }}
  th {{ background:#2a1f14; padding:10px; text-align:left; border-bottom:2px solid #3a2a1a; }}
  td {{ padding:10px; border-bottom:1px solid #221a10; }}
  .card {{ background:#1f1710; border:1px solid #3a2a1a; padding:20px; margin:20px 0; }}
  .big {{ font-size:32px; color:#d4a84b; }}
</style>
</head>
<body>
<a href="/admin">← 返回列表</a>
<h1>📊 统计面板</h1>
<div class="card">
  <div class="big">{len(battles)} 场对局 · 平均 {avg_ticks:.1f} 回合</div>
  <div style="margin-top:15px;display:flex;gap:30px;">{fw_rows}</div>
</div>
<h2>模型统计</h2>
<table>
  <tr><th>模型</th><th>总局数</th><th>胜场</th><th>胜率</th><th>超时</th><th>错误</th></tr>
  {rows}
</table>
</body>
</html>"""
    return HTMLResponse(content=html)


# ═══════════════════════════════════════════════════════════════
# PvP Arena — 对战大厅 API
# ═══════════════════════════════════════════════════════════════


@app.get("/lobby")
def lobby_list(session: Session = Depends(get_session)):
    return {"games": eng.lobby_list_games(session)}


@app.post("/games/create")
def pvp_create_game(body: dict, session: Session = Depends(get_session)):
    try:
        result = eng.pvp_create_game(
            session,
            title=body.get("title"),
            player_id=body.get("player_id"),
            host_name=body.get("agent_name", "房主"),
            host_faction=body.get("faction"),
            host_persona=body.get("persona"),
            max_ticks=body.get("max_ticks", 35),
            tick_timeout_sec=body.get("tick_timeout_sec", 60),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return result


@app.post("/games/{game_id}/join-managed")
def pvp_join_managed(
    game_id: int,
    body: dict,
    session: Session = Depends(get_session),
):
    try:
        token, faction, gid = eng.pvp_join_managed(
            session, game_id,
            player_id=body.get("player_id"),
            agent_name=body["agent_name"],
            faction=body["faction"],
            llm_config=body.get("llm_config"),
            persona=body.get("persona"),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"token": token, "faction": faction, "game_id": gid}


@app.post("/games/{game_id}/join-selfhosted")
def pvp_join_selfhosted(
    game_id: int,
    body: dict,
    session: Session = Depends(get_session),
):
    try:
        token, gid = eng.pvp_join_selfhosted(
            session, game_id,
            agent_id=body["agent_id"],
            secret=body["secret"],
            faction=body["faction"],
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"token": token, "game_id": gid, "agent_id": body["agent_id"]}


@app.post("/join/{game_id}")
def quick_join(
    game_id: int,
    body: dict,
    request: Request,
    session: Session = Depends(get_session),
):
    """One-click join: auto-register + auto-join as managed agent.
    No API keys needed — server uses default LLM provider."""
    host = request.headers.get("host", "")
    base_url = f"http://{host}" if host else os.environ.get("BASE_URL", "http://localhost:8000")

    # Managed mode (default): server handles LLM for the agent
    mode = body.get("mode", "managed")
    name = body.get("name", "神秘武将")
    faction = body.get("faction")

    if not faction or faction not in ["蜀", "魏", "吴"]:
        raise HTTPException(status_code=400, detail="faction must be 蜀/魏/吴")

    try:
        if mode == "self_hosted":
            # Legacy self-hosted path
            token, faction, gid, curl_state, curl_action = eng.quick_join(
                session, game_id, name, faction, base_url=base_url
            )
            return {
                "token": token, "faction": faction, "game_id": gid,
                "curl_state": curl_state, "curl_action": curl_action,
                "mode": "self_hosted",
            }
        else:
            # Managed mode: server handles decisions
            token, faction, gid = eng.pvp_join_managed(
                session, game_id,
                player_id=body.get("player_id"),
                agent_name=name,
                faction=faction,
                llm_config=body.get("llm_config"),  # optional
                persona=body.get("persona"),         # optional
            )
            invite_url = f"{base_url}/?tab=arena&join={gid}"
            return {
                "token": token, "faction": faction, "game_id": gid,
                "mode": "managed",
                "invite_url": invite_url,
            }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.put("/games/{game_id}/agent/{token}/config")
def update_agent_config(
    game_id: int,
    token: str,
    body: dict,
    session: Session = Depends(get_session),
):
    agent = _auth(session, game_id, token)
    if body.get("persona"):
        agent.persona_config = body["persona"]
    if body.get("llm_config"):
        agent.llm_config = json.dumps(body["llm_config"], ensure_ascii=False)
    session.add(agent)
    session.commit()
    return {"msg": "配置已更新"}


@app.post("/games/{game_id}/start")
def pvp_start_game(
    game_id: int,
    body: dict,
    session: Session = Depends(get_session),
):
    try:
        result = eng.pvp_start_game(session, game_id, token=body["token"])
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return result


@app.get("/games/{game_id}/live")
def pvp_live_game(
    game_id: int,
    session: Session = Depends(get_session),
):
    try:
        return eng.live_game_state(session, game_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/my-games")
def my_games(
    player_id: str,
    session: Session = Depends(get_session),
):
    return {"games": eng.my_games(session, player_id)}


@app.post("/games/{game_id}/surrender")
def pvp_surrender(
    game_id: int,
    body: dict,
    session: Session = Depends(get_session),
):
    try:
        return eng.surrender_agent(session, game_id, token=body["token"])
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ═══════════════════════════════════════════════════════════════
# 静态资源回退 — 服务 SPA 的 CSS/JSX 等文件
# ═══════════════════════════════════════════════════════════════

@app.get("/{filename:path}")
async def serve_static(filename: str):
    """Fallback: serve static files (CSS, JSX, etc.) that don't match any route."""
    file_path = static_dir / filename
    if file_path.is_file() and file_path.suffix in (".css", ".jsx", ".js", ".html", ".json", ".png", ".svg", ".ico", ".txt"):
        return FileResponse(file_path)
    raise HTTPException(status_code=404)

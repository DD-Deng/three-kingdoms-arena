"""运营后台 API —— 需要 X-Admin-Token header 鉴权"""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import JSONResponse
from sqlmodel import Session, select

from .database import get_session
from .models import BattleHistory, BattleLogFile, Game, Agent as AgentModel, City, Action

router = APIRouter(prefix="/api/admin", tags=["admin"])

ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "admin-dev-token")
LOG_DIR = Path("logs")


def _check_auth(request: Request):
    token = request.headers.get("X-Admin-Token", "") or request.query_params.get("token", "")
    if token != ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="未授权：X-Admin-Token 无效")
    return True


# ── GET /admin/battles ──────────────────────────────────────────

@router.get("/battles")
def list_battles(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    model: str | None = None,
    winner: str | None = None,
    date_from: str | None = None,
    session: Session = Depends(get_session),
):
    _check_auth(request)
    stmt = select(BattleHistory)
    if model:
        stmt = stmt.where(BattleHistory.model == model)
    if winner:
        stmt = stmt.where(BattleHistory.winner == winner)
    if date_from:
        stmt = stmt.where(BattleHistory.created_at >= date_from)
    stmt = stmt.order_by(BattleHistory.battle_id.desc())  # type: ignore[arg-type]

    total = len(session.exec(stmt).all())
    offset = (page - 1) * page_size
    battles = session.exec(stmt.offset(offset).limit(page_size)).all()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
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
                "summary": json.loads(b.summary) if b.summary else None,
            }
            for b in battles
        ],
    }


# ── GET /admin/battles/{battle_id} ──────────────────────────────

@router.get("/battles/{battle_id}")
def get_battle(
    battle_id: int,
    request: Request,
    session: Session = Depends(get_session),
):
    _check_auth(request)
    bh = session.get(BattleHistory, battle_id)
    if not bh:
        raise HTTPException(status_code=404, detail="对局不存在")

    log_files = session.exec(
        select(BattleLogFile).where(BattleLogFile.battle_id == battle_id)
    ).all()

    # 读取 battle_log JSON
    battle_data = None
    power_curve = []
    battle_log_file = next((lf for lf in log_files if lf.file_type == "battle_log"), None)
    if battle_log_file and Path(battle_log_file.file_path).exists():
        try:
            raw = Path(battle_log_file.file_path).read_text(encoding="utf-8")
            battle_data = json.loads(raw)
            power_curve = battle_data.get("power_curve", [])
        except Exception:
            pass

    # 构建 agent 日志列表
    agent_logs = {}
    for lf in log_files:
        if lf.file_type == "jsonl" and lf.agent_name:
            path = Path(lf.file_path)
            if path.exists():
                lines = []
                try:
                    for line in path.read_text(encoding="utf-8").strip().split("\n"):
                        if line.strip():
                            lines.append(json.loads(line))
                except Exception:
                    pass
                agent_logs[lf.agent_name] = {
                    "file_type": "jsonl",
                    "tick_count": len(lines),
                    "calls": lines,
                }

    # 构建 action 数据（从 battle_data ticks 中提取）
    ticks = []
    if battle_data:
        for t in battle_data.get("ticks", []):
            tick_entry = {
                "tick": t.get("tick"),
                "cities": t.get("cities", []),
                "events": t.get("events", []),
                "diplomacy": t.get("diplomacy", []),
                "attack_intentions": t.get("attack_intentions", []),
                "agent_actions": t.get("agent_actions", []),
            }
            ticks.append(tick_entry)

    return {
        "battle_id": bh.battle_id,
        "game_id": bh.game_id,
        "model": bh.model,
        "created_at": bh.created_at,
        "winner": bh.winner,
        "total_ticks": bh.total_ticks,
        "status": bh.status,
        "has_commentary": bh.has_commentary,
        "summary": json.loads(bh.summary) if bh.summary else None,
        "power_curve": power_curve,
        "ticks": ticks,
        "log_files": [
            {
                "id": lf.id,
                "file_type": lf.file_type,
                "agent_name": lf.agent_name,
                "file_path": lf.file_path,
            }
            for lf in log_files
        ],
    }


# ── GET /admin/battles/{battle_id}/agent/{agent_name} ───────────

@router.get("/battles/{battle_id}/agent/{agent_name}")
def get_agent_logs(
    battle_id: int,
    agent_name: str,
    request: Request,
    session: Session = Depends(get_session),
):
    _check_auth(request)
    bh = session.get(BattleHistory, battle_id)
    if not bh:
        raise HTTPException(status_code=404, detail="对局不存在")

    log_files = session.exec(
        select(BattleLogFile).where(
            BattleLogFile.battle_id == battle_id, BattleLogFile.agent_name == agent_name
        )
    ).all()

    result: dict = {"agent_name": agent_name, "jsonl_calls": [], "private_thoughts": [], "stdout": ""}

    for lf in log_files:
        path = Path(lf.file_path)
        if not path.exists():
            continue
        if lf.file_type == "jsonl":
            try:
                for line in path.read_text(encoding="utf-8").strip().split("\n"):
                    if line.strip():
                        result["jsonl_calls"].append(json.loads(line))
            except Exception:
                pass
        elif lf.file_type == "private_thoughts":
            try:
                for line in path.read_text(encoding="utf-8").strip().split("\n"):
                    if line.strip():
                        result["private_thoughts"].append(json.loads(line))
            except Exception:
                pass
        elif lf.file_type == "stdout":
            try:
                result["stdout"] = path.read_text(encoding="utf-8")
            except Exception:
                pass

    return result


# ── GET /admin/battles/{battle_id}/commentary ───────────────────

@router.get("/battles/{battle_id}/commentary")
def get_commentary(
    battle_id: int,
    request: Request,
    session: Session = Depends(get_session),
):
    _check_auth(request)
    bh = session.get(BattleHistory, battle_id)
    if not bh:
        raise HTTPException(status_code=404, detail="对局不存在")

    lf = session.exec(
        select(BattleLogFile).where(
            BattleLogFile.battle_id == battle_id, BattleLogFile.file_type == "commentary"
        )
    ).first()

    if not lf or not Path(lf.file_path).exists():
        raise HTTPException(status_code=404, detail="评书解说不存在")

    content = Path(lf.file_path).read_text(encoding="utf-8")
    return {"battle_id": battle_id, "commentary": content}


# ── GET /admin/stats ────────────────────────────────────────────

@router.get("/stats")
def admin_stats(
    request: Request,
    session: Session = Depends(get_session),
):
    _check_auth(request)
    battles = session.exec(select(BattleHistory)).all()

    total = len(battles)
    # 按模型胜率
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

    avg_ticks = total_ticks / total if total > 0 else 0

    return {
        "total_battles": total,
        "avg_ticks": round(avg_ticks, 1),
        "model_stats": model_stats,
        "faction_wins": faction_wins,
    }


# ── POST /admin/force-restart ─────────────────────────────────────

@router.post("/force-restart")
def force_restart(
    request: Request,
    confirm: str = Query("no"),
    session: Session = Depends(get_session),
):
    _check_auth(request)
    if confirm != "yes":
        return JSONResponse(
            status_code=400,
            content={"error": "必须传 confirm=yes 才执行", "hint": "?confirm=yes"},
        )

    from . import lobby
    logger = logging.getLogger("admin")

    game = lobby.get_active_game(session)
    if game is None:
        return {"status": "no active game"}

    old_id = game.id

    # Mark finished
    game.status = "finished"
    game.is_active = False
    game.is_current = False
    game.finished_at = datetime.now(timezone.utc).isoformat()
    game.winner = None
    session.add(game)
    session.commit()

    # Run full cleanup + create new game
    lobby.finish_game(session, game)

    new_game = lobby.get_active_game(session)
    new_id = new_game.id if new_game else None

    client_ip = request.headers.get("X-Forwarded-For", request.client.host if request.client else "unknown")
    logger.info(
        f"Admin force-restart: old game {old_id} → new game {new_id}, IP={client_ip}"
    )

    return {
        "status": "ok",
        "old_game_id": old_id,
        "new_game_id": new_id,
        "new_status": new_game.status if new_game else "unknown",
    }

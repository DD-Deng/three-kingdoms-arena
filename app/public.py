"""公开版 API —— 脱敏数据，不暴露 private_thoughts（进行中）和 LLM 日志"""

import json
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select

from .database import get_session
from .models import BattleHistory, BattleLogFile

router = APIRouter(prefix="/api/public", tags=["public"])
LOG_DIR = Path("logs")


# ── GET /public/battles ─────────────────────────────────────────

@router.get("/battles")
def list_battles(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    model: str | None = None,
    winner: str | None = None,
    session: Session = Depends(get_session),
):
    stmt = select(BattleHistory)
    if model:
        stmt = stmt.where(BattleHistory.model == model)
    if winner:
        stmt = stmt.where(BattleHistory.winner == winner)
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
            }
            for b in battles
        ],
    }


# ── GET /public/battles/{battle_id} ─────────────────────────────

@router.get("/battles/{battle_id}")
def get_battle(
    battle_id: int,
    session: Session = Depends(get_session),
):
    bh = session.get(BattleHistory, battle_id)
    if not bh:
        raise HTTPException(status_code=404, detail="对局不存在")

    # 读取 battle_log JSON 获取原始数据
    log_files = session.exec(
        select(BattleLogFile).where(BattleLogFile.battle_id == battle_id)
    ).all()

    battle_log_file = next((lf for lf in log_files if lf.file_type == "battle_log"), None)
    battle_data = None
    if battle_log_file and Path(battle_log_file.file_path).exists():
        try:
            raw = Path(battle_log_file.file_path).read_text(encoding="utf-8")
            battle_data = json.loads(raw)
        except Exception:
            pass

    is_finished = bh.status in ("finished", "max_ticks")

    # 读取 private_thoughts（仅在 finished 时返回）
    private_thoughts = {}
    if is_finished:
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

    # 构建 tick 数据（脱敏版）
    ticks = []
    if battle_data:
        for t in battle_data.get("ticks", []):
            # 公开 tick 数据：不含 agent LLM 日志
            tick_entry = {
                "tick": t.get("tick"),
                "cities": t.get("cities", []),
                "events": t.get("events", []),
                "diplomacy": t.get("diplomacy", []),
                # attack_intentions 不含兵力，可以公开
                "attack_intentions": t.get("attack_intentions", []),
                # agent_actions 只保留摘要，不含具体部队数
                "agent_actions": [_sanitize_action(a) for a in t.get("agent_actions", [])],
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
        "ticks": ticks,
        "private_thoughts": private_thoughts,  # 仅 finished 时非空
    }


def _sanitize_action(act: dict) -> dict:
    """移除攻击的具体兵力数，只保留 direction"""
    a = dict(act)
    as_detail = a.get("action_summary", [])
    sanitized = []
    for s in as_detail:
        import re
        # 移除 attack 中的 (数字兵)
        sanitized.append(re.sub(r"\(\d+兵\)", "(??兵)", s))
    a["action_summary"] = sanitized
    return a


# ── GET /public/battles/{battle_id}/commentary ──────────────────

@router.get("/battles/{battle_id}/commentary")
def get_commentary(
    battle_id: int,
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

    if not lf or not Path(lf.file_path).exists():
        raise HTTPException(status_code=404, detail="评书解说不存在")

    content = Path(lf.file_path).read_text(encoding="utf-8")
    return {"battle_id": battle_id, "commentary": content}


# ── GET /public/stats ───────────────────────────────────────────

@router.get("/stats")
def public_stats(
    session: Session = Depends(get_session),
):
    battles = session.exec(select(BattleHistory).order_by(BattleHistory.battle_id.desc())).all()

    total = len(battles)
    faction_wins: dict[str, int] = {}
    model_counts: dict[str, int] = {}

    for b in battles:
        m = b.model
        model_counts[m] = model_counts.get(m, 0) + 1
        if b.winner:
            faction_wins[b.winner] = faction_wins.get(b.winner, 0) + 1

    # 最近 5 局
    recent = [
        {
            "battle_id": b.battle_id,
            "model": b.model,
            "winner": b.winner,
            "total_ticks": b.total_ticks,
            "created_at": b.created_at,
            "status": b.status,
        }
        for b in battles[:5]
    ]

    return {
        "total_battles": total,
        "faction_wins": faction_wins,
        "model_distribution": model_counts,
        "recent_battles": recent,
    }

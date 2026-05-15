"""Lobby engine: game lifecycle, slot management, session management."""

import json
import secrets
from datetime import datetime, timezone
from sqlmodel import Session, select

from .models import Game, Slot, Session as SessionModel, Agent, Player, RegisteredAgent, BattleHistory
from . import engine as eng


FACTION_POOL = ["蜀", "魏", "吴"]
SLOT_HEARTBEAT_TIMEOUT_SEC = 30       # 30s no heartbeat → disconnected
RECONNECT_GRACE_SEC = 600             # 10 min grace period for reconnection
SESSION_MAX_AGE_SEC = 7200            # 2 hour hard expiry
MAX_ACTIVE_SESSIONS_PER_IP = 1        # one IP → one active session


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_token() -> str:
    return f"tk_{secrets.token_hex(16)}"  # tk_ + 32 hex chars, shell-friendly


def _hash_persona(persona: str | None) -> str | None:
    if not persona:
        return None
    import hashlib
    return hashlib.sha256(persona.encode()).hexdigest()[:16]


# ═══════════════════════════════════════════════════════════════
# Game lifecycle
# ═══════════════════════════════════════════════════════════════


def get_active_game(session: Session) -> Game:
    """Return the one active game, creating one if needed."""
    game = session.exec(
        select(Game).where(Game.is_active == True)
    ).first()
    if game is None:
        game = _create_active_game(session)
    return game


def _create_active_game(session: Session) -> Game:
    """Create a fresh active game with 3 open slots and 3 managed AI agents."""
    # Mark all existing games as inactive
    old_games = session.exec(
        select(Game).where(
            (Game.is_active == True) | (Game.is_current == True)
        )
    ).all()
    for g in old_games:
        g.is_active = False
        g.is_current = False
        session.add(g)

    # Create game via existing engine (sets up cities, resources, AI agents)
    game_id = eng.create_game(session)
    game = session.get(Game, game_id)
    game.mode = "pvp"
    game.auto_advance = True
    game.max_ticks = 50
    game.is_active = True
    game.is_current = True
    game.started_at = _now()
    game.status = "active"
    game.tick_started_at = _now()
    session.add(game)

    # Create 3 open slots
    for faction in FACTION_POOL:
        slot = Slot(
            game_id=game.id,
            faction=faction,
            status="open",
        )
        session.add(slot)

    session.commit()
    session.refresh(game)

    # Auto-register managed AI agents (via engine's managed defaults)
    _ensure_managed_agents(session, game)

    # Trigger initial decisions for managed agents
    _trigger_managed_decisions(session, game)

    return game


def _ensure_managed_agents(session: Session, game: Game):
    """Ensure each faction has a managed AI agent if the slot is not player-occupied."""
    from .config import ENABLE_MANAGED_AI
    if not ENABLE_MANAGED_AI:
        return
    existing_agents = session.exec(
        select(Agent).where(Agent.game_id == game.id, Agent.is_active == True)
    ).all()
    existing_factions = {a.faction for a in existing_agents}

    for faction in FACTION_POOL:
        if faction not in existing_factions:
            cfg = eng.MANAGED_DEFAULTS[faction]
            player = Player()
            session.add(player)
            session.flush()

            reg = RegisteredAgent(
                player_id=player.player_id,
                agent_name=cfg["name"],
            )
            session.add(reg)
            session.flush()

            agent = Agent(
                game_id=game.id,
                registered_agent_id=reg.agent_id,
                agent_name=cfg["name"],
                faction=faction,
                agent_mode="managed",
                persona_config=cfg["persona"],
            )
            session.add(agent)
    session.commit()


def _trigger_managed_decisions(session: Session, game: Game):
    """Trigger initial decisions for all managed agents in the game."""
    agents = session.exec(
        select(Agent).where(
            Agent.game_id == game.id,
            Agent.agent_mode == "managed",
            Agent.is_active == True,
        )
    ).all()
    for a in agents:
        try:
            eng.auto_decide_managed(session, game.id, a)
        except Exception:
            pass
    # Try auto-advance
    try:
        eng.pvp_maybe_advance(session, game.id)
    except Exception:
        pass


def finish_game(session: Session, game: Game, winner: str | None = None):
    """Mark a game as finished and create a new one."""
    game.status = "finished"
    game.is_active = False
    game.is_current = False
    game.finished_at = _now()
    if winner:
        game.winner = winner
    session.add(game)

    # Mark all sessions for this game as finished
    sessions = session.exec(
        select(SessionModel).where(SessionModel.game_id == game.id)
    ).all()
    for s in sessions:
        s.status = "finished"
        session.add(s)

    # Deactivate all active agents for this game
    agents = session.exec(
        select(Agent).where(
            Agent.game_id == game.id,
            Agent.is_active == True,
        )
    ).all()
    for a in agents:
        a.is_active = False
        a.deactivated_at = _now()
        a.deactivated_reason = "game_ended"
        session.add(a)

    # Release all slots
    slots = session.exec(
        select(Slot).where(Slot.game_id == game.id)
    ).all()
    for s in slots:
        s.status = "open"
        s.session_token = None
        session.add(s)

    # Create BattleHistory record for the finished game
    try:
        existing_bh = session.exec(
            select(BattleHistory).where(BattleHistory.game_id == game.id)
        ).first()
        if not existing_bh:
            cities = session.exec(
                select(eng.City).where(eng.City.game_id == game.id)
            ).all()
            summary = json.dumps(
                {"cities": [{"name": c.name, "owner": c.owner, "troops": c.troops} for c in cities]},
                ensure_ascii=False,
            )
            bh = BattleHistory(
                game_id=game.id,
                model="pvp",
                winner=game.winner,
                total_ticks=game.tick,
                summary=summary,
                status=game.status,
            )
            session.add(bh)
    except Exception:
        pass

    session.commit()

    # Create the next active game
    _create_active_game(session)


# ═══════════════════════════════════════════════════════════════
# Slot management
# ═══════════════════════════════════════════════════════════════


def get_lobby_status(session: Session) -> dict:
    """Public lobby status: game info + slot states + spectator count."""
    game = get_active_game(session)

    # Drive tick advancement — browser polls this every 3s
    if game.mode == "pvp" and game.status in ("active", "paused"):
        try:
            eng.pvp_maybe_advance(session, game.id)
        except Exception:
            pass

    slots = session.exec(
        select(Slot).where(Slot.game_id == game.id)
    ).all()
    slot_map = {s.faction: s for s in slots}

    # Count spectators
    spec_count = len(session.exec(
        select(SessionModel).where(
            SessionModel.game_id == game.id,
            SessionModel.faction == "spectator",
            SessionModel.status == "active",
        )
    ).all())

    # Build slot statuses
    slots_status = {}
    for faction in FACTION_POOL:
        s = slot_map.get(faction)
        if s is None:
            slots_status[faction] = {"status": "open", "occupied_since": None}
            continue

        status = s.status
        info = {"status": status, "occupied_since": s.joined_at}

        if status == "occupied":
            # Check heartbeat
            if s.last_heartbeat_at:
                last = datetime.fromisoformat(s.last_heartbeat_at)
                ago = (datetime.now(timezone.utc) - last).total_seconds()
                if ago > SLOT_HEARTBEAT_TIMEOUT_SEC:
                    # Auto-mark disconnected
                    s.status = "disconnected"
                    session.add(s)
                    session.commit()
                    status = "disconnected"
                    info["status"] = "disconnected"
                    info["disconnected_sec"] = int(ago)
                else:
                    info["online_sec"] = int(ago)
            info["ip"] = (s.occupied_by_ip or "")[:8] + "***"

        elif status == "disconnected":
            if s.last_heartbeat_at:
                last = datetime.fromisoformat(s.last_heartbeat_at)
                ago = (datetime.now(timezone.utc) - last).total_seconds()
                info["disconnected_sec"] = int(ago)
                remaining = RECONNECT_GRACE_SEC - int(ago)
                info["reconnect_remaining_sec"] = max(0, remaining)
                # Auto-release if grace period expired
                if ago > RECONNECT_GRACE_SEC:
                    old_session = session.exec(
                        select(SessionModel).where(
                            SessionModel.session_token == s.session_token
                        )
                    ).first()
                    if old_session:
                        old_session.status = "kicked"
                        session.add(old_session)
                    s.status = "open"
                    s.session_token = None
                    s.occupied_by_ip = None
                    s.occupied_by_persona_hash = None
                    session.add(s)

                    # Deactivate stale agents for this faction so re-join won't 409
                    stale_agents = session.exec(
                        select(Agent).where(
                            Agent.game_id == s.game_id,
                            Agent.faction == s.faction,
                            Agent.is_active == True,
                        )
                    ).all()
                    for agent in stale_agents:
                        agent.is_active = False
                        agent.deactivated_at = _now()
                        agent.deactivated_reason = "slot_released"
                        session.add(agent)

                    session.commit()
                    status = "open"
                    info = {"status": "open", "occupied_since": s.joined_at}
            info["ip"] = (s.occupied_by_ip or "")[:8] + "***"

        slots_status[faction] = info

    # Ensure managed agents for any newly-opened slots
    eng._ensure_managed_for_open_slots(session, game.id)

    # Current tick info
    cities = session.exec(
        select(eng.City).where(eng.City.game_id == game.id)
    ).all()

    # Events
    events = []
    if game.last_tick_events:
        events = json.loads(game.last_tick_events)

    diplomacy = []
    if game.last_tick_diplomacy:
        diplomacy = json.loads(game.last_tick_diplomacy)

    return {
        "game_id": game.id,
        "status": game.status,
        "tick": game.tick,
        "max_ticks": game.max_ticks,
        "winner": game.winner,
        "started_at": game.started_at,
        "slots": slots_status,
        "spectator_count": spec_count,
        "cities": [
            {"name": c.name, "owner": c.owner, "troops": c.troops}
            for c in cities
        ],
        "events": events[-5:] if events else [],
        "diplomacy": diplomacy[-3:] if diplomacy else [],
    }


def join_slot(
    session: Session,
    faction: str,
    ip: str,
    persona_hash: str | None = None,
    ua: str | None = None,
) -> dict:
    """Join a faction slot. Returns session info or raises ValueError."""
    game = get_active_game(session)

    if faction not in FACTION_POOL and faction != "spectator":
        raise ValueError(f"无效势力: {faction}")

    # ── Spectator join ──────────────────────────────────────
    if faction == "spectator":
        token = _new_token()
        sess = SessionModel(
            session_token=token,
            game_id=game.id,
            faction="spectator",
            status="active",
            heartbeat_at=_now(),
            ip=ip,
            ua=ua,
        )
        session.add(sess)
        session.commit()
        return {
            "session_token": token,
            "game_id": game.id,
            "faction": "spectator",
            "expires_at": _now(),
        }

    # ── Find the slot ──────────────────────────────────────
    slot = session.exec(
        select(Slot).where(Slot.game_id == game.id, Slot.faction == faction)
    ).first()
    if slot is None:
        slot = Slot(
            game_id=game.id,
            faction=faction,
            status="open",
        )
        session.add(slot)
        session.flush()

    # ── Check slot availability (before IP check) ──────────
    if slot.status == "occupied":
        # Check if heartbeat is stale
        if slot.last_heartbeat_at:
            last = datetime.fromisoformat(slot.last_heartbeat_at)
            ago = (datetime.now(timezone.utc) - last).total_seconds()
            if ago > SLOT_HEARTBEAT_TIMEOUT_SEC:
                # Mark old occupant as disconnected, allow takeover
                old_session = session.exec(
                    select(SessionModel).where(
                        SessionModel.session_token == slot.session_token
                    )
                ).first()
                if old_session:
                    old_session.status = "disconnected"
                    session.add(old_session)
                slot.status = "open"
                slot.session_token = None
            else:
                raise ValueError(f"势力 [{faction}] 已被占用")
        else:
            raise ValueError(f"势力 [{faction}] 已被占用")

    if slot.status == "disconnected":
        # Check if within grace period
        if slot.last_heartbeat_at:
            last = datetime.fromisoformat(slot.last_heartbeat_at)
            ago = (datetime.now(timezone.utc) - last).total_seconds()
            if ago < RECONNECT_GRACE_SEC:
                raise ValueError(
                    f"势力 [{faction}] 处于断线宽容期，剩余 "
                    f"{int(RECONNECT_GRACE_SEC - ago)} 秒，请使用 reconnect"
                )
        # Grace period expired, release the slot
        old_session = session.exec(
            select(SessionModel).where(
                SessionModel.session_token == slot.session_token
            )
        ).first()
        if old_session:
            old_session.status = "kicked"
            session.add(old_session)
        slot.status = "open"
        slot.session_token = None

    # ── Check IP limit: one active session per IP ──────────
    from .config import ENFORCE_ONE_FACTION_PER_IP
    if ENFORCE_ONE_FACTION_PER_IP:
        active_sessions = session.exec(
            select(SessionModel).where(
                SessionModel.ip == ip,
                SessionModel.faction != "spectator",
                SessionModel.status.in_(["active", "disconnected"]),
            )
        ).all()
        if len(active_sessions) >= MAX_ACTIVE_SESSIONS_PER_IP:
            raise ValueError("同一 IP 只能持有 1 个活跃席位")

    # ── Occupy the slot ────────────────────────────────────
    token = _new_token()
    now = _now()

    slot.status = "occupied"
    slot.session_token = token
    slot.last_heartbeat_at = now
    slot.occupied_by_ip = ip
    slot.occupied_by_persona_hash = persona_hash
    slot.joined_at = now
    session.add(slot)

    # Create session record
    sess = SessionModel(
        session_token=token,
        game_id=game.id,
        faction=faction,
        status="active",
        heartbeat_at=now,
        ip=ip,
        ua=ua,
    )
    session.add(sess)

    # ── Register as agent in the game ──────────────────────
    _register_player_agent(session, game, faction, token, ip)

    session.commit()

    # Resume paused game if needed
    try:
        eng.pvp_maybe_advance(session, game.id)
    except Exception:
        pass

    expires_at = datetime.now(timezone.utc).timestamp() + SESSION_MAX_AGE_SEC
    from datetime import datetime as dt
    expires_iso = dt.fromtimestamp(expires_at, tz=timezone.utc).isoformat()

    return {
        "session_token": token,
        "game_id": game.id,
        "faction": faction,
        "expires_at": expires_iso,
        "instruction_url": f"/v1/lobby/instruction?token={token}",
    }


def _register_player_agent(
    session: Session,
    game: Game,
    faction: str,
    token: str,
    ip: str,
):
    """Register a self-hosted agent for the joining player, replacing any managed AI."""
    existing_agents = session.exec(
        select(Agent).where(
            Agent.game_id == game.id,
            Agent.faction == faction,
            Agent.is_active == True,
        )
    ).all()
    default_names = [eng.MANAGED_DEFAULTS[f]["name"] for f in FACTION_POOL]
    for a in existing_agents:
        if a.agent_name in default_names:
            # Soft-deactivate managed AI — preserve history
            a.is_active = False
            a.deactivated_at = _now()
            a.deactivated_reason = "replaced_by_player"
            session.add(a)
            # Delete submitted actions from this agent for current tick
            actions_to_del = session.exec(
                select(eng.Action).where(
                    eng.Action.game_id == game.id,
                    eng.Action.agent_id == a.id,
                    eng.Action.tick == game.tick,
                )
            ).all()
            for act in actions_to_del:
                session.delete(act)
        else:
            # Non-default agent already occupies this faction
            raise ValueError(f"势力 [{faction}] 已被玩家占用")

    session.flush()

    # Register new player + agent
    player = Player()
    session.add(player)
    session.flush()

    reg = RegisteredAgent(
        player_id=player.player_id,
        agent_name=f"BYOA-{faction}-{ip}",
    )
    session.add(reg)
    session.flush()

    agent = Agent(
        game_id=game.id,
        registered_agent_id=reg.agent_id,
        agent_name=f"BYOA-{faction}",
        faction=faction,
        agent_mode="self_hosted",
        token=token,  # Use the session token as agent token
    )
    session.add(agent)
    session.flush()


# ═══════════════════════════════════════════════════════════════
# Session management
# ═══════════════════════════════════════════════════════════════


def validate_session(session: Session, token: str) -> SessionModel:
    """Validate a session token. Raises ValueError if invalid/expired."""
    sess = session.get(SessionModel, token)
    if sess is None:
        raise ValueError("无效 session_token")

    if sess.status == "finished":
        raise ValueError("对局已结束")

    if sess.status == "kicked":
        raise ValueError("会话已被踢出")

    # Check 30-min hard expiry
    created = datetime.fromisoformat(sess.created_at)
    age = (datetime.now(timezone.utc) - created).total_seconds()
    if age > SESSION_MAX_AGE_SEC:
        sess.status = "kicked"
        session.add(sess)
        session.commit()
        raise ValueError("session_token 已过期（2 小时）")

    return sess


def update_heartbeat(session: Session, token: str):
    """Update heartbeat for a session and its slot."""
    sess = validate_session(session, token)

    now = _now()
    sess.heartbeat_at = now
    sess.status = "active"  # Re-activate if disconnected
    session.add(sess)

    # Update slot heartbeat
    if sess.faction != "spectator":
        slot = session.exec(
            select(Slot).where(
                Slot.game_id == sess.game_id,
                Slot.faction == sess.faction,
                Slot.session_token == token,
            )
        ).first()
        if slot:
            slot.last_heartbeat_at = now
            if slot.status == "disconnected":
                slot.status = "occupied"
            session.add(slot)

    session.commit()


def reconnect_session(session: Session, token: str) -> dict:
    """Attempt to reconnect a disconnected session within grace period."""
    sess = session.get(SessionModel, token)
    if sess is None:
        raise ValueError("无效 session_token")

    if sess.status not in ("disconnected", "active"):
        raise ValueError(f"会话状态为 {sess.status}，无法重连")

    if sess.faction == "spectator":
        sess.status = "active"
        sess.heartbeat_at = _now()
        session.add(sess)
        session.commit()
        return {
            "session_token": token,
            "game_id": sess.game_id,
            "faction": sess.faction,
            "status": "reconnected",
        }

    # Check grace period
    slot = session.exec(
        select(Slot).where(
            Slot.game_id == sess.game_id,
            Slot.faction == sess.faction,
            Slot.session_token == token,
        )
    ).first()

    if slot is None:
        raise ValueError("槽位不存在")

    if slot.last_heartbeat_at:
        last = datetime.fromisoformat(slot.last_heartbeat_at)
        ago = (datetime.now(timezone.utc) - last).total_seconds()
        if ago > RECONNECT_GRACE_SEC:
            raise ValueError(
                f"断线宽容期已过（{int(ago)} 秒 > {RECONNECT_GRACE_SEC} 秒），"
                f"请重新加入"
            )

    # Re-activate
    now = _now()
    slot.status = "occupied"
    slot.last_heartbeat_at = now
    session.add(slot)

    sess.status = "active"
    sess.heartbeat_at = now
    session.add(sess)

    session.commit()

    # Resume paused game if needed
    try:
        eng.pvp_maybe_advance(session, sess.game_id)
    except Exception:
        pass

    return {
        "session_token": token,
        "game_id": sess.game_id,
        "faction": sess.faction,
        "status": "reconnected",
    }


def get_session_agent(session: Session, token: str) -> Agent:
    """Get the Agent record for a session token (for action auth)."""
    sess = validate_session(session, token)

    # Spectator cannot submit actions
    if sess.faction == "spectator":
        raise ValueError("观战 token 不能提交动作")

    agent = session.exec(
        select(Agent).where(
            Agent.game_id == sess.game_id,
            Agent.token == token,
            Agent.is_active == True,
        )
    ).first()
    if agent is None:
        raise ValueError("未找到对应的 agent")

    return agent


# ═══════════════════════════════════════════════════════════════
# Game end check (called after each tick)
# ═══════════════════════════════════════════════════════════════


def check_and_restart_game(session: Session, game_id: int):
    """After a tick, check if the game finished. If so, create a new one."""
    game = session.get(Game, game_id)
    if game is None:
        return
    if game.status != "finished":
        return
    if not game.is_active:
        return  # Already handled

    finish_game(session, game)

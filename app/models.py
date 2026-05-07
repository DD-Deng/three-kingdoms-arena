import uuid
import secrets
from datetime import datetime, timezone
from typing import Optional
from sqlmodel import SQLModel, Field


def _new_token():
    return uuid.uuid4().hex[:16]


def _new_uuid():
    return uuid.uuid4().hex


def _new_secret():
    return secrets.token_hex(32)


def _now():
    return datetime.now(timezone.utc).isoformat()


# ═══════════════════════════════════════════════════════════════
# Player —— 玩家身份
# ═══════════════════════════════════════════════════════════════

class Player(SQLModel, table=True):
    player_id: str = Field(default_factory=_new_uuid, primary_key=True)
    created_at: str = Field(default_factory=_now)


# ═══════════════════════════════════════════════════════════════
# RegisteredAgent —— 已注册的 agent（全局唯一）
# ═══════════════════════════════════════════════════════════════

class RegisteredAgent(SQLModel, table=True):
    agent_id: str = Field(default_factory=_new_uuid, primary_key=True)
    player_id: str = Field(foreign_key="player.player_id")
    agent_name: str
    version: str = "v1"
    secret: str = Field(default_factory=_new_secret)
    created_at: str = Field(default_factory=_now)


# ═══════════════════════════════════════════════════════════════
# Game —— 一局对战
# ═══════════════════════════════════════════════════════════════

class Game(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    tick: int = Field(default=0)
    status: str = Field(default="waiting")  # waiting | active | finished
    winner: Optional[str] = Field(default=None)
    last_tick_events: Optional[str] = Field(default=None)  # JSON: public events (sanitized)
    last_tick_diplomacy: Optional[str] = Field(default=None)  # JSON: public diplomacy messages
    last_tick_intentions: Optional[str] = Field(default=None)  # JSON: 上回合攻击意图(不含兵力)
    resources: Optional[str] = Field(default=None)  # JSON: {"蜀":{"grain":500},...}


# ═══════════════════════════════════════════════════════════════
# Agent —— 对局参与者（关联已注册 agent）
# ═══════════════════════════════════════════════════════════════

class Agent(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    game_id: int = Field(foreign_key="game.id")
    registered_agent_id: str = Field(foreign_key="registeredagent.agent_id")
    agent_name: str
    faction: str  # 蜀 | 魏 | 吴
    token: str = Field(default_factory=_new_token)


# ═══════════════════════════════════════════════════════════════
# City —— 城池
# ═══════════════════════════════════════════════════════════════

class City(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    game_id: int = Field(foreign_key="game.id")
    name: str
    owner: Optional[str] = None
    troops: int = Field(default=1000)


# ═══════════════════════════════════════════════════════════════
# Action —— 回合动作
# ═══════════════════════════════════════════════════════════════

class Action(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    game_id: int = Field(foreign_key="game.id")
    agent_id: int = Field(foreign_key="agent.id")
    tick: int
    type: str  # attack | defend | recruit | march | diplomacy
    target: str
    # Extended fields for new action types (Step 2+)
    from_city: Optional[str] = None
    troops: Optional[int] = None
    amount: Optional[int] = None
    message: Optional[str] = None
    diplomacy_type: Optional[str] = None  # Step 3: alliance_propose|alliance_accept|alliance_break|declare_war|trade_offer|message
    trade_terms: Optional[str] = None     # Step 3: JSON for trade_offer

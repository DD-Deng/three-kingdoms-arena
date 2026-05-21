import uuid
import secrets
from datetime import datetime, timezone
from typing import Optional
from sqlmodel import SQLModel, Field


def _new_token():
    return f"tk_{secrets.token_hex(16)}"  # tk_ + 32 hex chars, shell-friendly


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
    status: str = Field(default="lobby")  # lobby | countdown | active | paused | finished
    winner: Optional[str] = Field(default=None)
    last_tick_events: Optional[str] = Field(default=None)  # JSON: public events (sanitized)
    last_tick_diplomacy: Optional[str] = Field(default=None)  # JSON: public diplomacy messages
    last_tick_intentions: Optional[str] = Field(default=None)  # JSON: 上回合攻击意图(不含兵力)
    resources: Optional[str] = Field(default=None)  # JSON: {"蜀":{"grain":500},...}

    # PvP arena fields
    mode: str = Field(default="auto")               # "auto" | "pvp"
    host_agent_id: Optional[int] = Field(default=None, foreign_key="agent.id")
    auto_advance: bool = Field(default=True)
    created_by_player_id: Optional[str] = Field(default=None)
    title: Optional[str] = Field(default=None)
    max_ticks: int = Field(default=35)
    tick_timeout_sec: int = Field(default=60)
    tick_started_at: Optional[str] = Field(default=None)  # ISO timestamp when current tick began
    is_current: bool = Field(default=True)            # 标记为当前活跃对局

    # Lobby / BYOA fields
    is_active: bool = Field(default=False)            # 当前正在进行的对局（有且仅有一个）
    started_at: Optional[str] = Field(default=None)
    finished_at: Optional[str] = Field(default=None)

    # Countdown fields (3人齐ready → 5秒倒计时 → 开打)
    countdown_started_at: Optional[str] = Field(default=None)
    countdown_deadline: Optional[str] = Field(default=None)

    # Incremental narrative chapters (v0.8 — every 5 ticks)
    chapters: Optional[str] = Field(default=None)  # JSON array of chapter objects


# ═══════════════════════════════════════════════════════════════
# Slot —— 阵营槽位（每局 3 个，先到先得）
# ═══════════════════════════════════════════════════════════════

class Slot(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    game_id: int = Field(foreign_key="game.id")
    faction: str  # 蜀 | 魏 | 吴
    status: str = Field(default="open")  # open | occupied | disconnected
    session_token: Optional[str] = Field(default=None, index=True)
    last_heartbeat_at: Optional[str] = Field(default=None)
    occupied_by_ip: Optional[str] = Field(default=None)
    occupied_by_persona_hash: Optional[str] = Field(default=None)
    joined_at: Optional[str] = Field(default=None)
    # Ready system (agent declares ready before game starts)
    ready: bool = Field(default=False)
    ready_at: Optional[str] = Field(default=None)
    agent_display_name: Optional[str] = Field(default=None)


# ═══════════════════════════════════════════════════════════════
# Session —— 接入会话（BYOA agent 的身份凭证）
# ═══════════════════════════════════════════════════════════════

class Session(SQLModel, table=True):
    session_token: str = Field(primary_key=True)
    game_id: int = Field(foreign_key="game.id")
    faction: str  # 蜀 | 魏 | 吴 | spectator
    status: str = Field(default="active")  # active | disconnected | kicked | finished
    heartbeat_at: Optional[str] = Field(default=None)
    ip: Optional[str] = Field(default=None)
    ua: Optional[str] = Field(default=None)
    created_at: str = Field(default_factory=_now)


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

    # PvP arena fields
    agent_mode: str = Field(default="self_hosted")    # "managed" | "self_hosted"
    llm_config: Optional[str] = Field(default=None)   # JSON — LLM provider config
    persona_config: Optional[str] = Field(default=None)  # JSON — persona description

    # Soft delete — preserve historical records for commentary/replay/stats
    is_active: bool = Field(default=True)
    deactivated_at: Optional[str] = Field(default=None)
    deactivated_reason: Optional[str] = Field(default=None)  # slot_released / game_ended / manual


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


# ═══════════════════════════════════════════════════════════════
# BattleHistory —— 对战历史索引
# ═══════════════════════════════════════════════════════════════

class BattleHistory(SQLModel, table=True):
    battle_id: Optional[int] = Field(default=None, primary_key=True)
    game_id: Optional[int] = Field(default=None, foreign_key="game.id")
    model: str
    created_at: str = Field(default_factory=_now)
    winner: Optional[str] = None
    total_ticks: int = 0
    summary: Optional[str] = None  # JSON: 终局城池/兵力快照
    status: str = "finished"  # finished | max_ticks | error

    # Commentary system (v0.9)
    commentary_status: str = Field(default="not_started")  # not_started | generating | ready | failed
    commentary_started_at: Optional[str] = Field(default=None)
    commentary_content: Optional[str] = Field(default=None)
    last_error: Optional[str] = Field(default=None)

    @property
    def has_commentary(self) -> bool:
        """Backward-compat: derived from commentary_status."""
        return self.commentary_status == "ready"


# ═══════════════════════════════════════════════════════════════
# BattleLogFile —— 对战日志文件索引
# ═══════════════════════════════════════════════════════════════

class BattleLogFile(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    battle_id: int = Field(foreign_key="battlehistory.battle_id")
    file_type: str  # jsonl | private_thoughts | stdout | commentary | battle_log
    agent_name: Optional[str] = None
    file_path: str

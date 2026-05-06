import uuid
from typing import Optional
from sqlmodel import SQLModel, Field


def _new_token():
    return uuid.uuid4().hex[:16]


class Game(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    tick: int = Field(default=0)
    status: str = Field(default="waiting")  # waiting | active | finished
    winner: Optional[str] = Field(default=None)
    last_tick_events: Optional[str] = Field(default=None)  # JSON string


class Agent(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    game_id: int = Field(foreign_key="game.id")
    agent_name: str
    faction: str  # 蜀 | 魏 | 吴
    token: str = Field(default_factory=_new_token)


class City(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    game_id: int = Field(foreign_key="game.id")
    name: str
    owner: Optional[str] = None
    troops: int = Field(default=1000)


class Action(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    game_id: int = Field(foreign_key="game.id")
    agent_id: int = Field(foreign_key="agent.id")
    tick: int
    type: str  # attack | defend
    target: str

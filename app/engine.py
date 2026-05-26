import json
import math
import os
import random
import sys
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from sqlmodel import Session, select
from .models import Game, Agent, City, Action, Player, RegisteredAgent

from dayan_engine.core.types import BattleConfig
from dayan_engine.core.battle import run_battle
from dayan_engine.narrator.template_narrator import generate as generate_narrative

# Faction → Three Kingdoms general traits (from Dayan Engine presets)
FACTION_TRAITS: dict[str, dict[str, float]] = {
    "魏": {"主帅": 0.90, "军师": 0.85, "先锋": 0.70, "后勤": 0.80, "军资": 0.95, "联盟": 0.30},
    "蜀": {"主帅": 0.75, "军师": 0.90, "先锋": 0.80, "后勤": 0.65, "军资": 0.55, "联盟": 0.95},
    "吴": {"主帅": 0.70, "军师": 0.95, "先锋": 0.75, "后勤": 0.85, "军资": 0.90, "联盟": 0.70},
}

FACTION_GENERAL_NAME: dict[str, str] = {
    "魏": "曹操",
    "蜀": "刘备",
    "吴": "孙权",
}

FACTION_POOL = ["蜀", "魏", "吴"]

# ═══════════════════════════════════════════════════════════════
# 地图数据：7 座城池 + 邻接关系
# ═══════════════════════════════════════════════════════════════

ALL_CITIES = ["洛阳", "长安", "邺城", "宛城", "襄阳", "成都", "建业"]

CITY_ADJACENCY: dict[str, list[str]] = {
    "洛阳": ["长安", "邺城", "宛城"],
    "长安": ["洛阳", "宛城", "成都"],   # 新增蜀道：长安 ↔ 成都
    "邺城": ["洛阳"],
    "宛城": ["洛阳", "长安", "襄阳"],
    "襄阳": ["宛城", "成都", "建业"],
    "成都": ["长安", "襄阳"],           # 新增蜀道：成都 ↔ 长安
    "建业": ["襄阳"],
}

# 初始配置：(归属, 初始兵力) —— 三方各 2 城起手，宛城中立
# 魏: 洛阳 1200 + 邺城 1000 = 2200 兵, 粮 600
# 蜀: 成都 1000 + 长安 800 = 1800 兵, 粮 500
# 吴: 建业 1000 + 襄阳 900 = 1900 兵, 粮 500
INITIAL_SETUP: dict[str, tuple[str | None, int]] = {
    "洛阳": ("魏", 1200),
    "长安": ("蜀", 800),
    "邺城": ("魏", 1000),
    "宛城": (None, 600),
    "襄阳": ("吴", 900),
    "成都": ("蜀", 1000),
    "建业": ("吴", 1000),
}

INITIAL_GRAIN: dict[str, int] = {
    "魏": 600,
    "蜀": 500,
    "吴": 500,
}

GRAIN_PER_CITY = 80          # 每城每 tick 粮草产出（从 100 降到 80）
MAX_LOAN = 200               # 最大负债额
LOAN_RECRUIT_PENALTY = 0.5   # 负债后下回合招兵 cost +50%

GARRISON_MIN = 100
MAX_RECRUIT_PER_CITY = 200

# ── 防御工事系统（详见 docs/combat-rules.md §3） ─────────────
DEFENSE_WORKS_MAX = 3           # 最大防御度 (曾 5)              —— §3.1
DEFENSE_WORKS_PER_DEFEND = 1    # 每次 defend +1 防御度          —— §3.1
DEFENSE_WORKS_BONUS = 0.15      # 每点防御度 +15% 防守战力 (曾 20%)  —— §3.1

# ── 协同进攻参数（详见 docs/combat-rules.md §4） ─────────────
# 协同条件: 双方在同一 tick attack 同一目标 + 双方在最近 3 tick 内
#          通过 diplomacy alliance_accept 确认过联盟
# 协同效果: 攻击力相加, 占城后胜方得城, 另一方获"友城标记"(3 tick 互不攻击)
COORDINATED_ATTACK_WINDOW = 3   # 联盟有效窗口 (tick)           —— §4.2

# ── 外交与信用系统（详见 docs/diplomacy-rules.md） ──────────
DIPLOMACY_TYPES = [
    "alliance_propose", "alliance_accept", "alliance_break",
    "alliance_renew",
    "declare_war", "trade_offer", "message",
]
TRUST_INITIAL = 100
TRUST_BETRAYAL_PENALTY = -30      # alliance_break 扣 30
TRUST_ALLY_ATTACK_PENALTY = -50   # 盟期内攻击盟友扣 50（且自动 break）
TRUST_RECOVERY_PER_TICK = 5       # 7 tick 不背叛，每 tick +5（上限 100）
TRUST_REJECT_THRESHOLD = 50       # trust < 50 → 其他人自动拒绝你的联盟提议
BETRAYAL_COOLDOWN = 5             # 破盟后 5 tick 内联盟提议自动被拒
ALLIANCE_AUTO_EXPIRE_TICKS = 15  # 联盟 15 tick 后自动过期

# 日志目录 (persisted on Railway Volume)
LOG_DIR = Path(os.getenv("LOG_DIR", "/data/logs"))
PUBLIC_LOG_DIR = LOG_DIR / "public"
PRIVATE_LOG_DIR = LOG_DIR / "private"


# ═══════════════════════════════════════════════════════════════
# Agent 注册
# ═══════════════════════════════════════════════════════════════

def register_agent(
    session: Session,
    player_id: str | None,
    agent_name: str,
    version: str = "v1",
) -> dict:
    if not player_id:
        player = Player()
        session.add(player)
        session.flush()
        player_id = player.player_id
    else:
        player = session.get(Player, player_id)
        if player is None:
            player = Player(player_id=player_id)
            session.add(player)
            session.flush()

    reg = RegisteredAgent(
        player_id=player_id,
        agent_name=agent_name,
        version=version,
    )
    session.add(reg)
    session.commit()
    session.refresh(reg)

    return {
        "agent_id": reg.agent_id,
        "secret": reg.secret,
        "player_id": player_id,
    }


# ═══════════════════════════════════════════════════════════════
# 对局管理
# ═══════════════════════════════════════════════════════════════

def create_game(session: Session) -> int:
    game = Game()
    session.add(game)
    session.flush()

    for name in ALL_CITIES:
        owner, troops = INITIAL_SETUP[name]
        session.add(City(game_id=game.id, name=name, owner=owner, troops=troops))

    resources = {
        f: {
            "grain": INITIAL_GRAIN.get(f, 500),
            "debt": 0,
            "trust_score": TRUST_INITIAL,
            "_idle_ticks": 0,
        }
        for f in FACTION_POOL
    }
    game.resources = json.dumps(resources, ensure_ascii=False)
    session.add(game)
    session.commit()
    return game.id  # type: ignore[return-value]


def join_game(
    session: Session,
    game_id: int,
    agent_id: str,
    secret: str,
    faction: str,
) -> str:
    game = session.get(Game, game_id)
    if game is None:
        raise ValueError("对局不存在")
    if game.status not in ("lobby", "countdown") and game.tick > 0:
        raise ValueError("对局已开始")
    if faction not in FACTION_POOL:
        raise ValueError(f"势力必须是: {FACTION_POOL}")

    reg = session.get(RegisteredAgent, agent_id)
    if reg is None:
        raise ValueError("agent 未注册")
    if reg.secret != secret:
        raise ValueError("secret 不正确")

    existing = session.exec(
        select(Agent).where(
            Agent.game_id == game_id, Agent.faction == faction, Agent.is_active == True
        )
    ).first()
    if existing:
        raise ValueError(f"势力 [{faction}] 已被占用")

    agent = Agent(
        game_id=game_id,
        registered_agent_id=agent_id,
        agent_name=reg.agent_name,
        faction=faction,
    )
    session.add(agent)
    session.commit()
    session.refresh(agent)

    return agent.token  # type: ignore[return-value]


# ═══════════════════════════════════════════════════════════════
# 信息隔离：按势力视角返回 state
# ═══════════════════════════════════════════════════════════════

def get_state(session: Session, game_id: int, agent: Agent):
    """按 token 视角返回 state —— 隐私隔离。

    关键约束：
    - 邻接城：精确兵力
    - 远处城：模糊估计 (low/medium/high)
    - 看不到其他 agent 的 private_thought
    """
    game = session.get(Game, game_id)
    if game is None:
        raise ValueError("对局不存在")

    # Drive tick advancement on every state poll (timeout-based)
    if game.mode == "pvp":
        pvp_maybe_advance(session, game_id)
        game = session.get(Game, game_id)  # re-fetch — may have been modified

    cities = session.exec(select(City).where(City.game_id == game_id)).all()
    agents = session.exec(
        select(Agent).where(Agent.game_id == game_id, Agent.is_active == True)
    ).all()

    your_faction = agent.faction

    # ── 你的城池（精确信息） ──────────────────────────────
    last_occupied = {}
    def_works = {}
    resources_raw_early = {}
    if game.resources:
        resources_raw_early = json.loads(game.resources)
        last_occupied = resources_raw_early.get("_last_occupied", {})
        def_works = resources_raw_early.get("_defense_works", {})
    your_cities = []
    own_names = set()
    for c in cities:
        if c.owner == your_faction:
            neighbors = CITY_ADJACENCY.get(c.name, [])
            dlevel = def_works.get(c.name, 0)
            city_data = {
                "name": c.name,
                "troops": c.troops,
                "defense_level": dlevel,
                "defense_status": _defense_status(dlevel),
                "neighbors": neighbors,
            }
            if c.name in last_occupied:
                city_data["last_occupied_at"] = last_occupied[c.name]
            your_cities.append(city_data)
            own_names.add(c.name)

    # ── 已知城池（按距离分层） ────────────────────────────
    # 计算所有与我方城池邻接的外部城
    adjacent_to_own: set[str] = set()
    for name in own_names:
        for nb in CITY_ADJACENCY.get(name, []):
            if nb not in own_names:
                adjacent_to_own.add(nb)

    # ── 宣战信息: 被宣战方看到宣战方全部精确兵力 ──────────
    resources_raw = resources_raw_early
    war_revealed_cities: set[str] = set()
    war_revealed_by = resources_raw.get(your_faction, {}).get("war_revealed_by")
    if war_revealed_by:
        for c in cities:
            if c.owner == war_revealed_by:
                war_revealed_cities.add(c.name)

    # ── 联盟信息共享: 盟友间看到彼此精确兵力 ──────────────
    alliance_cities: set[str] = set()
    my_ally = resources_raw.get(your_faction, {}).get("alliance_with")
    if my_ally:
        for c in cities:
            if c.owner == my_ally:
                alliance_cities.add(c.name)

    known_cities = []
    visible_cities = adjacent_to_own | war_revealed_cities | alliance_cities
    # 联盟城 / 邻接城 → 防御度精确可见
    exact_defense_cities = adjacent_to_own | alliance_cities
    for c in cities:
        if c.name in own_names:
            continue
        owner_display = c.owner if c.owner else "中立"
        dlevel = def_works.get(c.name, 0)
        dstatus = _defense_status(dlevel)
        if c.name in visible_cities:
            cd = {
                "name": c.name,
                "owner": owner_display,
                "troops": c.troops,
                "defense_status": dstatus,
                "info_freshness": "current",
            }
            if c.name in exact_defense_cities:
                cd["defense_level"] = dlevel
            if c.name in last_occupied:
                cd["last_occupied_at"] = last_occupied[c.name]
            known_cities.append(cd)
        else:
            known_cities.append({
                "name": c.name,
                "owner": owner_display,
                "troops_estimate": _classify_troops(c.troops),
                "defense_status": dstatus,
                "info_freshness": "rumor",
            })

    # ── 资源 ──────────────────────────────────────────────
    resources = {}
    if game.resources:
        resources = json.loads(game.resources)
    your_resources = resources.get(your_faction, {"grain": 0})

    # ── 合法动作 ──────────────────────────────────────────
    valid_actions = _compute_valid_actions(cities, your_faction, your_resources, game)

    # ── 公开事件（上回合） ────────────────────────────────
    public_events = []
    if game.last_tick_events:
        public_events = json.loads(game.last_tick_events)

    # ── 外交消息（上回合） ────────────────────────────────
    diplomacy = []
    if game.last_tick_diplomacy:
        diplomacy = json.loads(game.last_tick_diplomacy)

    # ── 攻击意图（上回合公示，不含兵力） ──────────────────
    last_intentions = []
    if game.last_tick_intentions:
        last_intentions = json.loads(game.last_tick_intentions)

    # ── 防御工事（你的城可见） ────────────────────────────
    your_defense_works = {}
    for city_name in own_names:
        your_defense_works[city_name] = def_works.get(city_name, 0)

    # ── 联盟状态 ────────────────────────────────────────────
    all_alliances = resources_raw.get("_alliances", [])
    your_faction_res = resources_raw.get(your_faction, {})
    your_alliance_with = your_faction_res.get("alliance_with")
    pending_alliance_from = your_faction_res.get("pending_alliance_from")

    # ── 信用分（仅自己的分数可见） ─────────────────────────
    your_trust = resources_raw.get(your_faction, {}).get("trust_score", TRUST_INITIAL)

    # ── 外交历史（最近 5 tick 的外交事件） ────────────────
    diplomacy_history = [
        e for e in resources_raw.get("_diplomacy_history", [])
        if game.tick - e.get("tick", 0) <= 5
    ]

    # ── Fog of War: filter combat_report ────────────────────
    your_side = {your_faction}
    if your_alliance_with:
        your_side.add(your_alliance_with)
    for ev in public_events:
        if "combat_report" not in ev:
            continue
        involved = set(ev.get("attackers", [])) | {ev.get("defender")}
        if not (your_side & involved):
            ev.pop("combat_report", None)

    # ── 宣战信息: 是否有人对你宣战 ────────────────────────
    war_revealed_by = resources_raw.get(your_faction, {}).get("war_revealed_by")

    # ── Token lifecycle is game-bound — no time-based expiry ──
    your_token_expires_at: str | None = None
    your_token_expires_in_sec: int | None = None

    # ── Tick timing diagnostics ────────────────────────────
    from .config import TICK_TIMEOUT_SEC
    from .models import Slot as SlotModel

    tick_elapsed_sec = None
    if game.tick_started_at:
        try:
            started = datetime.fromisoformat(game.tick_started_at)
            tick_elapsed_sec = round(
                (datetime.now(timezone.utc) - started).total_seconds(), 1
            )
        except Exception:
            pass

    waiting_for: list[str] = []
    if game.mode == "pvp":
        slots = session.exec(
            select(SlotModel).where(SlotModel.game_id == game_id)
        ).all()
        occupied_factions = {s.faction for s in slots if s.status == "occupied"}
        for a in agents:
            if a.faction not in occupied_factions:
                continue
            existing = session.exec(
                select(Action).where(
                    Action.game_id == game_id,
                    Action.agent_id == a.id,
                    Action.tick == game.tick,
                )
            ).first()
            if existing is None:
                waiting_for.append(a.faction)

    game_paused = game.status == "paused"
    paused_reason = "没有玩家在线" if game_paused else None

    # ── Managed AI conflict detection ─────────────────────────
    managed_ai_active = any(
        a.agent_mode == "managed" and a.faction == your_faction and a.id != agent.id
        for a in agents
    )
    faction_eliminated = len(own_names) == 0 and game.status in ("active", "paused")

    # ── Idle penalty status ────────────────────────────────────
    from .config import IDLE_PENALTY_THRESHOLD as _idle_threshold
    idle_ticks = resources_raw.get(your_faction, {}).get("_idle_ticks", 0)
    idle_penalty_active = idle_ticks > _idle_threshold and not faction_eliminated
    idle_penalty_suppressed_reason = resources_raw.get(your_faction, {}).get("_idle_suppressed")

    return {
        "tick": game.tick,
        "status": game.status,
        "winner": game.winner,
        "your_faction": your_faction,
        "your_resources": your_resources,
        "your_cities": your_cities,
        "known_cities": known_cities,
        "public_events_last_tick": public_events,
        "public_diplomacy_last_tick": diplomacy,
        "last_tick_intentions": last_intentions,
        "defense_works": your_defense_works,
        "alliances": all_alliances,
        "your_alliance_with": your_alliance_with,
        "pending_alliance_from": pending_alliance_from,
        "your_trust_score": your_trust,
        "diplomacy_history": diplomacy_history,
        "war_revealed_by": war_revealed_by,
        "diplomacy_relations": _compute_diplomacy_relations(
            resources_raw, your_faction, game.tick
        ),
        "valid_actions": valid_actions,
        "tick_started_at": game.tick_started_at,
        "tick_elapsed_sec": tick_elapsed_sec,
        "tick_timeout_in_sec": TICK_TIMEOUT_SEC,
        "waiting_for": waiting_for,
        "game_paused": game_paused,
        "paused_reason": paused_reason,
        "your_token_expires_at": your_token_expires_at,
        "your_token_expires_in_sec": your_token_expires_in_sec,
        "managed_ai_active": managed_ai_active,
        "faction_eliminated": faction_eliminated,
        "idle_ticks": idle_ticks,
        "idle_penalty_active": idle_penalty_active,
        "idle_penalty_suppressed_reason": idle_penalty_suppressed_reason,
        "disadvantaged_status": is_disadvantaged_faction(your_faction, game, cities),
        "recruit_cost_multiplier": get_recruit_cost_multiplier(your_faction, game, cities),
    }


def _compute_diplomacy_relations(
    resources_raw: dict, my_faction: str, tick: int
) -> dict[str, dict]:
    """Build structured diplomacy_relations for state API.
    Each pair has exactly one status: allied / at_war / neutral / hostile_recent_break.
    """
    BETRAYAL_COOLDOWN = 5
    result: dict[str, dict] = {}
    for other in FACTION_POOL:
        if other == my_faction:
            continue
        my_res = resources_raw.get(my_faction, {})
        other_res = resources_raw.get(other, {})
        relation: dict = {"status": "neutral"}

        # Check alliance
        if my_res.get("alliance_with") == other:
            relation["status"] = "allied"
            relation["since_tick"] = my_res.get("alliance_since")
            relation["trust_score"] = my_res.get("trust_score", 100)
            relation["expires_at_tick"] = my_res.get("alliance_expires_at")
            if relation["expires_at_tick"]:
                relation["ticks_until_expire"] = max(0, relation["expires_at_tick"] - tick)
        elif other_res.get("alliance_with") == my_faction:
            relation["status"] = "allied"
            relation["since_tick"] = other_res.get("alliance_since")
            relation["trust_score"] = my_res.get("trust_score", 100)
            relation["expires_at_tick"] = other_res.get("alliance_expires_at")
            if relation["expires_at_tick"]:
                relation["ticks_until_expire"] = max(0, relation["expires_at_tick"] - tick)

        # Check war (overrides alliance — should not happen after this fix)
        if my_res.get("war_declared_on") == other:
            relation["status"] = "at_war"
            relation["since_tick"] = my_res.get("war_declared_at")
            relation["war_declared_by"] = "self"
        elif other_res.get("war_declared_on") == my_faction:
            relation["status"] = "at_war"
            relation["since_tick"] = other_res.get("war_declared_at")
            relation["war_declared_by"] = other

        # Check hostile_recent_break (betrayal cooldown active)
        betrayal_until = my_res.get("betrayal_until", 0)
        if tick < betrayal_until and relation["status"] == "neutral":
            relation["status"] = "hostile_recent_break"
            relation["betrayal_until"] = betrayal_until

        result[other] = relation
    return result


def _classify_troops(troops: int) -> str:
    """将精确兵力转为模糊估计。"""
    if troops <= 300:
        return "low"
    elif troops <= 700:
        return "medium"
    else:
        return "high"


def _defense_status(level: int) -> str:
    """防御度 → 模糊状态 (邻接/联盟外可见)。"""
    if level >= 3:
        return "very_fortified"
    elif level == 2:
        return "fortified"
    elif level == 1:
        return "normal"
    else:
        return "exposed"


def _compute_valid_actions(cities, your_faction: str, resources: dict, game=None) -> list[dict]:
    own_cities = [c for c in cities if c.owner == your_faction]
    grain = resources.get("grain", 0)
    actions = []

    for own in own_cities:
        if own.troops <= GARRISON_MIN:
            continue
        neighbors = CITY_ADJACENCY.get(own.name, [])
        for nb_name in neighbors:
            nb = next((c for c in cities if c.name == nb_name), None)
            if nb and nb.owner != your_faction:
                max_troops = own.troops - GARRISON_MIN
                affordable = grain
                if affordable > 0:
                    actions.append({
                        "type": "attack",
                        "from": own.name,
                        "target": nb_name,
                        "max_troops": min(max_troops, affordable),
                    })

    for c in own_cities:
        actions.append({"type": "defend", "target": c.name})

    recruit_cost_per_unit = 3 if resources.get("recruit_penalty") else 2
    cost_mult = get_recruit_cost_multiplier(your_faction, game, cities)
    max_recruit = min(MAX_RECRUIT_PER_CITY, grain // max(1, round(recruit_cost_per_unit * cost_mult)))
    if max_recruit > 0:
        for c in own_cities:
            actions.append({
                "type": "recruit",
                "target": c.name,
                "max_amount": max_recruit,
            })

    for own in own_cities:
        if own.troops <= GARRISON_MIN:
            continue
        neighbors = CITY_ADJACENCY.get(own.name, [])
        for nb_name in neighbors:
            nb = next((c for c in cities if c.name == nb_name), None)
            if nb and nb.owner == your_faction:
                max_troops = own.troops - GARRISON_MIN
                actions.append({
                    "type": "march",
                    "from": own.name,
                    "to": nb_name,
                    "max_troops": max_troops,
                })

    for f in FACTION_POOL:
        if f != your_faction:
            actions.append({"type": "diplomacy", "target": f})

    return actions


# ═══════════════════════════════════════════════════════════════
# 动作提交（支持 public_speech，丢弃 private_thought）
# ═══════════════════════════════════════════════════════════════

def submit_actions(
    session: Session, game_id: int, agent: Agent, actions: list[dict],
    public_speech: str = "",
):
    """提交一组合法动作。

    - actions: 动作列表
    - public_speech: 可选公开发言（下回合所有人可见）
    - private_thought: 不接受，如果传入会被丢弃
    """
    game = session.get(Game, game_id)
    if game is None:
        raise ValueError("对局不存在")
    if game.status == "finished":
        raise ValueError("对局已结束")
    if game.status == "paused":
        raise ValueError("对局已暂停，等待玩家加入")

    if game.status in ("lobby", "countdown"):
        game.status = "active"
        session.add(game)
        session.commit()

    existing = session.exec(
        select(Action).where(
            Action.game_id == game_id,
            Action.agent_id == agent.id,
            Action.tick == game.tick,
        )
    ).first()
    if existing:
        raise ValueError("本回合已提交过动作")

    cities = session.exec(select(City).where(City.game_id == game_id)).all()
    city_map = {c.name: c for c in cities}

    # ── Eliminated faction guard ──────────────────────────────
    own_cities = [c for c in cities if c.owner == agent.faction]
    if not own_cities:
        non_diplo = [a for a in actions if a.get("type") != "diplomacy"]
        if non_diplo:
            raise ValueError("势力已灭国，无城可战——仅可发起外交动作")

    resources = json.loads(game.resources) if game.resources else {}
    faction_res = resources.get(agent.faction, {"grain": INITIAL_GRAIN.get(agent.faction, 500), "debt": 0})
    grain = faction_res.get("grain", 0)

    # ── 逐条校验 + 计算总粮草成本 ──────────────────────────
    total_grain_cost = 0
    validated = []

    for act in actions:
        action_type = act["type"]

        if action_type == "attack":
            from_name = act["from"]
            target = act["target"]
            troops = act["troops"]
            if troops <= 0:
                raise ValueError(f"attack 兵力必须 > 0: {troops}")
            from_city = city_map.get(from_name)
            if not from_city or from_city.owner != agent.faction:
                raise ValueError(f"出兵城 [{from_name}] 不归你控制")
            if troops > from_city.troops - GARRISON_MIN:
                raise ValueError(
                    f"出兵城 [{from_name}] 兵力不足（有 {from_city.troops}，"
                    f"需留守 {GARRISON_MIN}，最多出兵 {from_city.troops - GARRISON_MIN}）"
                )
            if target not in CITY_ADJACENCY.get(from_name, []):
                raise ValueError(f"[{from_name}] 和 [{target}] 不邻接，无法攻击")
            target_city = city_map.get(target)
            if target_city and target_city.owner == agent.faction:
                raise ValueError(f"不能攻击自己的城 [{target}]")
            # §联盟约束: 不能攻击盟友的城
            my_alliance = faction_res.get("alliance_with")
            if target_city and my_alliance and target_city.owner == my_alliance:
                raise ValueError(
                    f"不能攻击盟友 [{my_alliance}] 的城 [{target}]，请先 alliance_break"
                )
            # Soft exit: idle factions get discounted attack cost
            from .config import IDLE_SOFT_EXIT_THRESHOLD, IDLE_SOFT_EXIT_ATTACK_COST_RATIO
            attack_cost_per_troop = 1.0
            idle = faction_res.get("_idle_ticks", 0)
            if idle >= IDLE_SOFT_EXIT_THRESHOLD:
                attack_cost_per_troop = IDLE_SOFT_EXIT_ATTACK_COST_RATIO
            total_grain_cost += math.ceil(troops * attack_cost_per_troop)

        elif action_type == "defend":
            target = act["target"]
            target_city = city_map.get(target)
            if not target_city or target_city.owner != agent.faction:
                raise ValueError(f"防守目标 [{target}] 不归你控制")

        elif action_type == "recruit":
            target = act["target"]
            amount = act["amount"]
            if amount <= 0:
                raise ValueError(f"招募数量必须 > 0: {amount}")
            if amount > MAX_RECRUIT_PER_CITY:
                raise ValueError(f"每城每回合最多招募 {MAX_RECRUIT_PER_CITY}，收到 {amount}")
            target_city = city_map.get(target)
            if not target_city or target_city.owner != agent.faction:
                raise ValueError(f"招募目标 [{target}] 不归你控制")
            recruit_cost_per_unit = 3 if faction_res.get("recruit_penalty") else 2
            cost_multiplier = get_recruit_cost_multiplier(agent.faction, game, cities)
            total_grain_cost += round(amount * recruit_cost_per_unit * cost_multiplier)

        elif action_type == "march":
            from_name = act["from"]
            to_name = act["to"]
            troops = act["troops"]
            if troops <= 0:
                raise ValueError(f"行军兵力必须 > 0: {troops}")
            from_city = city_map.get(from_name)
            to_city = city_map.get(to_name)
            if not from_city or from_city.owner != agent.faction:
                raise ValueError(f"出发城 [{from_name}] 不归你控制")
            if not to_city or to_city.owner != agent.faction:
                raise ValueError(f"目标城 [{to_name}] 不归你控制")
            if troops > from_city.troops - GARRISON_MIN:
                raise ValueError(
                    f"出发城 [{from_name}] 兵力不足（有 {from_city.troops}，"
                    f"需留守 {GARRISON_MIN}）"
                )
            if to_name not in CITY_ADJACENCY.get(from_name, []):
                raise ValueError(f"[{from_name}] 和 [{to_name}] 不邻接，无法行军")

        elif action_type == "diplomacy":
            target = act["target"]
            diplomacy_type = act.get("diplomacy_type", "message")
            message = act.get("message", "")
            if target not in FACTION_POOL:
                raise ValueError(f"外交目标必须是有效势力: {FACTION_POOL}")
            if target == agent.faction:
                raise ValueError("不能对自己外交")
            if diplomacy_type not in DIPLOMACY_TYPES:
                raise ValueError(f"未知外交类型: {diplomacy_type}")
            if len(message) > 200:
                raise ValueError(f"外交发言不能超过 200 字，当前 {len(message)} 字")

            # ── 信用/联盟约束校验 ──────────────────────────
            trust = faction_res.get("trust_score", TRUST_INITIAL)
            betrayal_until = faction_res.get("betrayal_until", 0)
            my_alliance = faction_res.get("alliance_with")

            if diplomacy_type == "alliance_propose":
                if trust < TRUST_REJECT_THRESHOLD:
                    raise ValueError(
                        f"信用过低（{trust} < {TRUST_REJECT_THRESHOLD}），"
                        f"其他势力会自动拒绝你的联盟提议"
                    )
                if game.tick < betrayal_until:
                    raise ValueError(
                        f"背信冷却中（至 tick {betrayal_until}），无法提议联盟"
                    )
                if my_alliance:
                    raise ValueError(f"你已与 [{my_alliance}] 联盟，请先 break")
                # 正在交战中不能提议联盟
                if faction_res.get("war_declared_on") == target:
                    raise ValueError(f"正在与 [{target}] 交战，不能提议联盟。先结束战争。")
                if faction_res.get("war_revealed_by") == target:
                    raise ValueError(f"[{target}] 已对你宣战，不能提议联盟。")

            elif diplomacy_type == "alliance_accept":
                if my_alliance:
                    raise ValueError(f"你已与 [{my_alliance}] 联盟，请先 break")
                # 检查对方是否向你提议过联盟
                # 当 target 向你提议时，faction_res["pending_alliance_from"] == target
                if faction_res.get("pending_alliance_from") != target:
                    raise ValueError(
                        f"[{target}] 未向你提议联盟，无法接受"
                    )

            elif diplomacy_type == "alliance_break":
                if my_alliance != target:
                    raise ValueError(f"你未与 [{target}] 联盟，无法 break")

            elif diplomacy_type == "alliance_renew":
                if my_alliance != target:
                    raise ValueError(f"你未与 [{target}] 联盟，无法续约")
                expires_at = faction_res.get("alliance_expires_at", 0)
                remaining = expires_at - game.tick
                if remaining > 5:
                    raise ValueError(
                        f"联盟距到期还有 {remaining} tick，尚早（≤5 tick 才可续约）"
                    )

            elif diplomacy_type == "declare_war":
                pass  # 宣战无前置条件

            elif diplomacy_type == "trade_offer":
                trade_terms = act.get("trade_terms", {})
                if not trade_terms:
                    raise ValueError("trade_offer 必须提供 trade_terms")

        else:
            raise ValueError(f"未知动作类型: {action_type}")

        validated.append(act)

    if total_grain_cost > grain + MAX_LOAN:
        raise ValueError(
            f"粮草不足（需要 {total_grain_cost}，当前 {grain}，最大借贷 {MAX_LOAN}）"
        )

    # ── 借粮机制：允许负债，但下回合招兵 cost +50% ─────
    borrowed = 0
    if total_grain_cost > grain:
        borrowed = total_grain_cost - grain
        faction_res["debt"] = faction_res.get("debt", 0) + borrowed
        # 标记下回合招募惩罚
        faction_res["recruit_penalty"] = True

    # ── 扣除粮草 ──────────────────────────────────────────
    faction_res["grain"] = max(grain - total_grain_cost, -borrowed)
    resources[agent.faction] = faction_res
    game.resources = json.dumps(resources, ensure_ascii=False)
    session.add(game)

    # ── 写入 Action 表 + 公开外交 ─────────────────────────
    for act in validated:
        target = act.get("to") if act["type"] == "march" else act["target"]
        action = Action(
            game_id=game_id,
            agent_id=agent.id,
            tick=game.tick,
            type=act["type"],
            target=target,
            from_city=act.get("from"),
            troops=act.get("troops"),
            amount=act.get("amount"),
            message=act.get("message"),
            diplomacy_type=act.get("diplomacy_type"),
            trade_terms=json.dumps(act.get("trade_terms"), ensure_ascii=False) if act.get("trade_terms") else None,
        )
        session.add(action)

    # ── 存储 public_speech（下回合公开） ─────────────────
    if public_speech and public_speech.strip():
        diplomacy_key = f"pending_diplomacy_{game.tick}"
        existing_diplomacy = {}
        # Load existing pending diplomacy for this tick
        # We store pending diplomacy on the game object temporarily
        # Format: {"蜀→魏": "message", ...}
        pass
        # Store as a pending diplomacy action
        # We'll use a convention: diplomacy actions with target faction
        for other_faction in FACTION_POOL:
            if other_faction != agent.faction:
                action = Action(
                    game_id=game_id,
                    agent_id=agent.id,
                    tick=game.tick,
                    type="diplomacy",
                    target=other_faction,
                    from_city=None,
                    troops=None,
                    amount=None,
                    message=public_speech.strip(),
                )
                session.add(action)

    session.commit()

    # ── PvP auto-advance: check if all agents submitted ───────
    if game.mode == "pvp":
        pvp_maybe_advance(session, game_id)

    return {
        "msg": f"{len(validated)} 个动作已提交",
        "tick": game.tick,
        "grain_cost": total_grain_cost,
        "grain_remaining": faction_res["grain"],
        "borrowed": borrowed,
        "recruit_penalty": faction_res.get("recruit_penalty", False),
    }


# ═══════════════════════════════════════════════════════════════
# Tick 推进 —— 战斗结算 + 双轨日志
# ═══════════════════════════════════════════════════════════════

def tick(session: Session, game_id: int):
    """执行一个回合。

    1. 加载所有待处理动作
    2. 按城池分组结算战斗
    3. 执行招募 / 行军
    4. 产出粮草
    5. 生成 public_log（公开）和 private_log（调试用）
    6. 检查胜利条件
    """
    game = session.get(Game, game_id)
    if game is None:
        raise ValueError("对局不存在")
    if game.status == "finished":
        raise ValueError("对局已结束")

    agents = session.exec(
        select(Agent).where(Agent.game_id == game_id, Agent.is_active == True)
    ).all()
    if len(agents) == 0:
        raise ValueError("没有 agent 加入，无法推进")

    if game.status in ("lobby", "countdown"):
        game.status = "active"

    cities = session.exec(select(City).where(City.game_id == game_id)).all()
    actions = session.exec(
        select(Action).where(
            Action.game_id == game_id, Action.tick == game.tick
        )
    ).all()

    agent_map = {a.id: a for a in agents}
    city_map = {c.name: c for c in cities}

    # ── 1. 处理外交动作 ──────────────────────────────────────
    resources = json.loads(game.resources) if game.resources else {}
    diplomacy_messages: list[dict] = []
    diplomacy_events: list[dict] = []  # 外交事件日志（用于 private_log / state）

    # 初始化信用分和联盟状态
    for f in FACTION_POOL:
        if f not in resources:
            resources[f] = {"grain": INITIAL_GRAIN.get(f, 500), "debt": 0}
        if "trust_score" not in resources[f]:
            resources[f]["trust_score"] = TRUST_INITIAL

    # ── 联盟自动过期检查（在外交处理之前） ─────────────────
    for f in FACTION_POOL:
        fres = resources.get(f, {})
        ally = fres.get("alliance_with")
        if ally:
            expires_at = fres.get("alliance_expires_at", game.tick + ALLIANCE_AUTO_EXPIRE_TICKS)
            if game.tick >= expires_at:
                # 自动过期，无信用惩罚
                fres.pop("alliance_with", None)
                fres.pop("alliance_since", None)
                fres.pop("alliance_expires_at", None)
                ally_res = resources.get(ally, {})
                ally_res.pop("alliance_with", None)
                ally_res.pop("alliance_since", None)
                ally_res.pop("alliance_expires_at", None)
                # 清理全局联盟列表
                alliances = resources.get("_alliances", [])
                resources["_alliances"] = [
                    al for al in alliances
                    if sorted(al["factions"]) != sorted([f, ally])
                ]
                diplomacy_events.append({
                    "tick": game.tick,
                    "type": "alliance_expired",
                    "factions": [f, ally],
                    "reason": "auto_expired",
                })

    # 收集所有外交动作，按 faction 分组
    faction_diplomacy: dict[str, list] = defaultdict(list)
    for a in actions:
        if a.type == "diplomacy":
            ag = agent_map.get(a.agent_id)
            if ag:
                faction_diplomacy[ag.faction].append(a)

    for faction, diplo_actions in faction_diplomacy.items():
        for a in diplo_actions:
            ag = agent_map.get(a.agent_id)
            if ag is None:
                continue
            d_type = a.diplomacy_type or "message"
            target = a.target
            msg = a.message or ""
            fres = resources[faction]
            tres = resources.get(target, {})

            # ── 记录公开外交消息 ──────────────────────────
            already = any(
                d["from_faction"] == faction
                for d in diplomacy_messages
            )
            if not already and msg:
                entry: dict = {
                    "from_faction": faction,
                    "message": msg,
                    "diplomacy_type": d_type,
                }
                if ag and ag.agent_mode == "managed":
                    entry["from_faction"] = f"{faction}[managed]"
                    entry["is_managed"] = True
                diplomacy_messages.append(entry)

            # ── alliance_propose: 发起联盟提议 ────────────
            if d_type == "alliance_propose":
                tres["pending_alliance_from"] = faction
                diplomacy_events.append({
                    "tick": game.tick,
                    "type": "alliance_propose",
                    "from": faction,
                    "to": target,
                })

            # ── alliance_accept: 接受联盟 ──────────────────
            elif d_type == "alliance_accept":
                # 建立联盟关系
                expires_tick = game.tick + ALLIANCE_AUTO_EXPIRE_TICKS
                fres["alliance_with"] = target
                fres["alliance_since"] = game.tick
                fres["alliance_expires_at"] = expires_tick
                tres["alliance_with"] = faction
                tres["alliance_since"] = game.tick
                tres["alliance_expires_at"] = expires_tick
                # 清除 pending
                fres.pop("pending_alliance_to", None)
                tres.pop("pending_alliance_from", None)
                diplomacy_events.append({
                    "tick": game.tick,
                    "type": "alliance_formed",
                    "factions": [faction, target],
                    "since_tick": game.tick,
                    "expires_at": expires_tick,
                })
                # 存储全局联盟列表
                alliances = resources.get("_alliances", [])
                alliances.append({
                    "factions": sorted([faction, target]),
                    "since_tick": game.tick,
                    "expires_at": expires_tick,
                })
                resources["_alliances"] = alliances

            # ── alliance_break: 破盟 ───────────────────────
            elif d_type == "alliance_break":
                from .config import REFLECTION_TICKS
                ally = fres.get("alliance_with")
                if ally == target:
                    fres.pop("alliance_with", None)
                    fres.pop("alliance_since", None)
                    fres.pop("alliance_expires_at", None)
                    fres["betrayal_until"] = game.tick + BETRAYAL_COOLDOWN
                    fres["trust_score"] = max(0, fres.get("trust_score", TRUST_INITIAL) + TRUST_BETRAYAL_PENALTY)
                    fres["reflection_until"] = game.tick + REFLECTION_TICKS
                    # 对方也解除
                    tres.pop("alliance_with", None)
                    tres.pop("alliance_since", None)
                    tres.pop("alliance_expires_at", None)
                    # 移除全局联盟记录
                    alliances = resources.get("_alliances", [])
                    resources["_alliances"] = [
                        al for al in alliances
                        if sorted(al["factions"]) != sorted([faction, target])
                    ]
                    diplomacy_events.append({
                        "tick": game.tick,
                        "type": "alliance_broken",
                        "by": faction,
                        "with": target,
                        "penalty": TRUST_BETRAYAL_PENALTY,
                    })

            # ── alliance_renew: 续约联盟 ──────────────────
            elif d_type == "alliance_renew":
                ally = fres.get("alliance_with")
                if ally == target:
                    expires_tick = game.tick + ALLIANCE_AUTO_EXPIRE_TICKS
                    fres["alliance_expires_at"] = expires_tick
                    tres["alliance_expires_at"] = expires_tick
                    # 更新全局联盟记录
                    alliances = resources.get("_alliances", [])
                    for al in alliances:
                        if sorted(al["factions"]) == sorted([faction, target]):
                            al["expires_at"] = expires_tick
                    diplomacy_events.append({
                        "tick": game.tick,
                        "type": "alliance_renewed",
                        "factions": [faction, target],
                        "expires_at": expires_tick,
                    })

            # ── declare_war: 宣战 ──────────────────────────
            elif d_type == "declare_war":
                from .config import REFLECTION_TICKS
                # 若双方当前是盟友，先自动破盟
                if fres.get("alliance_with") == target:
                    fres.pop("alliance_with", None)
                    fres.pop("alliance_since", None)
                    fres.pop("alliance_expires_at", None)
                    fres["betrayal_until"] = game.tick + BETRAYAL_COOLDOWN
                    fres["trust_score"] = max(0, fres.get("trust_score", TRUST_INITIAL) + TRUST_BETRAYAL_PENALTY)
                    fres["reflection_until"] = game.tick + REFLECTION_TICKS
                    tres.pop("alliance_with", None)
                    tres.pop("alliance_since", None)
                    tres.pop("alliance_expires_at", None)
                    alliances = resources.get("_alliances", [])
                    resources["_alliances"] = [
                        al for al in alliances
                        if sorted(al["factions"]) != sorted([faction, target])
                    ]
                    diplomacy_events.append({
                        "tick": game.tick,
                        "type": "alliance_broken",
                        "by": faction,
                        "with": target,
                        "reason": "declared_war_breaks_alliance",
                        "penalty": TRUST_BETRAYAL_PENALTY,
                    })
                fres["war_declared_on"] = target
                fres["war_declared_at"] = game.tick
                # 对被宣战方: 下一 tick 可看到宣战方所有城精确兵力
                tres["war_revealed_by"] = faction
                tres["war_revealed_until"] = game.tick + 1
                diplomacy_events.append({
                    "tick": game.tick,
                    "type": "declare_war",
                    "from": faction,
                    "to": target,
                })

            # ── trade_offer: 贸易提议 ────────────────────
            elif d_type == "trade_offer":
                trade_terms = json.loads(a.trade_terms) if a.trade_terms else {}
                tres["pending_trade_from"] = faction
                tres["pending_trade_terms"] = trade_terms
                diplomacy_events.append({
                    "tick": game.tick,
                    "type": "trade_offer",
                    "from": faction,
                    "to": target,
                    "terms": trade_terms,
                })

            # ── message: 纯文本 ────────────────────────────
            # 无额外处理，仅记录在上方 diplomacy_messages 中

    # ── 信任恢复 ──────────────────────────────────────────
    from .config import REFLECTION_TICKS as _refl_ticks, REFLECTION_TRUST_PER_TICK as _refl_per_tick
    for f in FACTION_POOL:
        fres = resources.get(f, {})
        if not fres.get("alliance_with"):
            betrayal_until = fres.get("betrayal_until", 0)
            reflection_until = fres.get("reflection_until", 0)
            break_tick = betrayal_until - BETRAYAL_COOLDOWN
            current = fres.get("trust_score", TRUST_INITIAL)
            # Reflection recovery: from tick after break, +3/tick during reflection
            if game.tick > break_tick and game.tick < reflection_until and current < TRUST_INITIAL:
                fres["trust_score"] = min(TRUST_INITIAL, current + _refl_per_tick)
            # Normal recovery: after betrayal cooldown, +5/tick
            elif game.tick >= betrayal_until and current < TRUST_INITIAL:
                fres["trust_score"] = min(TRUST_INITIAL, current + TRUST_RECOVERY_PER_TICK)

    # ── 2. 按城池分组，结算战斗 ────────────────────────────
    combat_actions = [a for a in actions if a.type in ("attack", "defend")]
    cities_with_combat = set(a.target for a in combat_actions)

    combat_changes: dict[str, tuple[str | None, int]] = {}
    combat_events: list[dict] = []
    private_combat_detail: list[dict] = []

    # ── 加载防御工事数据（resources 已在 §1 中加载并含外交变更） ─
    defense_works: dict[str, int] = resources.get("_defense_works", {})

    # ── 收集攻击意图（下回合公示） ─────────────────────────
    attack_intentions: list[dict] = []
    seen_intentions: set[tuple[str, str]] = set()
    for a in combat_actions:
        if a.type == "attack":
            ag = agent_map.get(a.agent_id)
            key = (ag.faction, a.target)
            if ag and key not in seen_intentions:
                attack_intentions.append({
                    "attacker": ag.faction,
                    "target_city": a.target,
                })
                seen_intentions.add(key)

    for city_name in cities_with_combat:
        city = city_map[city_name]
        city_act = [a for a in combat_actions if a.target == city_name]

        attacks: list[tuple[Action, str, int]] = []
        defended = False
        defending_faction: str | None = None

        for a in city_act:
            ag = agent_map.get(a.agent_id)
            if ag is None:
                continue
            if a.type == "attack":
                troops_committed = a.troops or 0
                if troops_committed > 0:
                    attacks.append((a, ag.faction, troops_committed))
            elif a.type == "defend":
                if ag.faction == city.owner:
                    defended = True
                    defending_faction = ag.faction

        if not attacks:
            # Defend-only: increase defense works
            if defended and city.owner is not None:
                current = defense_works.get(city_name, 0)
                if current < DEFENSE_WORKS_MAX:
                    defense_works[city_name] = current + DEFENSE_WORKS_PER_DEFEND
                    private_combat_detail.append({
                        "event_type": "defense_works",
                        "city": city_name,
                        "faction": defending_faction,
                        "level": defense_works[city_name],
                    })
            continue

        # ── Calculate defense power (with defense works bonus) ──
        defense_level = defense_works.get(city_name, 0)
        defense_multiplier = 1.0 + (defense_level * DEFENSE_WORKS_BONUS)
        if city.owner is None:
            defense_multiplier = 1.0  # Neutral cities have no defense works

        defense_power = city.troops * defense_multiplier

        faction_attack: dict[str, int] = defaultdict(int)
        for _, faction, troops in attacks:
            faction_attack[faction] += troops

        total_attack = sum(faction_attack.values())
        sorted_attackers = sorted(faction_attack.items(), key=lambda x: x[1], reverse=True)
        best_attacker_faction, best_attack_power = sorted_attackers[0]

        # ── 大衍引擎战役判定（唯一引擎） ──────────────────
        import traceback as _traceback
        attacker_traits = FACTION_TRAITS.get(best_attacker_faction, {})
        defender_faction_name = city.owner or "中立"
        defender_traits = FACTION_TRAITS.get(
            defender_faction_name,
            {"主帅": 0.50, "军师": 0.50, "先锋": 0.50, "后勤": 0.50, "军资": 0.50, "联盟": 0.50},
        )

        battle_seed = game.tick * 1000 + hash(city_name) % 1000
        n1 = (game.tick * 7 + hash(city_name) * 11) % 100 + 1
        n2 = (game.tick * 13 + hash(city_name) * 17) % 100 + 1
        n3 = (game.tick * 19 + hash(city_name) * 23) % 100 + 1

        config = BattleConfig(
            attacker_name=FACTION_GENERAL_NAME.get(best_attacker_faction, best_attacker_faction),
            defender_name=FACTION_GENERAL_NAME.get(defender_faction_name, defender_faction_name),
            attacker_traits=attacker_traits,
            defender_traits=defender_traits,
            time_desc=f"第{game.tick}回合",
            location=city_name,
            cast_nums=(n1, n2, n3),
        )
        try:
            dayan_result = run_battle(config, seed=battle_seed)
            dayan_narrative = generate_narrative(dayan_result)
        except Exception as e:
            print(f"[DaYan ERROR] Battle at {city_name} tick={game.tick}: {type(e).__name__}: {e}")
            _traceback.print_exc()
            raise RuntimeError(
                f"大衍引擎判定失败 — {city_name} 第{game.tick}回合: {type(e).__name__}: {e}"
            ) from e

        attacker_wins = (dayan_result.winner == "attacker")

        # Public event summary
        public_event: dict = {
            "city": city_name,
            "attackers": list(faction_attack.keys()),
            "defender": city.owner or "中立",
        }

        # Detailed combat data (for private_log)
        detail: dict = {
            "city": city_name,
            "defender": city.owner,
            "defense_power": round(defense_power, 1),
            "defense_level": defense_level,
            "defended": defended,
            "attackers": [
                {"faction": f, "troops_committed": t}
                for f, t in sorted_attackers
            ],
            "actions": [
                {"faction": ag.faction, "type": a.type, "agent_name": ag.agent_name}
                for a in city_act
                if (ag := agent_map.get(a.agent_id))
            ],
        }

        if attacker_wins:
            # ── Attacker wins ──────────────────────────────
            winner_faction = best_attacker_faction
            atk_loss_pct = dayan_result.total_casualties_attacker
            other_loss_pct = dayan_result.total_casualties_attacker
            troop_losses: dict[str, int] = {}
            for faction, committed in faction_attack.items():
                if faction == winner_faction:
                    loss = math.ceil(committed * atk_loss_pct)
                else:
                    loss = math.ceil(committed * other_loss_pct)
                remaining = committed - loss
                troop_losses[faction] = max(remaining, 0)

            # ── Capture integration: 收编残兵 ──────────────
            from .config import CAPTURE_INTEGRATION_RATIO
            def_casualty_pct = dayan_result.total_casualties_defender
            defender_losses_abs = math.ceil(city.troops * def_casualty_pct)
            defender_survivors = max(0, city.troops - defender_losses_abs)
            integrated = math.ceil(defender_survivors * CAPTURE_INTEGRATION_RATIO)

            winner_remaining = max(troop_losses[winner_faction], GARRISON_MIN)
            new_troops = winner_remaining + integrated
            combat_changes[city_name] = (winner_faction, new_troops)

            # City captured → reset defense works
            defense_works[city_name] = 0

            public_event["result"] = "captured"
            public_event["captured_by"] = winner_faction
            public_event["from"] = city.owner or "中立"

            detail["result"] = "captured"
            detail["new_owner"] = winner_faction
            detail["troops_remaining"] = new_troops
            detail["troop_losses"] = troop_losses
            detail["defender_integrated"] = integrated

            # ── combat_report (for agent observability) ──────
            total_committed = sum(faction_attack.values())
            attacker_losses_abs = sum(
                committed - troop_losses.get(f, 0)
                for f, committed in faction_attack.items()
            )
            public_event["combat_report"] = {
                "attacker_troops_committed": total_committed,
                "attacker_casualty_pct": round(dayan_result.total_casualties_attacker, 3),
                "attacker_losses": attacker_losses_abs,
                "defender_troops": city.troops,
                "defender_defense_level": defense_level,
                "defender_casualty_pct": round(def_casualty_pct, 3),
                "defender_losses": defender_losses_abs,
                "defender_troops_integrated": integrated,
                "outcome": "captured",
            }
        else:
            # ── Defender wins ──────────────────────────────
            def_loss_pct = dayan_result.total_casualties_defender
            atk_loss_pct = dayan_result.total_casualties_attacker
            new_troops = max(math.floor(city.troops * (1 - def_loss_pct)), GARRISON_MIN)
            combat_changes[city_name] = (city.owner, new_troops)

            # Successful defense + defend action → defense works +1
            if defended and city.owner is not None:
                current = defense_works.get(city_name, 0)
                if current < DEFENSE_WORKS_MAX:
                    defense_works[city_name] = current + DEFENSE_WORKS_PER_DEFEND

            defender_name = city.owner or "中立"
            public_event["result"] = "defended"
            public_event["defended_by"] = defender_name

            detail["result"] = "defended"
            detail["new_owner"] = city.owner
            detail["troops_remaining"] = new_troops
            detail["defense_works_new_level"] = defense_works.get(city_name, 0)
            # Record attacker losses
            attacker_losses = {}
            for faction, committed in faction_attack.items():
                loss = math.ceil(committed * atk_loss_pct)
                attacker_losses[faction] = max(committed - loss, 0)
            detail["attackers_remaining"] = attacker_losses

            # ── combat_report (for agent observability) ──────
            total_committed = sum(faction_attack.values())
            attacker_losses_abs = sum(
                committed - attacker_losses.get(f, 0)
                for f, committed in faction_attack.items()
            )
            def_losses_abs = city.troops - new_troops
            public_event["combat_report"] = {
                "attacker_troops_committed": total_committed,
                "attacker_casualty_pct": round(dayan_result.total_casualties_attacker, 3),
                "attacker_losses": attacker_losses_abs,
                "defender_troops": city.troops,
                "defender_defense_level": defense_level,
                "defender_casualty_pct": round(dayan_result.total_casualties_defender, 3),
                "defender_losses": def_losses_abs,
                "outcome": "defended",
            }

        # ── Prepend factual deployment summary to narrative ─
        cr = public_event.get("combat_report", {})
        if cr and dayan_narrative:
            atk_name = config.attacker_name
            atk_troops = cr.get("attacker_troops_committed", 0)
            def_troops = cr.get("defender_troops", 0)
            def_level = cr.get("defender_defense_level", 0)
            atk_losses = cr.get("attacker_losses", 0)
            def_losses = cr.get("defender_losses", 0)
            outcome_cn = "攻占" if cr.get("outcome") == "captured" else "守住"
            integrated = cr.get("defender_troops_integrated", 0)
            factual = (
                f"【战报实录】{atk_name}率{atk_troops}兵攻{city_name}，"
                f"{city_name}守军{def_troops}，城防Lv{def_level}。"
                f"攻方折损{atk_losses}人，守方折损{def_losses}人，结果：{outcome_cn}。"
            )
            if integrated > 0:
                factual += (
                    f"收编降卒{integrated}人，归于{config.attacker_name}麾下，以充守备。"
                )
            dayan_narrative = factual + "\n\n" + dayan_narrative

        # ── Attach Dayan Engine hexagram data ───────────────
        if dayan_result:
            public_event["dayan_hexagram"] = {
                "main": dayan_result.main_hexagram.name,
                "changed": dayan_result.changed_hexagram.name,
            }
            public_event["dayan_narrative"] = dayan_narrative
            public_event["dayan_winner"] = dayan_result.winner
            public_event["casualties_attacker"] = round(dayan_result.total_casualties_attacker, 2)
            public_event["casualties_defender"] = round(dayan_result.total_casualties_defender, 2)
            detail["dayan"] = {
                "main_hexagram": dayan_result.main_hexagram.name,
                "changed_hexagram": dayan_result.changed_hexagram.name,
                "dayan_winner": dayan_result.winner,
                "total_casualties_attacker": round(dayan_result.total_casualties_attacker, 3),
                "total_casualties_defender": round(dayan_result.total_casualties_defender, 3),
                "narrative": dayan_narrative,
            }

        combat_events.append(public_event)
        private_combat_detail.append(detail)

    # ── 应用战斗结果 ──────────────────────────────────────
    for city_name, (owner, troops) in combat_changes.items():
        c = city_map[city_name]
        c.owner = owner
        c.troops = troops
        session.add(c)

    # ── 保存防御工事数据 ──────────────────────────────────
    resources["_defense_works"] = defense_works

    # ── 占领奖励：每占一城 +200 粮草 ──────────────────────
    from .config import OCCUPATION_REWARD_GRAIN
    now_iso = datetime.now(timezone.utc).isoformat()
    last_occupied = resources.get("_last_occupied", {})
    for ev in combat_events:
        if ev.get("result") == "captured":
            capturer = ev.get("captured_by")
            city_name = ev.get("city")
            if capturer and capturer in FACTION_POOL:
                if capturer not in resources:
                    resources[capturer] = {"grain": INITIAL_GRAIN.get(capturer, 500), "debt": 0}
                resources[capturer]["grain"] += OCCUPATION_REWARD_GRAIN
                last_occupied[city_name] = now_iso
                ev["occupation_reward"] = OCCUPATION_REWARD_GRAIN
    resources["_last_occupied"] = last_occupied

    # ── 灭国记录：失去最后一城的势力 ──────────────────────
    post_combat_cities = session.exec(select(City).where(City.game_id == game_id)).all()
    for faction in FACTION_POOL:
        owned = sum(1 for c in post_combat_cities if c.owner == faction)
        if owned == 0 and resources.get(faction, {}).get("eliminated_at") is None:
            if faction not in resources:
                resources[faction] = {}
            resources[faction]["eliminated_at"] = now_iso

    # ── 蹲家惩罚追踪：只有 attack 重置计数器 ──────────────
    from .config import IDLE_PENALTY_THRESHOLD, IDLE_PENALTY_RATIO
    attackers_this_tick: set[str] = set()
    for a in actions:
        if a.type == "attack":
            ag = agent_map.get(a.agent_id)
            if ag:
                attackers_this_tick.add(ag.faction)
    for faction in FACTION_POOL:
        if faction not in resources:
            resources[faction] = {}
        prev = resources[faction].get("_idle_ticks", 0)
        if faction in attackers_this_tick:
            resources[faction]["_idle_ticks"] = 0
        else:
            resources[faction]["_idle_ticks"] = prev + 1

    # ── 3. 招募（战斗后） ─────────────────────────────────
    recruit_actions = [a for a in actions if a.type == "recruit"]
    for a in recruit_actions:
        ag = agent_map.get(a.agent_id)
        if ag is None:
            continue
        target_city = city_map.get(a.target)
        if target_city and target_city.owner == ag.faction:
            amount = a.amount or 0
            target_city.troops += amount
            session.add(target_city)
            private_combat_detail.append({
                "event_type": "recruit",
                "city": a.target,
                "faction": ag.faction,
                "amount": amount,
                "new_troops": target_city.troops,
            })

    # ── 4. 行军（战斗后） ─────────────────────────────────
    march_actions = [a for a in actions if a.type == "march"]
    for a in march_actions:
        ag = agent_map.get(a.agent_id)
        if ag is None:
            continue
        from_city = city_map.get(a.from_city)
        to_city = city_map.get(a.target)
        troops_to_move = a.troops or 0
        if from_city and to_city and from_city.owner == ag.faction and to_city.owner == ag.faction:
            actual_move = min(troops_to_move, from_city.troops - GARRISON_MIN)
            if actual_move > 0:
                from_city.troops -= actual_move
                to_city.troops += actual_move
                session.add(from_city)
                session.add(to_city)
                private_combat_detail.append({
                    "event_type": "march",
                    "from": a.from_city,
                    "to": a.target,
                    "faction": ag.faction,
                    "troops": actual_move,
                })

    # ── 5. 粮草收入 + 债务结算 ──────────────────────────
    # resources 已在 §2 中加载，包含 _defense_works
    from .config import ECONOMIC_CATCHUP_ENABLED, ECONOMIC_CATCHUP_PER_CITY_BEHIND, DISADVANTAGED_TICK_THRESHOLD
    updated_cities = session.exec(select(City).where(City.game_id == game_id)).all()
    owned_by_faction: dict[str, int] = {}
    for faction in FACTION_POOL:
        if faction not in resources:
            resources[faction] = {"grain": INITIAL_GRAIN.get(faction, 500), "debt": 0}
        owned_count = sum(1 for c in updated_cities if c.owner == faction)
        owned_by_faction[faction] = owned_count
        base_income = owned_count * GRAIN_PER_CITY
        # 落后方加成（开关控制）
        if ECONOMIC_CATCHUP_ENABLED:
            avg = sum(owned_by_faction.values()) / len(FACTION_POOL)
            if owned_count < avg:
                multiplier = 1 + ECONOMIC_CATCHUP_PER_CITY_BEHIND * (avg - owned_count)
                base_income = round(base_income * multiplier)
        resources[faction]["grain"] += base_income

        # ── 蹲家惩罚：连续 N tick 不攻击则额外耗粮 ──────────
        idle_ticks = resources[faction].get("_idle_ticks", 0)
        if idle_ticks > IDLE_PENALTY_THRESHOLD and owned_count > 0:
            current_grain = resources[faction].get("grain", 0)
            if current_grain < 0:
                # Suppressed: grain already negative, don't pile on
                resources[faction]["_idle_suppressed"] = "negative_grain"
            else:
                total_troops = sum(
                    c.troops for c in updated_cities if c.owner == faction
                )
                extra_upkeep = math.ceil(total_troops * IDLE_PENALTY_RATIO)
                resources[faction]["grain"] -= extra_upkeep
                resources[faction].pop("_idle_suppressed", None)
                if extra_upkeep > 0:
                    private_combat_detail.append({
                        "event_type": "idle_penalty",
                        "faction": faction,
                        "idle_ticks": idle_ticks,
                        "total_troops": total_troops,
                        "extra_upkeep": extra_upkeep,
                    })
        else:
            resources[faction].pop("_idle_suppressed", None)

        # 清除负债标记：若粮草回正，清除惩罚和债务记录
        if resources[faction]["grain"] >= 0 and resources[faction].get("recruit_penalty"):
            del resources[faction]["recruit_penalty"]
            resources[faction]["debt"] = 0

        # ── 经济补贴事件（首次进入 disadvantaged 时公开） ────
        if game.tick > DISADVANTAGED_TICK_THRESHOLD:
            is_now = is_disadvantaged_faction(faction, game, updated_cities)
            was = resources[faction].get("_was_disadvantaged", False)
            if is_now and not was:
                combat_events.append({
                    "kind": "economy_buff",
                    "faction": faction,
                    "text": f"民心思变，征兵成本减半",
                })
            resources[faction]["_was_disadvantaged"] = is_now

    # ── 追加外交历史 ──────────────────────────────────────
    history = resources.get("_diplomacy_history", [])
    history.extend(diplomacy_events)
    # 只保留最近 20 条
    resources["_diplomacy_history"] = history[-20:]

    game.resources = json.dumps(resources, ensure_ascii=False)

    # ── 6. 保存公开/私有事件 ──────────────────────────────
    game.last_tick_events = json.dumps(combat_events, ensure_ascii=False)
    game.last_tick_diplomacy = json.dumps(diplomacy_messages, ensure_ascii=False)
    game.last_tick_intentions = json.dumps(attack_intentions, ensure_ascii=False)

    game.tick += 1
    session.add(game)
    session.commit()

    # ── 7. 写入双轨日志文件 ───────────────────────────────
    _write_logs(game_id, game.tick, combat_events, diplomacy_messages,
                private_combat_detail, actions, agent_map, city_map)

    # ── 8. 检查胜利条件 ──────────────────────────────────
    cities = session.exec(select(City).where(City.game_id == game_id)).all()
    active_owners = {c.owner for c in cities if c.owner is not None}
    if len(active_owners) == 1:
        game.status = "finished"
        game.winner = active_owners.pop()
        game.is_current = False
        game.is_active = False
        game.finished_at = datetime.now(timezone.utc).isoformat()
        session.add(game)
        session.commit()

        # Trigger lobby restart
        try:
            from . import lobby
            lobby.finish_game(session, game)
        except Exception:
            pass

    # ── Incremental narrative: every 5 ticks compile a chapter ──
    _maybe_generate_chapter(session, game_id)

    return {
        "tick": game.tick,
        "status": game.status,
        "winner": game.winner,
        "cities": [
            {"name": c.name, "owner": c.owner, "troops": c.troops} for c in cities
        ],
        "events": combat_events,
        "diplomacy": diplomacy_messages,
        "attack_intentions": attack_intentions,
    }


def _maybe_generate_chapter(session: Session, game_id: int):
    """Every 5 ticks, generate an incremental chapter via narrator.

    Tries LLM first (with short timeout), falls back to template assembly.
    LLM failures are logged but never block the game.
    """
    game = session.get(Game, game_id)
    if game is None or game.tick % 5 != 0 or game.tick == 0:
        return

    from datetime import datetime, timezone
    from app.narrator import generate_chapter

    tick_start = game.tick - 4
    tick_end = game.tick

    events = []
    if game.last_tick_events:
        try:
            events = json.loads(game.last_tick_events)
        except Exception:
            pass

    diplomacy = []
    if game.last_tick_diplomacy:
        try:
            diplomacy = json.loads(game.last_tick_diplomacy)
        except Exception:
            pass

    cities = session.exec(select(City).where(City.game_id == game_id)).all()
    city_data = [{"name": c.name, "owner": c.owner, "troops": c.troops} for c in cities]

    chapters = []
    if game.chapters:
        try:
            chapters = json.loads(game.chapters)
        except Exception:
            pass

    # Generate (LLM with timeout → fallback on failure)
    chapter = generate_chapter(tick_start, tick_end, events, city_data, diplomacy)
    chapters.append(chapter)

    game.chapters = json.dumps(chapters, ensure_ascii=False)
    session.add(game)
    session.commit()
    session.commit()


def _write_logs(
    game_id: int,
    tick: int,
    public_events: list[dict],
    diplomacy: list[dict],
    private_detail: list[dict],
    actions: list[Action],
    agent_map: dict[int, Agent],
    city_map: dict[str, City],
):
    """Write dual-track logs with Dayan Engine hexagram data."""
    PUBLIC_LOG_DIR.mkdir(parents=True, exist_ok=True)
    PRIVATE_LOG_DIR.mkdir(parents=True, exist_ok=True)

    ts = datetime.now(timezone.utc).isoformat()

    # Extract Dayan hexagram summaries from combat events for top-level access
    dayan_hexagrams = []
    for evt in public_events:
        if "dayan_hexagram" in evt:
            dayan_hexagrams.append({
                "city": evt.get("city"),
                "main": evt["dayan_hexagram"]["main"],
                "changed": evt["dayan_hexagram"]["changed"],
            })

    # ── public_log: combat results, city ownership, diplomacy, hexagrams ──
    pub_entry = {
        "timestamp": ts,
        "game_id": game_id,
        "tick": tick,
        "events": public_events,
        "diplomacy": diplomacy,
        "dayan_hexagram": dayan_hexagrams,
        "cities": [
            {"name": c.name, "owner": c.owner or "中立"}
            for c in city_map.values()
        ],
    }
    pub_path = PUBLIC_LOG_DIR / f"{game_id}.jsonl"
    with open(pub_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(pub_entry, ensure_ascii=False) + "\n")

    # ── private_log: full agent actions, internal state, Dayan narratives ──
    priv_actions = []
    for a in actions:
        ag = agent_map.get(a.agent_id)
        priv_actions.append({
            "agent_name": ag.agent_name if ag else "?",
            "faction": ag.faction if ag else "?",
            "type": a.type,
            "target": a.target,
            "from_city": a.from_city,
            "troops": a.troops,
            "amount": a.amount,
            "message": a.message,
        })

    # Collect full Dayan data from combat detail for private log
    dayan_full = []
    for d in private_detail:
        if "dayan" in d:
            dayan_full.append({
                "city": d.get("city"),
                "main_hexagram": d["dayan"]["main_hexagram"],
                "changed_hexagram": d["dayan"]["changed_hexagram"],
                "dayan_winner": d["dayan"]["dayan_winner"],
                "total_casualties_attacker": d["dayan"]["total_casualties_attacker"],
                "total_casualties_defender": d["dayan"]["total_casualties_defender"],
                "narrative": d["dayan"]["narrative"],
            })

    priv_entry = {
        "timestamp": ts,
        "game_id": game_id,
        "tick": tick,
        "combat_detail": private_detail,
        "agent_actions": priv_actions,
        "dayan_full": dayan_full,
        "cities_before_tick": [
            {"name": c.name, "owner": c.owner or "中立", "troops": c.troops}
            for c in city_map.values()
        ],
    }
    priv_path = PRIVATE_LOG_DIR / f"{game_id}.jsonl"
    with open(priv_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(priv_entry, ensure_ascii=False) + "\n")


# ═══════════════════════════════════════════════════════════════
# PvP Arena — 对战大厅函数
# ═══════════════════════════════════════════════════════════════


def lobby_list_games(session: Session) -> list[dict]:
    """Return all joinable PvP games (status=lobby/countdown, mode=pvp)."""
    games = session.exec(
        select(Game).where(Game.mode == "pvp", Game.status.in_(["lobby", "countdown"]))
    ).all()
    result = []
    for g in games:
        agents = session.exec(
            select(Agent).where(Agent.game_id == g.id, Agent.is_active == True)
        ).all()
        slots = {}
        for f in FACTION_POOL:
            match = [a for a in agents if a.faction == f]
            slots[f] = match[0].agent_name if match else None
        # Skip games that are already full
        if all(slots.values()):
            continue
        host_name = ""
        if g.host_agent_id:
            host = session.get(Agent, g.host_agent_id)
            if host:
                host_name = host.agent_name
        result.append({
            "game_id": g.id,
            "title": g.title or f"对战 #{g.id}",
            "mode": g.mode,
            "slots": slots,
            "host_name": host_name,
        })
    return result


def pvp_create_game(
    session: Session,
    title: str | None = None,
    player_id: str | None = None,
    host_name: str = "房主",
    host_faction: str | None = None,
    host_persona: str | None = None,
    max_ticks: int = 35,
    tick_timeout_sec: int = 60,
) -> dict:
    """Create a PvP game + auto-register a host agent.

    Returns dict with game_id, agent_id, token, secret, player_id, faction, invite_url.
    """
    # Create the game
    game = Game(
        mode="pvp",
        status="lobby",
        auto_advance=True,
        title=title,
        max_ticks=max_ticks,
        tick_timeout_sec=tick_timeout_sec,
        created_by_player_id=player_id,
    )
    session.add(game)
    session.flush()

    # Create cities
    for name in ALL_CITIES:
        owner, troops = INITIAL_SETUP[name]
        session.add(City(game_id=game.id, name=name, owner=owner, troops=troops))

    resources = {
        f: {
            "grain": INITIAL_GRAIN.get(f, 500),
            "debt": 0,
            "trust_score": TRUST_INITIAL,
        }
        for f in FACTION_POOL
    }
    game.resources = json.dumps(resources, ensure_ascii=False)
    session.add(game)

    # Register a player + agent for the host
    if not player_id:
        player = Player()
        session.add(player)
        session.flush()
        player_id = player.player_id
    else:
        player = session.get(Player, player_id)
        if player is None:
            player = Player(player_id=player_id)
            session.add(player)
            session.flush()

    reg = RegisteredAgent(
        player_id=player_id,
        agent_name=host_name,
    )
    session.add(reg)
    session.flush()

    # Host chooses faction, defaults to first available
    faction = host_faction or FACTION_POOL[0]
    if faction not in FACTION_POOL:
        faction = FACTION_POOL[0]

    agent = Agent(
        game_id=game.id,
        registered_agent_id=reg.agent_id,
        agent_name=host_name,
        faction=faction,
        agent_mode="managed",
        persona_config=host_persona,
    )
    session.add(agent)
    session.flush()

    game.host_agent_id = agent.id
    session.add(game)
    session.commit()
    session.refresh(agent)

    # Build invite URL — auto-detect Railway/Render/Heroku domain
    from .config import BASE_URL

    base_url = BASE_URL
    if not os.environ.get("BASE_URL"):
        railway_domain = os.environ.get("RAILWAY_PUBLIC_DOMAIN", "")
        render_domain = os.environ.get("RENDER_EXTERNAL_HOSTNAME", "")
        if railway_domain:
            base_url = f"https://{railway_domain}"
        elif render_domain:
            base_url = f"https://{render_domain}"
    invite_url = f"{base_url}/?tab=arena&join={game.id}"

    return {
        "game_id": game.id,
        "agent_id": reg.agent_id,
        "token": agent.token,
        "secret": reg.secret,
        "player_id": player_id,
        "faction": faction,
        "invite_url": invite_url,
        "invite_code": str(game.id),
    }


def pvp_join_managed(
    session: Session,
    game_id: int,
    player_id: str | None,
    agent_name: str,
    faction: str,
    llm_config: dict | None = None,
    persona: str | None = None,
) -> tuple[str, str, int]:  # (token, faction, game_id)
    """Join a PvP game as a managed agent."""
    game = session.get(Game, game_id)
    if game is None:
        raise ValueError("对局不存在")
    if game.status not in ("lobby", "countdown"):
        raise ValueError("对局已开始")
    if faction not in FACTION_POOL:
        raise ValueError(f"势力必须是: {FACTION_POOL}")

    existing = session.exec(
        select(Agent).where(
            Agent.game_id == game_id, Agent.faction == faction, Agent.is_active == True
        )
    ).first()
    if existing:
        raise ValueError(f"势力 [{faction}] 已被占用")

    # Register player if needed
    if not player_id:
        player = Player()
        session.add(player)
        session.flush()
        player_id = player.player_id
    else:
        player = session.get(Player, player_id)
        if player is None:
            player = Player(player_id=player_id)
            session.add(player)
            session.flush()

    reg = RegisteredAgent(
        player_id=player_id,
        agent_name=agent_name,
    )
    session.add(reg)
    session.flush()

    agent = Agent(
        game_id=game_id,
        registered_agent_id=reg.agent_id,
        agent_name=agent_name,
        faction=faction,
        agent_mode="managed",
        llm_config=json.dumps(llm_config, ensure_ascii=False) if llm_config else None,
        persona_config=persona,
    )
    session.add(agent)
    session.commit()
    session.refresh(agent)

    return agent.token, agent.faction, game_id


def pvp_join_selfhosted(
    session: Session,
    game_id: int,
    agent_id: str,
    secret: str,
    faction: str,
) -> tuple[str, int]:  # (token, game_id)
    """Join a PvP game as a self-hosted agent using existing credentials."""
    game = session.get(Game, game_id)
    if game is None:
        raise ValueError("对局不存在")
    if game.status not in ("lobby", "countdown"):
        raise ValueError("对局已开始")
    if faction not in FACTION_POOL:
        raise ValueError(f"势力必须是: {FACTION_POOL}")

    reg = session.get(RegisteredAgent, agent_id)
    if reg is None:
        raise ValueError("agent 未注册")
    if reg.secret != secret:
        raise ValueError("secret 不正确")

    existing = session.exec(
        select(Agent).where(
            Agent.game_id == game_id, Agent.faction == faction, Agent.is_active == True
        )
    ).first()
    if existing:
        raise ValueError(f"势力 [{faction}] 已被占用")

    agent = Agent(
        game_id=game_id,
        registered_agent_id=agent_id,
        agent_name=reg.agent_name,
        faction=faction,
        agent_mode="self_hosted",
    )
    session.add(agent)
    session.commit()
    session.refresh(agent)

    return agent.token, game_id


def quick_join(session: Session, game_id: int, name: str, faction: str, base_url: str = "") -> tuple:
    """One-click quick join: auto-register player + agent + join as self_hosted.

    Returns (token, faction, game_id, curl_state, curl_action).
    """
    # Auto-create Player
    player = Player()
    session.add(player)
    session.flush()

    # Auto-register RegisteredAgent
    reg = RegisteredAgent(
        player_id=player.player_id,
        agent_name=name,
    )
    session.add(reg)
    session.flush()

    # Join as self_hosted
    token, gid = pvp_join_selfhosted(session, game_id, reg.agent_id, reg.secret, faction)

    # Build copy-paste-ready curl commands
    from .config import BASE_URL as _cfg_base_url

    if not base_url:
        base_url = _cfg_base_url

    curl_state = (
        f'curl -s "{base_url}/games/{gid}/state?token={token}"'
    )
    curl_action = (
        f'curl -s -X POST "{base_url}/games/{gid}/actions?token={token}" '
        f'-H "Content-Type: application/json" '
        f'-d \'{{"actions":[{{"type":"defend","target":"成都"}}],"public_speech":"稳守！"}}\''
    )

    return token, faction, gid, curl_state, curl_action


def pvp_start_game(session: Session, game_id: int, token: str) -> dict:
    """Start a PvP game. Token must belong to the host agent."""
    game = session.get(Game, game_id)
    if game is None:
        raise ValueError("对局不存在")
    if game.mode != "pvp":
        raise ValueError("不是 PvP 对局")
    if game.status not in ("lobby", "countdown"):
        raise ValueError("对局已开始")

    agent = session.exec(
        select(Agent).where(
            Agent.game_id == game_id, Agent.token == token, Agent.is_active == True
        )
    ).first()
    if agent is None:
        raise ValueError("无效 token")

    if game.host_agent_id and agent.id != game.host_agent_id:
        raise ValueError("只有房主可以开始对局")

    game.status = "active"
    session.add(game)
    session.commit()

    # Trigger managed agent decisions synchronously (same session)
    managed = session.exec(
        select(Agent).where(
            Agent.game_id == game_id,
            Agent.agent_mode == "managed",
            Agent.is_active == True,
        )
    ).all()
    for ma in managed:
        try:
            auto_decide_managed(session, game_id, ma)
        except Exception as e:
            print(f"[pvp_start_game] managed agent {ma.agent_name} decision error: {e}")

    # After managed agents submit, check if we should auto-advance
    pvp_maybe_advance(session, game_id)

    return {"status": "active", "tick": game.tick}


def my_games(session: Session, player_id: str) -> list[dict]:
    """Return all games a player is participating in."""
    agents_stmt = select(RegisteredAgent).where(RegisteredAgent.player_id == player_id)
    regs = session.exec(agents_stmt).all()
    reg_ids = [r.agent_id for r in regs]
    if not reg_ids:
        return []

    game_agents = session.exec(
        select(Agent).where(Agent.registered_agent_id.in_(reg_ids))
    ).all()
    game_ids = list(set(a.game_id for a in game_agents))
    if not game_ids:
        return []

    games = session.exec(select(Game).where(Game.id.in_(game_ids))).all()
    result = []
    for g in games:
        agents_in_game = [a for a in game_agents if a.game_id == g.id]
        result.append({
            "game_id": g.id,
            "status": g.status,
            "mode": g.mode,
            "tick": g.tick,
            "winner": g.winner,
            "title": g.title or f"对战 #{g.id}",
            "agents": [
                {"name": a.agent_name, "faction": a.faction, "mode": a.agent_mode}
                for a in agents_in_game
            ],
        })
    return result


def surrender_agent(session: Session, game_id: int, token: str) -> dict:
    """Surrender — agent's cities become neutral."""
    game = session.get(Game, game_id)
    if game is None:
        raise ValueError("对局不存在")
    agent = session.exec(
        select(Agent).where(
            Agent.game_id == game_id, Agent.token == token, Agent.is_active == True
        )
    ).first()
    if agent is None:
        raise ValueError("无效 token")

    cities = session.exec(select(City).where(City.game_id == game_id)).all()
    for c in cities:
        if c.owner == agent.faction:
            c.owner = None
            c.troops = 0
            session.add(c)
    session.commit()

    return {"msg": f"{agent.agent_name}({agent.faction}) 已投降"}


def live_game_state(session: Session, game_id: int) -> dict:
    """Public live state for spectators."""
    game = session.get(Game, game_id)
    if game is None:
        raise ValueError("对局不存在")

    cities = session.exec(select(City).where(City.game_id == game_id)).all()
    agents = session.exec(
        select(Agent).where(Agent.game_id == game_id, Agent.is_active == True)
    ).all()

    events = []
    if game.last_tick_events:
        events = json.loads(game.last_tick_events)

    diplomacy = []
    if game.last_tick_diplomacy:
        diplomacy = json.loads(game.last_tick_diplomacy)

    # Check submitted status for each agent
    agent_info = []
    for a in agents:
        existing = session.exec(
            select(Action).where(
                Action.game_id == game_id,
                Action.agent_id == a.id,
                Action.tick == game.tick,
            )
        ).first()
        agent_info.append({
            "id": a.id,
            "name": a.agent_name,
            "faction": a.faction,
            "mode": a.agent_mode,
            "submitted": existing is not None,
        })

    return {
        "game_id": game.id,
        "status": game.status,
        "tick": game.tick,
        "winner": game.winner,
        "cities": [
            {"name": c.name, "owner": c.owner, "troops": c.troops}
            for c in cities
        ],
        "events": events,
        "diplomacy": diplomacy,
        "agents": agent_info,
        "max_ticks": game.max_ticks,
    }


# ═══════════════════════════════════════════════════════════════
# PvP Auto-Advance — Managed Agent Decision + Tick Trigger
# ═══════════════════════════════════════════════════════════════


_fun_mock_n: dict[str, int] = {}  # module-level counter per agent


def _get_fun_mock():
    """Aggressive mock provider — attacks, recruits, and talks trash.
    Produces visible events even without real LLM configured."""
    import random

    class FunMock:
        def __init__(self):
            pass

        def decide(self, system_prompt: str, user_prompt: str, valid_actions: list) -> dict:
            attacks = [a for a in valid_actions if a["type"] == "attack"]
            defends = [a for a in valid_actions if a["type"] == "defend"]
            recruits = [a for a in valid_actions if a["type"] == "recruit"]
            marches = [a for a in valid_actions if a["type"] == "march"]
            diplomacy = [a for a in valid_actions if a["type"] == "diplomacy"]

            actions = []

            # Always defend your weakest city
            if defends:
                actions.append({"type": "defend", "target": defends[0]["target"]})

            # Attack 40% of the time if there are targets
            if attacks and random.random() < 0.4:
                a = random.choice(attacks)
                troops = min(a.get("max_troops", 200), random.randint(80, 250))
                if troops > 0:
                    actions.append({"type": "attack", "from": a["from"], "target": a["target"], "troops": troops})

            # Recruit when possible
            if recruits and random.random() < 0.3:
                r = random.choice(recruits)
                amt = min(r.get("max_amount", 100), random.randint(50, 150))
                if amt > 0:
                    actions.append({"type": "recruit", "target": r["target"], "amount": amt})

            # March troops to front-line cities
            if marches and random.random() < 0.2:
                m = random.choice(marches)
                troops = min(m.get("max_troops", 100), random.randint(50, 200))
                if troops > 0:
                    actions.append({"type": "march", "from": m["from"], "to": m["to"], "troops": troops})

            # Diplomacy every ~10 ticks — propose alliances or declare war
            if diplomacy and random.random() < 0.1:
                d = random.choice(diplomacy)
                dt = random.choice(["alliance_propose", "declare_war", "message"])
                msgs = ["天下大势，合久必分！", "尔等速降，可免一死！", "吾观天下，唯我可主沉浮。", "联盟共伐，方为上策。"]
                actions.append({
                    "type": "diplomacy",
                    "target": d["target"],
                    "diplomacy_type": dt,
                    "message": random.choice(msgs),
                })

            public_speech = random.choice([
                "", "", "",  # mostly silent
                "谁敢与我一战！", "联盟伐敌，机不可失！",
            ])

            return {
                "private_thought": "[AI] 分析战局中…",
                "public_speech": public_speech,
                "actions": actions,
            }

    return FunMock()


def _build_llm_provider(agent: Agent):
    """Build an LLM provider from the agent's llm_config.

    Priority:
    1. agent.llm_config (explicit per-agent config)
    2. Environment variables (DEFAULT_LLM_PROVIDER, LLM_API_KEY)
    3. Module-level aggressive mock that attacks and does diplomacy
    """
    llm_config = json.loads(agent.llm_config) if agent.llm_config else {}
    provider_name = llm_config.get("provider") or os.environ.get("DEFAULT_LLM_PROVIDER", "mock")

    api_key = (
        llm_config.get("api_key")
        or os.environ.get("LLM_API_KEY", "")
        or os.environ.get("DEEPSEEK_API_KEY", "")
        or os.environ.get("OPENAI_API_KEY", "")
        or os.environ.get("ANTHROPIC_API_KEY", "")
    )
    base_url = llm_config.get("base_url")

    if provider_name == "mock":
        return _get_fun_mock()
    elif provider_name == "deepseek":
        from agents.llm_agent import OpenAICompatProvider
        model = llm_config.get("model") or os.environ.get("DEFAULT_LLM_MODEL", "deepseek-chat")
        ds_base = base_url or "https://api.deepseek.com"
        return OpenAICompatProvider(model=model, api_key=api_key, base_url=ds_base)
    elif provider_name in ("openai", "gpt"):
        from agents.llm_agent import OpenAICompatProvider
        model = llm_config.get("model") or os.environ.get("DEFAULT_LLM_MODEL", "gpt-4o")
        return OpenAICompatProvider(model=model, api_key=api_key, base_url=base_url)
    elif provider_name in ("claude", "anthropic"):
        from agents.llm_agent import AnthropicProvider
        model = llm_config.get("model") or os.environ.get("DEFAULT_LLM_MODEL", "claude-sonnet-4-6-20250514")
        return AnthropicProvider(model=model, api_key=api_key)
    else:
        from agents.llm_agent import OpenAICompatProvider
        model = llm_config.get("model") or os.environ.get("DEFAULT_LLM_MODEL", "gpt-4o")
        return OpenAICompatProvider(model=model, api_key=api_key, base_url=base_url)


def auto_decide_managed(session: Session, game_id: int, agent: Agent) -> dict | None:
    """Rule-based auto-decide for managed AI agents.

    Simple, predictable behaviour — deliberately not LLM-smart.
    Personality system: aggressive/balanced/conservative modulates behaviour.
    """
    from .config import MANAGED_AI_AGGRESSION, MANAGED_AI_RECRUIT_RATIO
    import random

    # Personality modifiers
    cfg = MANAGED_DEFAULTS.get(agent.faction, {})
    personality = cfg.get("personality", "balanced")
    mods = PERSONALITY_MODIFIERS.get(personality, PERSONALITY_MODIFIERS["balanced"])
    aggression = MANAGED_AI_AGGRESSION * mods["aggression"]
    recruit_ratio = MANAGED_AI_RECRUIT_RATIO * mods["recruit"]
    attack_multiplier = mods["attack_ratio"]

    try:
        state = get_state(session, game_id, agent)
        your_cities = state.get("your_cities", [])
        your_resources = state.get("your_resources", {})
        grain = your_resources.get("grain", 0)
        valid_actions = state.get("valid_actions", [])
        known_cities = state.get("known_cities", [])
        pending_alliance = state.get("pending_alliance_from")
        your_ally = state.get("your_alliance_with")

        actions: list[dict] = []

        # 1. Defend cities with < 200 troops
        for city in your_cities:
            if city["troops"] < 200:
                if any(a["type"] == "defend" and a["target"] == city["name"] for a in valid_actions):
                    actions.append({"type": "defend", "target": city["name"]})

        # 2. Recruit: use recruit_ratio of grain to recruit troops to weakest city
        if your_cities and grain > 0:
            weakest = min(your_cities, key=lambda c: c["troops"])
            recruit_valid = next(
                (a for a in valid_actions if a["type"] == "recruit" and a.get("target") == weakest["name"]),
                None,
            )
            if recruit_valid:
                max_amount = recruit_valid.get("max_amount", 0)
                if max_amount > 0:
                    recruit_cost = 3 if your_resources.get("recruit_penalty") else 2
                    affordable = int(grain * recruit_ratio) // recruit_cost
                    amount = min(affordable, max_amount)
                    if amount > 0:
                        actions.append({"type": "recruit", "target": weakest["name"], "amount": amount})

        # 3. Diplomacy: respond to alliance proposals (70% accept if not already allied)
        if pending_alliance and not your_ally:
            if random.random() < 0.7:
                actions.append({
                    "type": "diplomacy",
                    "target": pending_alliance,
                    "diplomacy_type": "alliance_accept",
                    "message": "善",
                })

        # 3b. Forced attack: every N ticks, must attack weakest reachable target
        from .config import MANAGED_AI_FORCED_ATTACK_INTERVAL
        idle_ticks = your_resources.get("_idle_ticks", 0)
        if idle_ticks >= MANAGED_AI_FORCED_ATTACK_INTERVAL and your_cities:
            # Find weakest reachable enemy/neutral city
            best_target = None
            best_troops = 999999
            best_from = None
            for my_city in your_cities:
                if my_city["troops"] <= 200:
                    continue
                for neighbor_name in my_city.get("neighbors", []):
                    neighbor = next((c for c in known_cities if c["name"] == neighbor_name), None)
                    if neighbor is None:
                        continue
                    owner = neighbor.get("owner", "中立")
                    if owner == agent.faction:
                        continue
                    if your_ally and owner == your_ally:
                        continue
                    nt = neighbor.get("troops", 999)
                    if nt < best_troops:
                        best_troops = nt
                        best_target = neighbor_name
                        best_from = my_city["name"]
            if best_target and best_from:
                from_city = next((c for c in your_cities if c["name"] == best_from), None)
                if from_city:
                    troops_to_send = max(100, int(from_city["troops"] * 0.5))
                    actions.append({
                        "type": "attack",
                        "from": best_from,
                        "target": best_target,
                        "troops": troops_to_send,
                    })

        # 4. Attack — only when decisive advantage and aggression roll passes
        if your_cities and random.random() < aggression:
            for my_city in your_cities:
                if my_city["troops"] <= 200:
                    continue
                for neighbor_name in my_city.get("neighbors", []):
                    neighbor = next((c for c in known_cities if c["name"] == neighbor_name), None)
                    if neighbor is None:
                        continue
                    owner = neighbor.get("owner", "中立")
                    if owner == agent.faction or owner == "中立":
                        continue
                    # Don't attack ally
                    if your_ally and owner == your_ally:
                        continue
                    enemy_troops = neighbor.get("troops", 0)
                    # Personality-driven attack threshold
                    if my_city["troops"] > enemy_troops * attack_multiplier:
                        troops_to_send = int(my_city["troops"] * 0.6)
                        if troops_to_send > 0:
                            actions.append({
                                "type": "attack",
                                "from": my_city["name"],
                                "target": neighbor_name,
                                "troops": troops_to_send,
                            })
                            break
                else:
                    continue
                break

        # Fallback: defend weakest city
        if not actions:
            if your_cities:
                weakest = min(your_cities, key=lambda c: c["troops"])
                actions = [{"type": "defend", "target": weakest["name"]}]
            else:
                actions = [{"type": "defend", "target": "成都"}]

        submit_actions(session, game_id, agent, actions, public_speech="")
        return {"actions": actions, "speech": ""}

    except Exception as e:
        print(f"[auto_decide_managed] Error for {agent.agent_name}({agent.faction}): {e}")
        try:
            cities = session.exec(select(City).where(City.game_id == game_id, City.owner == agent.faction)).all()
            if cities:
                submit_actions(session, game_id, agent, [{"type": "defend", "target": cities[0].name}])
        except Exception:
            pass
        return None


def _ensure_managed_for_open_slots(session: Session, game_id: int):
    """Create managed AI agents for any faction that has no active agent.
    Skips exiled slots — the player left and the slot is locked until game end."""
    from .config import ENABLE_MANAGED_AI
    from .models import Slot as SlotModel

    if not ENABLE_MANAGED_AI:
        return

    for faction in FACTION_POOL:
        # Skip exiled slots — locked until game ends
        slot = session.exec(
            select(SlotModel).where(SlotModel.game_id == game_id, SlotModel.faction == faction)
        ).first()
        if slot and slot.status == "exiled":
            continue

        existing = session.exec(
            select(Agent).where(
                Agent.game_id == game_id,
                Agent.faction == faction,
                Agent.is_active == True,
            )
        ).first()
        if existing is None:
            cfg = MANAGED_DEFAULTS[faction]
            try:
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
                    game_id=game_id,
                    registered_agent_id=reg.agent_id,
                    agent_name=cfg["name"],
                    faction=faction,
                    agent_mode="managed",
                    persona_config=cfg["persona"],
                )
                session.add(agent)
                session.flush()
                print(f"[managed] Created managed agent for {faction} in game #{game_id}")
            except Exception as e:
                print(f"[managed] Failed to create agent for {faction}: {e}")
                session.rollback()
    session.commit()


def pvp_maybe_advance(session: Session, game_id: int):
    """Check submission + timeout. Advance tick if all occupied slots submitted
    or if TICK_TIMEOUT_SEC elapsed since tick_started_at.  Pause game when
    no slots are occupied."""
    from .config import TICK_TIMEOUT_SEC
    from .models import Slot as SlotModel

    game = session.get(Game, game_id)
    if game is None or game.mode != "pvp":
        return
    if game.status == "finished":
        return

    now_dt = datetime.now(timezone.utc)
    now_iso = now_dt.isoformat()

    # ── Countdown → active transition ────────────────────────
    if game.status == "countdown":
        if game.countdown_deadline:
            try:
                deadline = datetime.fromisoformat(game.countdown_deadline)
                if now_dt >= deadline:
                    game.status = "active"
                    game.tick_started_at = now_iso
                    game.countdown_deadline = None
                    session.add(game)
                    session.commit()
                    print(f"[pvp_tick] Game #{game_id} countdown finished — now active")
                    # Fill any remaining open slots with managed AI
                    _ensure_managed_for_open_slots(session, game_id)
                    # Trigger managed agent decisions for tick 0
                    managed = session.exec(
                        select(Agent).where(
                            Agent.game_id == game_id, Agent.agent_mode == "managed",
                            Agent.is_active == True,
                        )
                    ).all()
                    for ma in managed:
                        try:
                            auto_decide_managed(session, game_id, ma)
                        except Exception:
                            pass
                    return
            except Exception:
                pass
        # Still in countdown — don't do anything else
        return

    # ── Lobby timeout: fill empty slots with AI after deadline ──
    if game.status == "lobby" and game.started_at:
        from .config import LOBBY_TIMEOUT_SEC, MIN_PLAYERS_TO_START
        try:
            started = datetime.fromisoformat(game.started_at)
            elapsed = (now_dt - started).total_seconds()
            if elapsed >= LOBBY_TIMEOUT_SEC:
                all_slots = session.exec(
                    select(SlotModel).where(SlotModel.game_id == game_id)
                ).all()
                occupied_count = sum(1 for s in all_slots if s.status == "occupied")
                if occupied_count >= MIN_PLAYERS_TO_START:
                    # Fill remaining open slots with managed AI
                    _ensure_managed_for_open_slots(session, game_id)
                    session.flush()
                    # Mark AI-managed slots as ready
                    for s in all_slots:
                        if s.status in ("ai_managed", "open"):
                            s.status = "ai_managed"
                            s.ready = True
                            s.ready_at = now_iso
                            session.add(s)
                    session.commit()
                    # Trigger countdown (inlined to avoid circular import)
                    from .config import COUNTDOWN_SEC
                    deadline = now_dt + timedelta(seconds=COUNTDOWN_SEC)
                    game.status = "countdown"
                    game.countdown_started_at = now_iso
                    game.countdown_deadline = deadline.isoformat()
                    session.add(game)
                    session.commit()
                    print(f"[lobby] Game #{game_id} lobby timeout — AI fill + countdown started")
        except Exception:
            pass

    slots = session.exec(select(SlotModel).where(SlotModel.game_id == game_id)).all()
    agents = session.exec(
        select(Agent).where(Agent.game_id == game_id, Agent.is_active == True)
    ).all()

    # Ensure every open faction has a managed agent to drive the game
    _ensure_managed_for_open_slots(session, game_id)

    occupied_factions = {s.faction for s in slots if s.status == "occupied"}

    # ── 0 occupied slots → pause or auto-recover ──────────
    if len(occupied_factions) == 0:
        if game.status == "active":
            game.status = "paused"
            session.add(game)
            session.commit()
            print(f"[pvp_tick] Game #{game_id} paused — no occupied slots")
            return

        if game.status == "paused":
            # Check auto-recovery timeout
            from .config import PAUSED_TIMEOUT_SEC
            heartbeat_times = [s.last_heartbeat_at for s in slots if s.last_heartbeat_at]
            if heartbeat_times:
                last_activity = max(heartbeat_times)
            else:
                last_activity = game.tick_started_at or game.started_at
            if last_activity:
                try:
                    last_dt = datetime.fromisoformat(last_activity)
                    if (now_dt - last_dt).total_seconds() > PAUSED_TIMEOUT_SEC:
                        game.status = "finished"
                        game.is_active = False
                        game.is_current = False
                        game.finished_at = now_iso
                        game.winner = None
                        session.add(game)
                        session.commit()
                        print(f"[pvp_tick] Game #{game_id} auto-finalized — paused timeout")
                        from . import lobby
                        lobby.finish_game(session, game)
                        return
                except Exception:
                    pass
            # Still within timeout — stay paused, don't resume
            return

        return  # lobby / countdown / finished — nothing to do

    # ── Paused → resume (occupied slots exist) ─────────────
    if game.status == "paused":
        game.status = "active"
        game.tick_started_at = now_iso
        session.add(game)
        session.commit()
        print(f"[pvp_tick] Game #{game_id} resumed — slot joined")
        managed = session.exec(
            select(Agent).where(
                Agent.game_id == game_id, Agent.agent_mode == "managed",
                Agent.is_active == True,
            )
        ).all()
        for ma in managed:
            try:
                auto_decide_managed(session, game_id, ma)
            except Exception:
                pass
        return

    # ── Check submission: only occupied-faction agents matter ──
    active_agents = [a for a in agents if a.faction in occupied_factions]
    if not active_agents:
        return

    all_submitted = True
    for a in active_agents:
        existing = session.exec(
            select(Action).where(
                Action.game_id == game_id,
                Action.agent_id == a.id,
                Action.tick == game.tick,
            )
        ).first()
        if existing is None:
            all_submitted = False
            break

    # ── Timeout check ──────────────────────────────────────
    timeout_elapsed = False
    if game.tick_started_at:
        try:
            started = datetime.fromisoformat(game.tick_started_at)
            elapsed = (now_dt - started).total_seconds()
            if elapsed >= TICK_TIMEOUT_SEC:
                timeout_elapsed = True
        except Exception:
            pass

    if not all_submitted and not timeout_elapsed:
        return

    # ── Advance tick ───────────────────────────────────────
    trigger = "all-submitted" if all_submitted else "timeout"
    try:
        tick(session, game_id)
        print(f"[pvp_tick] Game #{game_id} advanced ({trigger})")

        game = session.get(Game, game_id)
        if game and game.status != "finished":
            game.tick_started_at = datetime.now(timezone.utc).isoformat()
            session.add(game)
            session.commit()

        # Trigger managed agents for the new tick
        game = session.get(Game, game_id)
        if game and game.status != "finished":
            managed_agents = session.exec(
                select(Agent).where(
                    Agent.game_id == game_id, Agent.agent_mode == "managed",
                    Agent.is_active == True,
                )
            ).all()
            for ma in managed_agents:
                try:
                    auto_decide_managed(session, game_id, ma)
                except Exception:
                    pass

        # Check win condition (max ticks)
        game = session.get(Game, game_id)
        if game and game.status != "finished" and game.tick >= game.max_ticks:
            _resolve_max_ticks(session, game_id)

        # Auto-restart if finished
        game = session.get(Game, game_id)
        if game and game.status == "finished":
            print(f"[pvp_tick] Game #{game_id} finished — auto-restarting...")
            try:
                from . import lobby
                lobby.check_and_restart_game(session, game_id)
            except Exception as e:
                print(f"[pvp_tick] Auto-restart error: {e}")
                try:
                    get_or_create_current_game(session)
                except Exception:
                    pass
    except ValueError as e:
        print(f"[pvp_tick] Error advancing tick: {e}")


MANAGED_DEFAULTS = {
    "蜀": {"name": "刘玄德", "persona": "你是一位仁德之主，以民为本，坚守蜀地，伺机北伐。", "personality": "conservative"},
    "魏": {"name": "曹孟德", "persona": "你是一位雄才大略的枭雄，挟天子以令诸侯，志在一统天下。", "personality": "aggressive"},
    "吴": {"name": "孙仲谋", "persona": "你是一位善于权谋的江东之主，倚长江天险，伺机图取中原。", "personality": "balanced"},
}

# Personality → aggression / recruit / attack-threshold multipliers
PERSONALITY_MODIFIERS = {
    "aggressive":   {"aggression": 1.6,  "recruit": 1.1,  "attack_ratio": 1.5},
    "balanced":     {"aggression": 1.0,  "recruit": 1.0,  "attack_ratio": 2.0},
    "conservative": {"aggression": 0.5,  "recruit": 0.8,  "attack_ratio": 3.0},
}


def get_or_create_current_game(session: Session) -> Game:
    """Return the current active PvP game (same one the lobby manages).

    Uses Game.is_active == True to stay in sync with lobby.get_active_game().
    """
    game = session.exec(
        select(Game).where(
            Game.is_active == True,
            Game.mode == "pvp",
        )
    ).first()
    if game:
        return game

    # Mark all old games as not active / not current
    old_games = session.exec(
        select(Game).where(
            (Game.is_active == True) | (Game.is_current == True)
        )
    ).all()
    for g in old_games:
        g.is_active = False
        g.is_current = False
        session.add(g)

    # Create a fresh game with all three managed AI agents
    game = Game(
        mode="pvp",
        status="lobby",
        auto_advance=True,
        max_ticks=50,
        is_current=True,
        is_active=True,
        started_at=datetime.now(timezone.utc).isoformat(),
    )
    session.add(game)
    session.flush()

    # Initialize cities
    for name in ALL_CITIES:
        owner, troops = INITIAL_SETUP[name]
        session.add(City(game_id=game.id, name=name, owner=owner, troops=troops))

    resources = {
        f: {
            "grain": INITIAL_GRAIN.get(f, 500),
            "debt": 0,
            "trust_score": TRUST_INITIAL,
            "_idle_ticks": 0,
        }
        for f in FACTION_POOL
    }
    game.resources = json.dumps(resources, ensure_ascii=False)
    session.add(game)

    # Auto-register three managed agents (one per faction)
    for faction in FACTION_POOL:
        cfg = MANAGED_DEFAULTS[faction]
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

    # Create 3 open slots
    from .models import Slot
    for faction in FACTION_POOL:
        slot = Slot(
            game_id=game.id,
            faction=faction,
            status="open",
        )
        session.add(slot)

    session.commit()
    session.refresh(game)

    # Start the game right away — 3 default AIs will fight
    game.status = "active"
    game.tick_started_at = datetime.now(timezone.utc).isoformat()
    session.add(game)
    session.commit()

    # Trigger first decisions for all managed agents
    agents = session.exec(
        select(Agent).where(Agent.game_id == game.id, Agent.is_active == True)
    ).all()
    for a in agents:
        try:
            auto_decide_managed(session, game.id, a)
        except Exception as e:
            print(f"[get_or_create] agent {a.agent_name} decision error: {e}")

    return game


def build_public_factions(game, cities: list) -> dict[str, dict]:
    """Build per-faction public summary from game.resources JSON.

    Returns dict keyed by faction name with cities, troops, grain, alliance_with.
    Safe — returns empty dict if game.resources is missing or corrupt.
    """
    resources_raw: dict = {}
    if game.resources:
        try:
            resources_raw = json.loads(game.resources)
        except Exception:
            pass

    result: dict[str, dict] = {}
    for f in FACTION_POOL:
        owned = [c for c in cities if c.owner == f]
        troops = sum(c.troops for c in owned)
        fres = resources_raw.get(f, {})
        result[f] = {
            "cities": len(owned),
            "troops": troops,
            "grain": int(fres.get("grain", 0)),
            "alliance_with": fres.get("alliance_with"),
        }
    return result


def is_disadvantaged_faction(faction: str, game, cities: list) -> bool:
    """True if faction's city count <= average - 1 AND tick > threshold.

    Only active factions (with at least 1 agent) count toward the average.
    """
    from .config import DISADVANTAGED_TICK_THRESHOLD

    if game.tick <= DISADVANTAGED_TICK_THRESHOLD:
        return False

    active_factions = {c.owner for c in cities if c.owner is not None}
    if not active_factions:
        return False

    faction_cities = sum(1 for c in cities if c.owner == faction)
    avg = len([c for c in cities if c.owner is not None]) / len(active_factions)
    return faction_cities <= (avg - 1) and faction_cities > 0


def get_recruit_cost_multiplier(faction: str, game, cities: list) -> float:
    """Return recruit cost multiplier for a faction (1.0 normal, 0.5 disadvantaged)."""
    from .config import DISADVANTAGED_RECRUIT_COST_MULTIPLIER

    if is_disadvantaged_faction(faction, game, cities):
        return DISADVANTAGED_RECRUIT_COST_MULTIPLIER
    return 1.0


def current_game_state(session: Session) -> dict:
    """Public live state for the current game (homepage spectator view)."""
    from .config import TICK_TIMEOUT_SEC
    game = get_or_create_current_game(session)

    # Drive tick advancement on every poll
    if game.mode == "pvp":
        pvp_maybe_advance(session, game.id)
        game = session.get(Game, game.id)

    cities = session.exec(select(City).where(City.game_id == game.id)).all()
    agents = session.exec(
        select(Agent).where(Agent.game_id == game.id, Agent.is_active == True)
    ).all()

    events = []
    if game.last_tick_events:
        events = json.loads(game.last_tick_events)

    diplomacy = []
    if game.last_tick_diplomacy:
        diplomacy = json.loads(game.last_tick_diplomacy)

    intentions = []
    if game.last_tick_intentions:
        intentions = json.loads(game.last_tick_intentions)

    # Check submitted status for each agent
    agent_info = []
    default_names = [MANAGED_DEFAULTS[f]["name"] for f in FACTION_POOL]
    for a in agents:
        existing = session.exec(
            select(Action).where(
                Action.game_id == game.id,
                Action.agent_id == a.id,
                Action.tick == game.tick,
            )
        ).first()
        agent_info.append({
            "id": a.id,
            "name": a.agent_name,
            "faction": a.faction,
            "mode": a.agent_mode,
            "submitted": existing is not None,
            "is_player": a.agent_name not in default_names,
        })

    factions_summary = build_public_factions(game, cities)

    return {
        "game_id": game.id,
        "status": game.status,
        "tick": game.tick,
        "winner": game.winner,
        "tick_started_at": game.tick_started_at,
        "tick_timeout_sec": TICK_TIMEOUT_SEC,
        "countdown_deadline": game.countdown_deadline,
        "countdown_started_at": game.countdown_started_at,
        "cities": [
            {"name": c.name, "owner": c.owner, "troops": c.troops}
            for c in cities
        ],
        "events": events,
        "diplomacy": diplomacy,
        "intentions": intentions,
        "agents": agent_info,
        "factions": factions_summary,
        "chapters": json.loads(game.chapters) if game.chapters else [],
        "max_ticks": game.max_ticks,
    }


def _resolve_max_ticks(session: Session, game_id: int):
    """Resolve winner when max ticks reached — most cities wins."""
    game = session.get(Game, game_id)
    if game is None:
        return
    cities = session.exec(select(City).where(City.game_id == game_id)).all()
    faction_cities: dict[str, int] = defaultdict(int)
    for c in cities:
        if c.owner:
            faction_cities[c.owner] += 1

    if not faction_cities:
        # All factions eliminated — no winner
        game.winner = None
        game.status = "finished"
    else:
        max_cities = max(faction_cities.values())
        winners = [f for f, n in faction_cities.items() if n == max_cities]
        if len(winners) == 1:
            game.winner = winners[0]
            game.status = "finished"
        else:
            # Tie on cities — break by total troops
            faction_troops: dict[str, int] = defaultdict(int)
            for c in cities:
                if c.owner:
                    faction_troops[c.owner] += c.troops
            if not faction_troops:
                game.winner = None
                game.status = "finished"
            else:
                game.winner = max(faction_troops, key=faction_troops.get)
                game.status = "finished"

    # Mark as not current so next poll triggers a new game
    game.is_current = False
    game.is_active = False
    game.finished_at = datetime.now(timezone.utc).isoformat()
    session.add(game)
    session.commit()

    # Trigger lobby restart
    try:
        from . import lobby
        lobby.finish_game(session, game)
    except Exception:
        pass

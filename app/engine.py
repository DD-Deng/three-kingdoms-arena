import json
import math
import os
import random
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from sqlmodel import Session, select
from .models import Game, Agent, City, Action, Player, RegisteredAgent

# ── Dayan Engine integration ──────────────────────────────────
_DAYAN_PATH = Path(__file__).resolve().parent.parent.parent / "DaYan Engine"
if _DAYAN_PATH.exists() and str(_DAYAN_PATH) not in sys.path:
    sys.path.insert(0, str(_DAYAN_PATH))

try:
    from dayan_engine.core.types import BattleConfig  # noqa: E402
    from dayan_engine.core.battle import run_battle  # noqa: E402
    from dayan_engine.narrator.template_narrator import generate as generate_narrative  # noqa: E402
    HAS_DAYAN = True
except ImportError:
    HAS_DAYAN = False

USE_DAYAN_ENGINE = HAS_DAYAN  # Toggle: set False to fall back to simple combat

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

# ── 战斗参数（详见 docs/combat-rules.md §2） ──────────────────
ATTACKER_WIN_LOSS = 0.25        # 进攻胜: 损失 25% (曾 30%)    —— §2.1
ATTACKER_LOSE_LOSS = 0.60       # 进攻败: 损失 60% (曾 100%)   —— §2.1
ATTACKER_MIN_LOSS = 0.10        # 进攻方最低损失 10%            —— §2.1
DEFENDER_WIN_LOSS = 0.50        # 防守胜: 守方损失 50%          —— §2.2
DEFENDER_LOSE_LOSS = 0.30       # 防守败: 守方损失 30%          —— §2.2
GARRISON_MIN = 100
MAX_RECRUIT_PER_CITY = 200

# ── 防御工事系统（详见 docs/combat-rules.md §3） ─────────────
DEFENSE_WORKS_MAX = 5           # 最大防御度                     —— §3.1
DEFENSE_WORKS_PER_DEFEND = 1    # 每次 defend +1 防御度          —— §3.1
DEFENSE_WORKS_BONUS = 0.20      # 每点防御度 +20% 防守战力       —— §3.1

# ── 协同进攻参数（详见 docs/combat-rules.md §4） ─────────────
# 协同条件: 双方在同一 tick attack 同一目标 + 双方在最近 3 tick 内
#          通过 diplomacy alliance_accept 确认过联盟
# 协同效果: 攻击力相加, 占城后胜方得城, 另一方获"友城标记"(3 tick 互不攻击)
COORDINATED_ATTACK_WINDOW = 3   # 联盟有效窗口 (tick)           —— §4.2

# ── 外交与信用系统（详见 docs/diplomacy-rules.md） ──────────
DIPLOMACY_TYPES = [
    "alliance_propose", "alliance_accept", "alliance_break",
    "declare_war", "trade_offer", "message",
]
TRUST_INITIAL = 100
TRUST_BETRAYAL_PENALTY = -30      # alliance_break 扣 30
TRUST_ALLY_ATTACK_PENALTY = -50   # 盟期内攻击盟友扣 50（且自动 break）
TRUST_RECOVERY_PER_TICK = 5       # 7 tick 不背叛，每 tick +5（上限 100）
TRUST_REJECT_THRESHOLD = 50       # trust < 50 → 其他人自动拒绝你的联盟提议
BETRAYAL_COOLDOWN = 5             # 破盟后 5 tick 内联盟提议自动被拒

# 日志目录
LOG_DIR = Path("logs")
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
    if game.status != "waiting" and game.tick > 0:
        raise ValueError("对局已开始")
    if faction not in FACTION_POOL:
        raise ValueError(f"势力必须是: {FACTION_POOL}")

    reg = session.get(RegisteredAgent, agent_id)
    if reg is None:
        raise ValueError("agent 未注册")
    if reg.secret != secret:
        raise ValueError("secret 不正确")

    existing = session.exec(
        select(Agent).where(Agent.game_id == game_id, Agent.faction == faction)
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
    cities = session.exec(select(City).where(City.game_id == game_id)).all()
    agents = session.exec(select(Agent).where(Agent.game_id == game_id)).all()

    your_faction = agent.faction

    # ── 你的城池（精确信息） ──────────────────────────────
    your_cities = []
    own_names = set()
    for c in cities:
        if c.owner == your_faction:
            neighbors = CITY_ADJACENCY.get(c.name, [])
            your_cities.append({
                "name": c.name,
                "troops": c.troops,
                "neighbors": neighbors,
            })
            own_names.add(c.name)

    # ── 已知城池（按距离分层） ────────────────────────────
    # 计算所有与我方城池邻接的外部城
    adjacent_to_own: set[str] = set()
    for name in own_names:
        for nb in CITY_ADJACENCY.get(name, []):
            if nb not in own_names:
                adjacent_to_own.add(nb)

    # ── 宣战信息: 被宣战方看到宣战方全部精确兵力 ──────────
    resources_raw = {}
    if game.resources:
        resources_raw = json.loads(game.resources)
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
    for c in cities:
        if c.name in own_names:
            continue
        owner_display = c.owner if c.owner else "中立"
        if c.name in visible_cities:
            known_cities.append({
                "name": c.name,
                "owner": owner_display,
                "troops": c.troops,
                "info_freshness": "current",
            })
        else:
            known_cities.append({
                "name": c.name,
                "owner": owner_display,
                "troops_estimate": _classify_troops(c.troops),
                "info_freshness": "rumor",
            })

    # ── 资源 ──────────────────────────────────────────────
    resources = {}
    if game.resources:
        resources = json.loads(game.resources)
    your_resources = resources.get(your_faction, {"grain": 0})

    # ── 合法动作 ──────────────────────────────────────────
    valid_actions = _compute_valid_actions(cities, your_faction, your_resources)

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
    resources_raw = {}
    if game.resources:
        resources_raw = json.loads(game.resources)
    your_defense_works = {}
    for city_name in own_names:
        your_defense_works[city_name] = resources_raw.get("_defense_works", {}).get(city_name, 0)

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

    # ── 宣战信息: 是否有人对你宣战 ────────────────────────
    war_revealed_by = resources_raw.get(your_faction, {}).get("war_revealed_by")

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
        "valid_actions": valid_actions,
    }


def _classify_troops(troops: int) -> str:
    """将精确兵力转为模糊估计。"""
    if troops <= 300:
        return "low"
    elif troops <= 700:
        return "medium"
    else:
        return "high"


def _compute_valid_actions(cities, your_faction: str, resources: dict) -> list[dict]:
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
    max_recruit = min(MAX_RECRUIT_PER_CITY, grain // recruit_cost_per_unit)
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

    if game.status == "waiting":
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
            total_grain_cost += troops * 1

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
            total_grain_cost += amount * recruit_cost_per_unit

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

    agents = session.exec(select(Agent).where(Agent.game_id == game_id)).all()
    if len(agents) == 0:
        raise ValueError("没有 agent 加入，无法推进")

    if game.status == "waiting":
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
                diplomacy_messages.append({
                    "from_faction": faction,
                    "message": msg,
                    "diplomacy_type": d_type,
                })

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
                fres["alliance_with"] = target
                fres["alliance_since"] = game.tick
                tres["alliance_with"] = faction
                tres["alliance_since"] = game.tick
                # 清除 pending
                fres.pop("pending_alliance_to", None)
                tres.pop("pending_alliance_from", None)
                diplomacy_events.append({
                    "tick": game.tick,
                    "type": "alliance_formed",
                    "factions": [faction, target],
                    "since_tick": game.tick,
                })
                # 存储全局联盟列表
                alliances = resources.get("_alliances", [])
                alliances.append({
                    "factions": sorted([faction, target]),
                    "since_tick": game.tick,
                })
                resources["_alliances"] = alliances

            # ── alliance_break: 破盟 ───────────────────────
            elif d_type == "alliance_break":
                ally = fres.get("alliance_with")
                if ally == target:
                    fres.pop("alliance_with", None)
                    fres.pop("alliance_since", None)
                    fres["betrayal_until"] = game.tick + BETRAYAL_COOLDOWN
                    fres["trust_score"] = max(0, fres.get("trust_score", TRUST_INITIAL) + TRUST_BETRAYAL_PENALTY)
                    # 对方也解除
                    tres.pop("alliance_with", None)
                    tres.pop("alliance_since", None)
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

            # ── declare_war: 宣战 ──────────────────────────
            elif d_type == "declare_war":
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

    # ── 信任恢复: 每 tick +5（7 tick 未背叛的势力） ──────
    for f in FACTION_POOL:
        fres = resources.get(f, {})
        if not fres.get("alliance_with"):
            betrayal_until = fres.get("betrayal_until", 0)
            if game.tick >= betrayal_until:
                current = fres.get("trust_score", TRUST_INITIAL)
                if current < TRUST_INITIAL:
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

        # ── Dayan Engine battle resolution ──────────────────
        dayan_result = None
        dayan_narrative = ""
        if USE_DAYAN_ENGINE:
            try:
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
                dayan_result = run_battle(config, seed=battle_seed)
                dayan_narrative = generate_narrative(dayan_result)
            except Exception:
                dayan_result = None
                dayan_narrative = ""

        # Dayan Engine is the sole determinant of battle outcomes.
        # Fall back to power comparison only if Dayan Engine is unavailable.
        if dayan_result is not None:
            attacker_wins = (dayan_result.winner == "attacker")
        else:
            attacker_wins = total_attack > defense_power

        # Public event summary
        public_event: dict = {"city": city_name}

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
            atk_loss_pct = dayan_result.total_casualties_attacker if dayan_result else ATTACKER_WIN_LOSS
            other_loss_pct = dayan_result.total_casualties_attacker if dayan_result else ATTACKER_LOSE_LOSS
            troop_losses: dict[str, int] = {}
            for faction, committed in faction_attack.items():
                if faction == winner_faction:
                    loss = math.ceil(committed * atk_loss_pct)
                else:
                    loss = math.ceil(committed * other_loss_pct)
                remaining = committed - loss
                troop_losses[faction] = max(remaining, 0)

            new_troops = max(troop_losses[winner_faction], GARRISON_MIN)
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
        else:
            # ── Defender wins ──────────────────────────────
            def_loss_pct = dayan_result.total_casualties_defender if dayan_result else DEFENDER_WIN_LOSS
            atk_loss_pct = dayan_result.total_casualties_attacker if dayan_result else ATTACKER_LOSE_LOSS
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

        # ── Attach Dayan Engine hexagram data ───────────────
        if dayan_result:
            public_event["dayan_hexagram"] = {
                "main": dayan_result.main_hexagram.name,
                "changed": dayan_result.changed_hexagram.name,
            }
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
    updated_cities = session.exec(select(City).where(City.game_id == game_id)).all()
    for faction in FACTION_POOL:
        if faction not in resources:
            resources[faction] = {"grain": INITIAL_GRAIN.get(faction, 500), "debt": 0}
        owned_count = sum(1 for c in updated_cities if c.owner == faction)
        resources[faction]["grain"] += owned_count * GRAIN_PER_CITY
        # 清除负债标记：若粮草回正，清除惩罚和债务记录
        if resources[faction]["grain"] >= 0 and resources[faction].get("recruit_penalty"):
            del resources[faction]["recruit_penalty"]
            resources[faction]["debt"] = 0

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
        session.add(game)
        session.commit()

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
    """Return all joinable PvP games (status=waiting, mode=pvp)."""
    games = session.exec(
        select(Game).where(Game.mode == "pvp", Game.status == "waiting")
    ).all()
    result = []
    for g in games:
        agents = session.exec(select(Agent).where(Agent.game_id == g.id)).all()
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
        status="waiting",
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
    base_url = os.environ.get("BASE_URL")
    if not base_url:
        railway_domain = os.environ.get("RAILWAY_PUBLIC_DOMAIN", "")
        render_domain = os.environ.get("RENDER_EXTERNAL_HOSTNAME", "")
        if railway_domain:
            base_url = f"https://{railway_domain}"
        elif render_domain:
            base_url = f"https://{render_domain}"
        else:
            base_url = "http://localhost:8000"
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
    if game.status != "waiting":
        raise ValueError("对局已开始")
    if faction not in FACTION_POOL:
        raise ValueError(f"势力必须是: {FACTION_POOL}")

    existing = session.exec(
        select(Agent).where(Agent.game_id == game_id, Agent.faction == faction)
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
    if game.status != "waiting":
        raise ValueError("对局已开始")
    if faction not in FACTION_POOL:
        raise ValueError(f"势力必须是: {FACTION_POOL}")

    reg = session.get(RegisteredAgent, agent_id)
    if reg is None:
        raise ValueError("agent 未注册")
    if reg.secret != secret:
        raise ValueError("secret 不正确")

    existing = session.exec(
        select(Agent).where(Agent.game_id == game_id, Agent.faction == faction)
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
    if not base_url:
        base_url = os.environ.get("BASE_URL", "http://localhost:8000")

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
    if game.status != "waiting":
        raise ValueError("对局已开始")

    agent = session.exec(
        select(Agent).where(Agent.game_id == game_id, Agent.token == token)
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
        select(Agent).where(Agent.game_id == game_id, Agent.token == token)
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
    agents = session.exec(select(Agent).where(Agent.game_id == game_id)).all()

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


def _build_llm_provider(agent: Agent):
    """Build an LLM provider from the agent's llm_config.

    Priority:
    1. agent.llm_config (explicit per-agent config)
    2. Environment variables (DEFAULT_LLM_PROVIDER, LLM_API_KEY)
    3. Fallback to mock provider
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
        from agents.llm_agent import MockProvider
        return MockProvider()
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
    """Auto-decide for a managed agent using LLM."""
    try:
        from agents.prompts import build_prompt

        state = get_state(session, game_id, agent)
        valid_actions = state.get("valid_actions", [])
        persona = agent.persona_config or "你是一位三国时期的君主。"

        system_prompt, user_prompt = build_prompt(persona, state)
        provider = _build_llm_provider(agent)

        parsed = provider.decide(system_prompt, user_prompt, valid_actions)
        actions = parsed.get("actions", [])
        if not actions and "action" in parsed:
            actions = [parsed["action"]]
        public_speech = parsed.get("public_speech", "")

        # Validate & clamp actions
        clamped = []
        for act in actions:
            atype = act.get("type")
            if atype == "attack":
                from_c = act.get("from")
                target = act.get("target")
                troops = act.get("troops", 0)
                valid = next((a for a in valid_actions if a["type"] == "attack" and a.get("from") == from_c and a.get("target") == target), None)
                if valid:
                    troops = min(troops, valid.get("max_troops", troops))
                    if troops > 0:
                        clamped.append({"type": "attack", "from": from_c, "target": target, "troops": troops})
            elif atype == "defend":
                target = act.get("target")
                valid = next((a for a in valid_actions if a["type"] == "defend" and a.get("target") == target), None)
                if valid:
                    clamped.append({"type": "defend", "target": target})
            elif atype == "recruit":
                target = act.get("target")
                amount = act.get("amount", 0)
                valid = next((a for a in valid_actions if a["type"] == "recruit" and a.get("target") == target), None)
                if valid:
                    amount = min(amount, valid.get("max_amount", amount))
                    if amount > 0:
                        clamped.append({"type": "recruit", "target": target, "amount": amount})
            elif atype == "march":
                from_c = act.get("from")
                to = act.get("to")
                troops = act.get("troops", 0)
                valid = next((a for a in valid_actions if a["type"] == "march" and a.get("from") == from_c and a.get("to") == to), None)
                if valid:
                    troops = min(troops, valid.get("max_troops", troops))
                    if troops > 0:
                        clamped.append({"type": "march", "from": from_c, "to": to, "troops": troops})
            elif atype == "diplomacy":
                target = act.get("target")
                valid = next((a for a in valid_actions if a["type"] == "diplomacy" and a.get("target") == target), None)
                if valid:
                    clamped.append({
                        "type": "diplomacy",
                        "target": target,
                        "diplomacy_type": act.get("diplomacy_type", "message"),
                        "message": act.get("message", ""),
                    })

        if not clamped:
            # Fallback: defend first own city
            your_cities = state.get("your_cities", [])
            if your_cities:
                clamped = [{"type": "defend", "target": your_cities[0]["name"]}]
            else:
                clamped = [{"type": "defend", "target": state.get("known_cities", [{}])[0].get("name", "洛阳")}]

        submit_actions(session, game_id, agent, clamped, public_speech=public_speech)
        return {"actions": clamped, "speech": public_speech}

    except Exception as e:
        print(f"[auto_decide_managed] Error for {agent.agent_name}({agent.faction}): {e}")
        # Fallback: defend first own city
        try:
            cities = session.exec(select(City).where(City.game_id == game_id, City.owner == agent.faction)).all()
            if cities:
                submit_actions(session, game_id, agent, [{"type": "defend", "target": cities[0].name}])
        except Exception:
            pass
        return None


def pvp_maybe_advance(session: Session, game_id: int):
    """Check if all agents have submitted for current tick. If so, auto-tick."""
    game = session.get(Game, game_id)
    if game is None or game.mode != "pvp":
        return

    if game.status == "finished":
        return

    agents = session.exec(select(Agent).where(Agent.game_id == game_id)).all()
    all_submitted = True
    for a in agents:
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

    if not all_submitted:
        return

    # All submitted — advance the tick
    try:
        result = tick(session, game_id)
        print(f"[pvp_tick] Game #{game_id} tick {game.tick - 1} → {game.tick}")

        # After tick, trigger managed agents to decide for the new tick
        game = session.get(Game, game_id)
        if game and game.status != "finished":
            managed_agents = session.exec(
                select(Agent).where(
                    Agent.game_id == game_id,
                    Agent.agent_mode == "managed",
                )
            ).all()
            for ma in managed_agents:
                auto_decide_managed(session, game_id, ma)

        # Check win condition (max ticks)
        game = session.get(Game, game_id)
        if game and game.status != "finished" and game.tick >= game.max_ticks:
            _resolve_max_ticks(session, game_id)

        # Auto-restart: if game just finished, create a fresh one
        game = session.get(Game, game_id)
        if game and game.status == "finished":
            print(f"[pvp_tick] Game #{game_id} finished. Auto-creating new game...")
            try:
                get_or_create_current_game(session)
            except Exception as e:
                print(f"[pvp_tick] Auto-restart error: {e}")
    except ValueError as e:
        print(f"[pvp_tick] Error advancing tick: {e}")


MANAGED_DEFAULTS = {
    "蜀": {"name": "刘玄德", "persona": "你是一位仁德之主，以民为本，坚守蜀地，伺机北伐。"},
    "魏": {"name": "曹孟德", "persona": "你是一位雄才大略的枭雄，挟天子以令诸侯，志在一统天下。"},
    "吴": {"name": "孙仲谋", "persona": "你是一位善于权谋的江东之主，倚长江天险，伺机图取中原。"},
}


def get_or_create_current_game(session: Session) -> Game:
    """Return the current active/waiting PvP game, or create a new one.

    The current game is the one with is_current=True, mode=pvp,
    and status in (waiting, active). If none exists, creates a fresh game
    with three managed AI agents pre-joined.
    """
    game = session.exec(
        select(Game).where(
            Game.is_current == True,
            Game.mode == "pvp",
            Game.status.in_(["waiting", "active"]),
        )
    ).first()
    if game:
        return game

    # Mark all old games as not current
    old_games = session.exec(
        select(Game).where(Game.is_current == True)
    ).all()
    for g in old_games:
        g.is_current = False
        session.add(g)

    # Create a fresh game with all three managed AI agents
    game = Game(
        mode="pvp",
        status="waiting",
        auto_advance=True,
        max_ticks=35,
        is_current=True,
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

    session.commit()
    session.refresh(game)
    return game


def join_current_game(session: Session, name: str, faction: str, persona: str | None = None) -> dict:
    """Join the current game as a managed agent, replacing the default AI for that faction."""
    game = get_or_create_current_game(session)
    if game.status not in ("waiting", "active"):
        raise ValueError("当前对局不允许加入")

    if faction not in FACTION_POOL:
        raise ValueError(f"势力必须是: {FACTION_POOL}")

    # Check if the faction already has a player (non-default AI name)
    existing = session.exec(
        select(Agent).where(Agent.game_id == game.id, Agent.faction == faction)
    ).first()
    if existing and existing.agent_name not in [
        MANAGED_DEFAULTS[f]["name"] for f in FACTION_POOL
    ]:
        raise ValueError(f"势力 [{faction}] 已被玩家 [{existing.agent_name}] 占用")

    # Remove the default AI agent if it exists
    if existing:
        # Delete any submitted actions from this agent for current tick
        actions_to_del = session.exec(
            select(Action).where(
                Action.game_id == game.id,
                Action.agent_id == existing.id,
                Action.tick == game.tick,
            )
        ).all()
        for a in actions_to_del:
            session.delete(a)
        session.delete(existing)
        session.flush()

    # Register new player
    player = Player()
    session.add(player)
    session.flush()

    reg = RegisteredAgent(
        player_id=player.player_id,
        agent_name=name,
    )
    session.add(reg)
    session.flush()

    agent = Agent(
        game_id=game.id,
        registered_agent_id=reg.agent_id,
        agent_name=name,
        faction=faction,
        agent_mode="managed",
        persona_config=persona,
    )
    session.add(agent)
    session.commit()
    session.refresh(agent)

    # If game was active with AI agents, trigger new agent's decision
    if game.status == "active":
        try:
            auto_decide_managed(session, game.id, agent)
        except Exception as e:
            print(f"[join_current_game] agent {name} decision error: {e}")

    return {
        "token": agent.token,
        "faction": agent.faction,
        "game_id": game.id,
        "player_id": player.player_id,
    }


def current_game_state(session: Session) -> dict:
    """Public live state for the current game (homepage spectator view)."""
    game = get_or_create_current_game(session)

    cities = session.exec(select(City).where(City.game_id == game.id)).all()
    agents = session.exec(select(Agent).where(Agent.game_id == game.id)).all()

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
        })

    # Read resources for alliance info
    resources_raw = {}
    if game.resources:
        resources_raw = json.loads(game.resources)

    # Per-faction summary
    factions_summary = {}
    for f in FACTION_POOL:
        owned = [c for c in cities if c.owner == f]
        troops = sum(c.troops for c in owned)
        fres = resources_raw.get(f, {})
        factions_summary[f] = {
            "cities": len(owned),
            "troops": troops,
            "alliance_with": fres.get("alliance_with"),
        }

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
        "intentions": intentions,
        "agents": agent_info,
        "factions": factions_summary,
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
        game.status = "finished"
    else:
        max_cities = max(faction_cities.values())
        winners = [f for f, n in faction_cities.items() if n == max_cities]
        if len(winners) == 1:
            game.winner = winners[0]
            game.status = "finished"
        else:
            faction_troops: dict[str, int] = defaultdict(int)
            for c in cities:
                if c.owner:
                    faction_troops[c.owner] += c.troops
            winner = max(faction_troops, key=faction_troops.get)
            game.winner = winner
            game.status = "finished"

    # Mark as not current so next poll triggers a new game
    game.is_current = False
    session.add(game)
    session.commit()

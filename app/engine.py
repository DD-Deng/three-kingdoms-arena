import json
import random
from sqlmodel import Session, select
from .models import Game, Agent, City, Action, Player, RegisteredAgent

FACTION_POOL = ["蜀", "魏", "吴"]

# ═══════════════════════════════════════════════════════════════
# 地图数据：7 座城池 + 邻接关系
# ═══════════════════════════════════════════════════════════════

ALL_CITIES = ["洛阳", "长安", "邺城", "宛城", "襄阳", "成都", "建业"]

CITY_ADJACENCY: dict[str, list[str]] = {
    "洛阳": ["长安", "邺城", "宛城"],
    "长安": ["洛阳", "宛城"],
    "邺城": ["洛阳"],
    "宛城": ["洛阳", "长安", "襄阳"],
    "襄阳": ["宛城", "成都", "建业"],
    "成都": ["襄阳"],
    "建业": ["襄阳"],
}

# 初始归属
INITIAL_OWNERSHIP: dict[str, str | None] = {
    "洛阳": "魏",
    "长安": "魏",
    "邺城": "魏",
    "宛城": None,   # 中立
    "襄阳": None,   # 中立
    "成都": "蜀",
    "建业": "吴",
}

INITIAL_TROOPS_MIN = 800
INITIAL_TROOPS_MAX = 1200
NEUTRAL_TROOPS = 500
INITIAL_GRAIN = 500
GRAIN_PER_CITY = 100

DEFEND_BONUS = 300
ATTACKER_BONUS = 200


# ═══════════════════════════════════════════════════════════════
# Agent 注册
# ═══════════════════════════════════════════════════════════════

def register_agent(
    session: Session,
    player_id: str | None,
    agent_name: str,
    version: str = "v1",
) -> dict:
    """注册一个 agent 到全局注册表。"""
    # 如果没有 player_id，自动创建 Player
    if not player_id:
        player = Player()
        session.add(player)
        session.flush()
        player_id = player.player_id
    else:
        # 确保 player 存在
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
        owner = INITIAL_OWNERSHIP.get(name)
        if owner is None:
            troops = NEUTRAL_TROOPS
        else:
            troops = random.randint(INITIAL_TROOPS_MIN, INITIAL_TROOPS_MAX)
        session.add(City(game_id=game.id, name=name, owner=owner, troops=troops))

    # 初始化粮草
    resources = {f: {"grain": INITIAL_GRAIN} for f in FACTION_POOL}
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
    """通过已注册的 agent_id + secret 加入对局。"""
    game = session.get(Game, game_id)
    if game is None:
        raise ValueError("对局不存在")
    if game.status != "waiting" and game.tick > 0:
        raise ValueError("对局已开始")
    if faction not in FACTION_POOL:
        raise ValueError(f"势力必须是: {FACTION_POOL}")

    # 验证 agent 身份
    reg = session.get(RegisteredAgent, agent_id)
    if reg is None:
        raise ValueError("agent 未注册")
    if reg.secret != secret:
        raise ValueError("secret 不正确")

    # 检查该势力是否已被占用
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
# 视角内状态
# ═══════════════════════════════════════════════════════════════

def get_state(session: Session, game_id: int, agent: Agent):
    game = session.get(Game, game_id)
    if game is None:
        raise ValueError("对局不存在")
    cities = session.exec(select(City).where(City.game_id == game_id)).all()
    agents = session.exec(select(Agent).where(Agent.game_id == game_id)).all()

    your_faction = agent.faction

    your_cities = [
        {"name": c.name, "troops": c.troops}
        for c in cities
        if c.owner == your_faction
    ]

    all_cities = [
        {"name": c.name, "owner": c.owner, "troops": c.troops}
        for c in cities
    ]

    # 资源
    resources = {}
    if game.resources:
        resources = json.loads(game.resources)
    your_resources = resources.get(your_faction, {"grain": 0})

    # Valid actions
    valid_actions = _compute_valid_actions(cities, your_faction)

    # Parse last tick events
    last_events = []
    if game.last_tick_events:
        last_events = json.loads(game.last_tick_events)

    return {
        "game_id": game.id,
        "current_tick": game.tick,
        "status": game.status,
        "winner": game.winner,
        "your_faction": your_faction,
        "your_cities": your_cities,
        "all_cities": all_cities,
        "your_resources": your_resources,
        "agents": [
            {"agent_name": a.agent_name, "faction": a.faction} for a in agents
        ],
        "last_tick_events": last_events,
        "valid_actions": valid_actions,
    }


def _compute_valid_actions(cities, your_faction: str) -> list[dict]:
    """计算当前势力的合法动作列表。"""
    own_cities = [c for c in cities if c.owner == your_faction]
    actions = []

    # Attack: 自己的城 -> 邻接的敌对/中立城
    for own in own_cities:
        neighbors = CITY_ADJACENCY.get(own.name, [])
        for nb_name in neighbors:
            nb = next((c for c in cities if c.name == nb_name), None)
            if nb and nb.owner != your_faction:
                actions.append({
                    "type": "attack",
                    "from": own.name,
                    "target": nb_name,
                })

    # Defend: 自己的任何城
    for c in own_cities:
        actions.append({"type": "defend", "target": c.name})

    return actions


# ═══════════════════════════════════════════════════════════════
# 动作提交
# ═══════════════════════════════════════════════════════════════

def submit_action(
    session: Session, game_id: int, agent: Agent, action_type: str, target: str,
    from_city: str | None = None, troops: int | None = None,
    amount: int | None = None, message: str | None = None,
):
    game = session.get(Game, game_id)
    if game is None:
        raise ValueError("对局不存在")
    if game.status == "finished":
        raise ValueError("对局已结束")
    if game.status == "waiting":
        game.status = "active"
        session.add(game)
        session.commit()

    valid_cities = [c.name for c in session.exec(
        select(City).where(City.game_id == game_id)
    ).all()]
    if target not in valid_cities:
        raise ValueError(f"目标城池不存在: {target}")

    # 单 tick 单 agent 只能提交一个动作（Step 2 会改为多个）
    existing = session.exec(
        select(Action).where(
            Action.game_id == game_id,
            Action.agent_id == agent.id,
            Action.tick == game.tick,
        )
    ).first()
    if existing:
        raise ValueError("本回合已提交过动作")

    action = Action(
        game_id=game_id,
        agent_id=agent.id,
        tick=game.tick,
        type=action_type,
        target=target,
        from_city=from_city,
        troops=troops,
        amount=amount,
        message=message,
    )
    session.add(action)
    session.commit()
    return {"msg": "动作已提交", "tick": game.tick}


# ═══════════════════════════════════════════════════════════════
# Tick 推进
# ═══════════════════════════════════════════════════════════════

def tick(session: Session, game_id: int):
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

    changes: dict[str, tuple[str | None, int]] = {}
    events: list[dict] = []

    for city_name, city in city_map.items():
        city_actions = [a for a in actions if a.target == city_name]
        if not city_actions:
            continue

        action_desc_by_faction: dict[str, list[str]] = {}
        for action in city_actions:
            ag = agent_map.get(action.agent_id)
            if ag is None:
                continue
            action_desc_by_faction.setdefault(ag.faction, []).append(action.type)

        # Aggregate attack power by faction
        attack_by_faction: dict[str, float] = {}
        defend_bonus = 0

        for action in city_actions:
            ag = agent_map.get(action.agent_id)
            if ag is None:
                continue
            faction = ag.faction
            faction_troops = sum(
                c.troops for c in cities if c.owner == faction
            )
            if action.type == "attack":
                if faction not in attack_by_faction:
                    attack_by_faction[faction] = 0
                attack_by_faction[faction] += faction_troops
            elif action.type == "defend":
                defend_bonus += DEFEND_BONUS

        if not attack_by_faction:
            continue

        # Pick strongest attacker
        best_attacker = max(attack_by_faction, key=attack_by_faction.get)  # type: ignore[arg-type]
        attack_power = attack_by_faction[best_attacker] + ATTACKER_BONUS

        defender = city.owner
        defense_power = float(city.troops)
        if defender is not None:
            defense_power += defend_bonus

        if attack_power > defense_power:
            new_owner = best_attacker
            new_troops = max(int(attack_power - defense_power), 100)
        else:
            new_owner = defender
            new_troops = max(int(defense_power - attack_power), 100)

        changes[city_name] = (new_owner, new_troops)

        event = {
            "city": city_name,
            "attacker": best_attacker,
            "defender": defender,
            "attack_power": attack_power,
            "defense_power": defense_power,
            "result": "captured" if new_owner != defender else "defended",
            "new_owner": new_owner,
            "troops_remaining": new_troops,
            "actions": [
                {"faction": ag.faction, "type": a.type,
                 "agent_name": ag.agent_name}
                for a in city_actions
                if (ag := agent_map.get(a.agent_id))
            ],
        }
        events.append(event)

    # Apply city changes
    for city_name, (owner, troops) in changes.items():
        c = city_map[city_name]
        c.owner = owner
        c.troops = troops
        session.add(c)

    # ═══════════════════════════════════════════════════════════
    # 粮草生产：每控制一座城 +100 粮草
    # ═══════════════════════════════════════════════════════════
    resources = {}
    if game.resources:
        resources = json.loads(game.resources)

    updated_cities = session.exec(select(City).where(City.game_id == game_id)).all()
    for faction in FACTION_POOL:
        if faction not in resources:
            resources[faction] = {"grain": INITIAL_GRAIN}
        owned_count = sum(1 for c in updated_cities if c.owner == faction)
        resources[faction]["grain"] += owned_count * GRAIN_PER_CITY

    game.resources = json.dumps(resources, ensure_ascii=False)

    game.tick += 1
    game.last_tick_events = json.dumps(events, ensure_ascii=False)
    session.add(game)
    session.commit()

    # Check victory: one faction owns all owned cities (excludes unowned neutrals)
    cities = session.exec(select(City).where(City.game_id == game_id)).all()
    active_owners = {c.owner for c in cities if c.owner is not None}
    if len(active_owners) == 1:
        game.status = "finished"
        game.winner = active_owners.pop()
        session.add(game)
        session.commit()

    return {
        "tick": game.tick,
        "status": game.status,
        "winner": game.winner,
        "cities": [
            {"name": c.name, "owner": c.owner, "troops": c.troops} for c in cities
        ],
        "events": events,
    }

import json
import math
import random
from collections import defaultdict
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
    "宛城": None,
    "襄阳": None,
    "成都": "蜀",
    "建业": "吴",
}

INITIAL_TROOPS_MIN = 800
INITIAL_TROOPS_MAX = 1200
NEUTRAL_TROOPS = 500
INITIAL_GRAIN = 500
GRAIN_PER_CITY = 100

# 战斗参数
DEFEND_BONUS_MULTIPLIER = 0.5    # defend 动作：守城兵力 × 1.5
ATTACKER_WIN_LOSS = 0.30         # 胜方损失 30%
ATTACKER_LOSE_LOSS = 1.00        # 败方全军覆没
DEFENDER_WIN_LOSS = 0.50         # 守方胜时损失 50%
DEFENDER_LOSE_LOSS = 0.30        # 守方败时损失 30%（多方进攻中其他进攻方也用这个）
GARRISON_MIN = 100               # 出兵城留守底线
MAX_RECRUIT_PER_CITY = 200       # 每城每回合最多招募


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
        owner = INITIAL_OWNERSHIP.get(name)
        if owner is None:
            troops = NEUTRAL_TROOPS
        else:
            troops = random.randint(INITIAL_TROOPS_MIN, INITIAL_TROOPS_MAX)
        session.add(City(game_id=game.id, name=name, owner=owner, troops=troops))

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

    resources = {}
    if game.resources:
        resources = json.loads(game.resources)
    your_resources = resources.get(your_faction, {"grain": 0})

    valid_actions = _compute_valid_actions(cities, your_faction, your_resources)

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


def _compute_valid_actions(cities, your_faction: str, resources: dict) -> list[dict]:
    """计算当前势力所有合法动作（不考虑粮草上限，只列出可能选项）。"""
    own_cities = [c for c in cities if c.owner == your_faction]
    grain = resources.get("grain", 0)
    actions = []

    # Attack: 自己的城 -> 邻接的非己方城
    for own in own_cities:
        if own.troops <= GARRISON_MIN:
            continue
        neighbors = CITY_ADJACENCY.get(own.name, [])
        for nb_name in neighbors:
            nb = next((c for c in cities if c.name == nb_name), None)
            if nb and nb.owner != your_faction:
                max_troops = own.troops - GARRISON_MIN
                affordable = grain  # 每兵 1 粮草
                if affordable > 0:
                    actions.append({
                        "type": "attack",
                        "from": own.name,
                        "target": nb_name,
                        "max_troops": min(max_troops, affordable),
                    })

    # Defend: 自己的任何城
    for c in own_cities:
        actions.append({"type": "defend", "target": c.name})

    # Recruit: 自己的城
    max_recruit = min(MAX_RECRUIT_PER_CITY, grain // 2)
    if max_recruit > 0:
        for c in own_cities:
            actions.append({
                "type": "recruit",
                "target": c.name,
                "max_amount": max_recruit,
            })

    # March: 自己邻接的己方城之间
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

    # Diplomacy: 向其他势力喊话
    for f in FACTION_POOL:
        if f != your_faction:
            actions.append({
                "type": "diplomacy",
                "target": f,
            })

    return actions


# ═══════════════════════════════════════════════════════════════
# 动作提交（支持多动作）
# ═══════════════════════════════════════════════════════════════

def submit_actions(
    session: Session, game_id: int, agent: Agent, actions: list[dict],
):
    """提交一组合法动作。扣除对应粮草，写入 Action 表。"""
    game = session.get(Game, game_id)
    if game is None:
        raise ValueError("对局不存在")
    if game.status == "finished":
        raise ValueError("对局已结束")

    if game.status == "waiting":
        game.status = "active"
        session.add(game)
        session.commit()

    # 检查本回合是否已提交过
    existing = session.exec(
        select(Action).where(
            Action.game_id == game_id,
            Action.agent_id == agent.id,
            Action.tick == game.tick,
        )
    ).first()
    if existing:
        raise ValueError("本回合已提交过动作")

    # 加载城池和资源
    cities = session.exec(select(City).where(City.game_id == game_id)).all()
    city_map = {c.name: c for c in cities}
    resources = json.loads(game.resources) if game.resources else {}
    faction_res = resources.get(agent.faction, {"grain": INITIAL_GRAIN})
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
            # 校验 from 城
            from_city = city_map.get(from_name)
            if not from_city or from_city.owner != agent.faction:
                raise ValueError(f"出兵城 [{from_name}] 不归你控制")
            if troops > from_city.troops - GARRISON_MIN:
                raise ValueError(
                    f"出兵城 [{from_name}] 兵力不足（有 {from_city.troops}，"
                    f"需留守 {GARRISON_MIN}，最多出兵 {from_city.troops - GARRISON_MIN}）"
                )
            # 校验邻接
            if target not in CITY_ADJACENCY.get(from_name, []):
                raise ValueError(f"[{from_name}] 和 [{target}] 不邻接，无法攻击")
            # 校验 target 不是自己的城
            target_city = city_map.get(target)
            if target_city and target_city.owner == agent.faction:
                raise ValueError(f"不能攻击自己的城 [{target}]")
            total_grain_cost += troops * 1

        elif action_type == "defend":
            target = act["target"]
            target_city = city_map.get(target)
            if not target_city or target_city.owner != agent.faction:
                raise ValueError(f"防守目标 [{target}] 不归你控制")
            # defend 不消耗粮草

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
            total_grain_cost += amount * 2

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
            # march 不消耗粮草

        elif action_type == "diplomacy":
            target = act["target"]
            message = act.get("message", "")
            if target not in FACTION_POOL:
                raise ValueError(f"外交目标必须是有效势力: {FACTION_POOL}")
            if target == agent.faction:
                raise ValueError("不能对自己外交")
            if len(message) > 200:
                raise ValueError(f"外交发言不能超过 200 字，当前 {len(message)} 字")
            # diplomacy 不消耗粮草

        else:
            raise ValueError(f"未知动作类型: {action_type}")

        validated.append(act)

    # ── 检查粮草 ──────────────────────────────────────────
    if total_grain_cost > grain:
        raise ValueError(
            f"粮草不足（需要 {total_grain_cost}，当前 {grain}）"
        )

    # ── 扣除粮草 ──────────────────────────────────────────
    faction_res["grain"] = grain - total_grain_cost
    resources[agent.faction] = faction_res
    game.resources = json.dumps(resources, ensure_ascii=False)
    session.add(game)

    # ── 写入 Action 表 ────────────────────────────────────
    for act in validated:
        # march 用 "to" 作为 target；其他类型用 "target"
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
        )
        session.add(action)

    session.commit()
    return {
        "msg": f"{len(validated)} 个动作已提交",
        "tick": game.tick,
        "grain_cost": total_grain_cost,
        "grain_remaining": faction_res["grain"],
    }


# ═══════════════════════════════════════════════════════════════
# Tick 推进 —— 战斗结算
# ═══════════════════════════════════════════════════════════════

def tick(session: Session, game_id: int):
    """执行一个回合。

    流程：
    1. 加载所有待处理的 attack/defend 动作
    2. 按城池分组结算战斗（基于 tick 开始时的城池状态）
    3. 执行 recruit（新兵入城）
    4. 执行 march（调兵，在战斗后所以不参战）
    5. 产出粮草
    6. 记录事件
    7. 检查胜利条件
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

    # 战斗前城池状态快照
    city_before: dict[str, tuple[str | None, int]] = {
        c.name: (c.owner, c.troops) for c in cities
    }

    # ── 1. 收集外交消息 ──────────────────────────────────────
    diplomacy_messages: list[dict] = []
    for a in actions:
        if a.type == "diplomacy":
            ag = agent_map.get(a.agent_id)
            if ag:
                diplomacy_messages.append({
                    "from_faction": ag.faction,
                    "to_faction": a.target,
                    "message": a.message or "",
                })

    # ── 2. 按城池分组，结算战斗 ────────────────────────────
    # 只处理 attack / defend 动作
    combat_actions = [a for a in actions if a.type in ("attack", "defend")]
    cities_with_combat = set(a.target for a in combat_actions)

    combat_changes: dict[str, tuple[str | None, int]] = {}
    combat_events: list[dict] = []

    for city_name in cities_with_combat:
        city = city_map[city_name]
        city_act = [a for a in combat_actions if a.target == city_name]

        # 分离 attack 和 defend
        attacks: list[tuple[Action, str, int]] = []  # (action, faction, troops_committed)
        defended = False

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

        if not attacks:
            continue

        # 计算防守方力量
        defense_multiplier = 1.0
        if city.owner is not None and defended:
            defense_multiplier += DEFEND_BONUS_MULTIPLIER  # 1.0 + 0.5 = 1.5
        # 中立城无防守加成
        if city.owner is None:
            defense_multiplier = 1.0

        defense_power = city.troops * defense_multiplier

        # 按势力聚合进攻兵力
        faction_attack: dict[str, int] = defaultdict(int)
        for _, faction, troops in attacks:
            faction_attack[faction] += troops

        total_attack = sum(faction_attack.values())

        # 按攻击力从高到低排序
        sorted_attackers = sorted(faction_attack.items(), key=lambda x: x[1], reverse=True)
        best_attacker_faction, best_attack_power = sorted_attackers[0]

        event = {
            "city": city_name,
            "defender": city.owner,
            "defense_power": round(defense_power, 1),
            "defended": defended,
            "attackers": [
                {"faction": f, "troops_committed": t}
                for f, t in sorted_attackers
            ],
            "result": "",
            "new_owner": None,
            "troops_remaining": 0,
        }

        if total_attack > defense_power:
            # ── 进攻方胜 ──────────────────────────────────
            # 最强攻击者获得城池
            winner_faction = best_attacker_faction

            # 各方兵力损失
            troop_losses: dict[str, int] = {}
            for faction, committed in faction_attack.items():
                if faction == winner_faction:
                    # 获胜方损失 30%
                    loss = math.ceil(committed * ATTACKER_WIN_LOSS)
                    remaining = committed - loss
                else:
                    # 其他进攻方损失 50%
                    loss = math.ceil(committed * DEFENDER_LOSE_LOSS)
                    remaining = committed - loss
                troop_losses[faction] = remaining

            # 守方兵力清零
            new_troops = max(troop_losses[winner_faction], 100)

            combat_changes[city_name] = (winner_faction, new_troops)

            event["result"] = "captured"
            event["new_owner"] = winner_faction
            event["troops_remaining"] = new_troops
            event["winner"] = winner_faction
            event["troop_losses"] = troop_losses

        else:
            # ── 防守方胜 ──────────────────────────────────
            # 所有进攻方损失 100%
            # 守方损失 30%
            new_troops = max(math.floor(city.troops * (1 - DEFENDER_LOSE_LOSS)), 100)

            combat_changes[city_name] = (city.owner, new_troops)

            event["result"] = "defended"
            event["new_owner"] = city.owner
            event["troops_remaining"] = new_troops
            event["attacker_loss"] = "100%"

        # 记录各方参与的动作类型
        event["actions"] = [
            {"faction": ag.faction, "type": a.type, "agent_name": ag.agent_name}
            for a in city_act
            if (ag := agent_map.get(a.agent_id))
        ]

        combat_events.append(event)

    # ── 应用战斗结果 ──────────────────────────────────────
    for city_name, (owner, troops) in combat_changes.items():
        c = city_map[city_name]
        c.owner = owner
        c.troops = troops
        session.add(c)

    # ── 3. 执行招募（战斗后，新兵入城） ──────────────────
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
            combat_events.append({
                "city": a.target,
                "event_type": "recruit",
                "faction": ag.faction,
                "amount": amount,
                "new_troops": target_city.troops,
            })

    # ── 4. 执行行军（战斗后，调兵不参战） ────────────────
    march_actions = [a for a in actions if a.type == "march"]
    for a in march_actions:
        ag = agent_map.get(a.agent_id)
        if ag is None:
            continue
        from_city = city_map.get(a.from_city)
        to_city = city_map.get(a.target)
        troops_to_move = a.troops or 0
        if from_city and to_city and from_city.owner == ag.faction and to_city.owner == ag.faction:
            # 检查出发城仍有足够兵力（可能已被战斗消耗）
            actual_move = min(troops_to_move, from_city.troops - GARRISON_MIN)
            if actual_move > 0:
                from_city.troops -= actual_move
                to_city.troops += actual_move
                session.add(from_city)
                session.add(to_city)
                combat_events.append({
                    "event_type": "march",
                    "from": a.from_city,
                    "to": a.target,
                    "faction": ag.faction,
                    "troops": actual_move,
                })

    # ── 5. 粮草收入 ──────────────────────────────────────
    resources = json.loads(game.resources) if game.resources else {}
    updated_cities = session.exec(select(City).where(City.game_id == game_id)).all()
    for faction in FACTION_POOL:
        if faction not in resources:
            resources[faction] = {"grain": INITIAL_GRAIN}
        owned_count = sum(1 for c in updated_cities if c.owner == faction)
        resources[faction]["grain"] += owned_count * GRAIN_PER_CITY

    game.resources = json.dumps(resources, ensure_ascii=False)

    # ── 6. 记录公开事件 ──────────────────────────────────
    public_events = []
    # 战斗结果
    for ev in combat_events:
        if ev.get("result") in ("captured", "defended"):
            public_events.append({
                "type": "battle",
                "city": ev["city"],
                "result": ev["result"],
                "new_owner": ev.get("new_owner"),
                "troops_remaining": ev.get("troops_remaining"),
            })
        elif ev.get("event_type") == "recruit":
            public_events.append({
                "type": "recruit",
                "city": ev["city"],
                "faction": ev["faction"],
            })
        elif ev.get("event_type") == "march":
            public_events.append({
                "type": "march",
                "from": ev["from"],
                "to": ev["to"],
                "faction": ev["faction"],
            })

    game.tick += 1
    game.last_tick_events = json.dumps(public_events, ensure_ascii=False)
    session.add(game)
    session.commit()

    # ── 7. 检查胜利条件 ──────────────────────────────────
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
        "events": public_events,
        "diplomacy": diplomacy_messages,
    }

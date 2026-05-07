import json
import math
import random
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
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
DEFEND_BONUS_MULTIPLIER = 0.5
ATTACKER_WIN_LOSS = 0.30
ATTACKER_LOSE_LOSS = 1.00
DEFENDER_WIN_LOSS = 0.50
DEFENDER_LOSE_LOSS = 0.30
GARRISON_MIN = 100
MAX_RECRUIT_PER_CITY = 200

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

    known_cities = []
    for c in cities:
        if c.name in own_names:
            continue
        owner_display = c.owner if c.owner else "中立"
        if c.name in adjacent_to_own:
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

    max_recruit = min(MAX_RECRUIT_PER_CITY, grain // 2)
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

        elif action_type == "diplomacy":
            target = act["target"]
            message = act.get("message", "")
            if target not in FACTION_POOL:
                raise ValueError(f"外交目标必须是有效势力: {FACTION_POOL}")
            if target == agent.faction:
                raise ValueError("不能对自己外交")
            if len(message) > 200:
                raise ValueError(f"外交发言不能超过 200 字，当前 {len(message)} 字")

        else:
            raise ValueError(f"未知动作类型: {action_type}")

        validated.append(act)

    if total_grain_cost > grain:
        raise ValueError(
            f"粮草不足（需要 {total_grain_cost}，当前 {grain}）"
        )

    # ── 扣除粮草 ──────────────────────────────────────────
    faction_res["grain"] = grain - total_grain_cost
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
    return {
        "msg": f"{len(validated)} 个动作已提交",
        "tick": game.tick,
        "grain_cost": total_grain_cost,
        "grain_remaining": faction_res["grain"],
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

    # ── 1. 收集外交消息 ──────────────────────────────────────
    diplomacy_messages: list[dict] = []
    for a in actions:
        if a.type == "diplomacy":
            ag = agent_map.get(a.agent_id)
            if ag and a.message:
                # Check if we already recorded this agent's speech this tick
                already = any(
                    d["from_faction"] == ag.faction
                    for d in diplomacy_messages
                )
                if not already:
                    diplomacy_messages.append({
                        "from_faction": ag.faction,
                        "message": a.message,
                    })

    # ── 2. 按城池分组，结算战斗 ────────────────────────────
    combat_actions = [a for a in actions if a.type in ("attack", "defend")]
    cities_with_combat = set(a.target for a in combat_actions)

    combat_changes: dict[str, tuple[str | None, int]] = {}
    combat_events: list[dict] = []
    # 记录详细的战斗数据用于 private_log
    private_combat_detail: list[dict] = []

    for city_name in cities_with_combat:
        city = city_map[city_name]
        city_act = [a for a in combat_actions if a.target == city_name]

        attacks: list[tuple[Action, str, int]] = []
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

        defense_multiplier = 1.0
        if city.owner is not None and defended:
            defense_multiplier += DEFEND_BONUS_MULTIPLIER
        if city.owner is None:
            defense_multiplier = 1.0

        defense_power = city.troops * defense_multiplier

        faction_attack: dict[str, int] = defaultdict(int)
        for _, faction, troops in attacks:
            faction_attack[faction] += troops

        total_attack = sum(faction_attack.values())
        sorted_attackers = sorted(faction_attack.items(), key=lambda x: x[1], reverse=True)
        best_attacker_faction, best_attack_power = sorted_attackers[0]

        # 公开事件摘要
        public_event = {"city": city_name}

        # 详细战斗数据（仅用于 private_log）
        detail = {
            "city": city_name,
            "defender": city.owner,
            "defense_power": round(defense_power, 1),
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

        if total_attack > defense_power:
            winner_faction = best_attacker_faction
            troop_losses: dict[str, int] = {}
            for faction, committed in faction_attack.items():
                if faction == winner_faction:
                    loss = math.ceil(committed * ATTACKER_WIN_LOSS)
                    remaining = committed - loss
                else:
                    loss = math.ceil(committed * DEFENDER_LOSE_LOSS)
                    remaining = committed - loss
                troop_losses[faction] = remaining

            new_troops = max(troop_losses[winner_faction], 100)
            combat_changes[city_name] = (winner_faction, new_troops)

            public_event["result"] = "captured"
            public_event["captured_by"] = winner_faction
            public_event["from"] = city.owner or "中立"

            detail["result"] = "captured"
            detail["new_owner"] = winner_faction
            detail["troops_remaining"] = new_troops
            detail["troop_losses"] = troop_losses
        else:
            new_troops = max(math.floor(city.troops * (1 - DEFENDER_LOSE_LOSS)), 100)
            combat_changes[city_name] = (city.owner, new_troops)

            defender_name = city.owner or "中立"
            public_event["result"] = "defended"
            public_event["defended_by"] = defender_name

            detail["result"] = "defended"
            detail["new_owner"] = city.owner
            detail["troops_remaining"] = new_troops
            detail["attacker_loss"] = "100%"

        combat_events.append(public_event)
        private_combat_detail.append(detail)

    # ── 应用战斗结果 ──────────────────────────────────────
    for city_name, (owner, troops) in combat_changes.items():
        c = city_map[city_name]
        c.owner = owner
        c.troops = troops
        session.add(c)

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

    # ── 5. 粮草收入 ──────────────────────────────────────
    resources = json.loads(game.resources) if game.resources else {}
    updated_cities = session.exec(select(City).where(City.game_id == game_id)).all()
    for faction in FACTION_POOL:
        if faction not in resources:
            resources[faction] = {"grain": INITIAL_GRAIN}
        owned_count = sum(1 for c in updated_cities if c.owner == faction)
        resources[faction]["grain"] += owned_count * GRAIN_PER_CITY

    game.resources = json.dumps(resources, ensure_ascii=False)

    # ── 6. 保存公开/私有事件 ──────────────────────────────
    game.last_tick_events = json.dumps(combat_events, ensure_ascii=False)
    game.last_tick_diplomacy = json.dumps(diplomacy_messages, ensure_ascii=False)

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
    """写入双轨日志文件。"""
    PUBLIC_LOG_DIR.mkdir(parents=True, exist_ok=True)
    PRIVATE_LOG_DIR.mkdir(parents=True, exist_ok=True)

    ts = datetime.now(timezone.utc).isoformat()

    # ── public_log: 只含战斗结果、城池易主、外交 ─────────
    pub_entry = {
        "timestamp": ts,
        "game_id": game_id,
        "tick": tick,
        "events": public_events,
        "diplomacy": diplomacy,
        "cities": [
            {"name": c.name, "owner": c.owner or "中立"}
            for c in city_map.values()
        ],
    }
    pub_path = PUBLIC_LOG_DIR / f"{game_id}.jsonl"
    with open(pub_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(pub_entry, ensure_ascii=False) + "\n")

    # ── private_log: 含所有 agent 提交的 actions、详细内部状态 ──
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

    priv_entry = {
        "timestamp": ts,
        "game_id": game_id,
        "tick": tick,
        "combat_detail": private_detail,
        "agent_actions": priv_actions,
        "cities_before_tick": [
            {"name": c.name, "owner": c.owner or "中立", "troops": c.troops}
            for c in city_map.values()
        ],
    }
    priv_path = PRIVATE_LOG_DIR / f"{game_id}.jsonl"
    with open(priv_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(priv_entry, ensure_ascii=False) + "\n")

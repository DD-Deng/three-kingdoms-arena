from sqlmodel import Session, select
from .models import Game, Agent, City, Action

FACTION_POOL = ["蜀", "魏", "吴"]
INITIAL_CITIES = ["洛阳", "成都", "建业"]
INITIAL_TROOPS = 1000
DEFEND_BONUS = 300
ATTACKER_BONUS = 200


def create_game(session: Session) -> int:
    game = Game()
    session.add(game)
    session.flush()

    for name in INITIAL_CITIES:
        session.add(City(game_id=game.id, name=name))

    session.commit()
    return game.id  # type: ignore[return-value]


def join_game(session: Session, game_id: int, agent_name: str, faction: str) -> str:
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

    agent = Agent(game_id=game_id, agent_name=agent_name, faction=faction)
    session.add(agent)
    session.commit()
    session.refresh(agent)

    _init_faction_city(session, game_id, faction)

    return agent.token  # type: ignore[return-value]


def _init_faction_city(session: Session, game_id: int, faction: str):
    city_map = {"蜀": "成都", "魏": "洛阳", "吴": "建业"}
    city_name = city_map.get(faction)
    if not city_name:
        return
    city = session.exec(
        select(City).where(City.game_id == game_id, City.name == city_name)
    ).first()
    if city and city.owner is None:
        city.owner = faction
        city.troops = INITIAL_TROOPS
        session.add(city)
        session.commit()


def get_state(session: Session, game_id: int):
    game = session.get(Game, game_id)
    if game is None:
        raise ValueError("对局不存在")
    cities = session.exec(select(City).where(City.game_id == game_id)).all()
    agents = session.exec(select(Agent).where(Agent.game_id == game_id)).all()

    return {
        "game_id": game.id,
        "tick": game.tick,
        "status": game.status,
        "winner": game.winner,
        "cities": [
            {"name": c.name, "owner": c.owner, "troops": c.troops} for c in cities
        ],
        "agents": [
            {"agent_name": a.agent_name, "faction": a.faction} for a in agents
        ],
    }


def submit_action(
    session: Session, game_id: int, agent: Agent, action_type: str, target: str
):
    game = session.get(Game, game_id)
    if game is None:
        raise ValueError("对局不存在")
    if game.status == "finished":
        raise ValueError("对局已结束")
    if game.status == "waiting":
        # 允许第一个 tick 前的动作提交
        game.status = "active"
        session.add(game)
        session.commit()

    valid_cities = [c.name for c in session.exec(
        select(City).where(City.game_id == game_id)
    ).all()]
    if target not in valid_cities:
        raise ValueError(f"目标城池不存在: {target}")

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
    )
    session.add(action)
    session.commit()
    return {"msg": "动作已提交", "tick": game.tick}


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

    for city_name, city in city_map.items():
        city_actions = [a for a in actions if a.target == city_name]
        if not city_actions:
            continue

        # 按 faction 聚合攻击力，防御加成
        attack_by_faction: dict[str, float] = {}
        faction_attack_count: dict[str, int] = {}
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
                    faction_attack_count[faction] = 0
                attack_by_faction[faction] += faction_troops
                faction_attack_count[faction] += 1
            elif action.type == "defend":
                defend_bonus += DEFEND_BONUS

        if not attack_by_faction:
            continue

        # 选最强进攻方，加攻击方优势打破对称僵局
        best_attacker = max(attack_by_faction, key=attack_by_faction.get)  # type: ignore[arg-type]
        attack_power = attack_by_faction[best_attacker] + ATTACKER_BONUS

        # 防御方战力 = 城池兵力 + 防御加成
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

    # 应用变更
    for city_name, (owner, troops) in changes.items():
        c = city_map[city_name]
        c.owner = owner
        c.troops = troops
        session.add(c)

    game.tick += 1
    session.add(game)
    session.commit()

    # 检查胜利条件
    cities = session.exec(select(City).where(City.game_id == game_id)).all()
    active_owners = {c.owner for c in cities if c.owner is not None}
    if len(active_owners) == 1:
        game.status = "finished"
        game.winner = active_owners.pop()
        session.add(game)
        session.commit()

    return {"tick": game.tick, "status": game.status, "winner": game.winner}

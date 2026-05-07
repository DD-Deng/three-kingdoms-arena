from fastapi.testclient import TestClient
from app.main import app
from app.database import init_db
from sqlmodel import SQLModel
from app.database import engine

client = TestClient(app)


def setup():
    SQLModel.metadata.drop_all(engine)
    init_db()


# ═══════════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════════

def _register_and_join(faction: str, name: str, game_id: int) -> str:
    r = client.post("/agents/register", json={"agent_name": name})
    reg = r.json()
    r = client.post(f"/games/{game_id}/join", json={
        "agent_id": reg["agent_id"],
        "secret": reg["secret"],
        "faction": faction,
    })
    return r.json()["token"]


def _submit(token: str, game_id: int, actions: list[dict]):
    return client.post(
        f"/games/{game_id}/actions",
        params={"token": token},
        json={"actions": actions},
    )


def _tick(game_id: int):
    return client.post(f"/games/{game_id}/tick")


# ═══════════════════════════════════════════════════════════════
# Step 1 测试
# ═══════════════════════════════════════════════════════════════

def test_agent_register():
    setup()
    r = client.post("/agents/register", json={
        "agent_name": "刘备",
        "version": "v1",
    })
    assert r.status_code == 200
    data = r.json()
    assert "agent_id" in data
    assert len(data["agent_id"]) == 32
    assert "secret" in data
    assert len(data["secret"]) == 64
    assert "player_id" in data

    r2 = client.post("/agents/register", json={
        "player_id": data["player_id"],
        "agent_name": "曹操",
    })
    assert r2.status_code == 200
    assert r2.json()["player_id"] == data["player_id"]


def test_join_requires_agent_credentials():
    setup()
    r = client.post("/agents/register", json={"agent_name": "刘备"})
    reg = r.json()
    r = client.post("/games")
    gid = r.json()["game_id"]

    r = client.post(f"/games/{gid}/join", json={
        "agent_id": reg["agent_id"],
        "secret": reg["secret"],
        "faction": "蜀",
    })
    assert r.status_code == 200
    assert "token" in r.json()

    r = client.post(f"/games/{gid}/join", json={
        "agent_id": reg["agent_id"],
        "secret": "wrong-secret",
        "faction": "魏",
    })
    assert r.status_code == 400
    assert "secret" in r.json()["detail"]

    r = client.post(f"/games/{gid}/join", json={
        "agent_id": "nonexistent",
        "secret": "whatever",
        "faction": "魏",
    })
    assert r.status_code == 400


def test_seven_cities_and_adjacency():
    setup()
    r = client.post("/games")
    gid = r.json()["game_id"]
    token = _register_and_join("蜀", "刘备", gid)

    r = client.get(f"/games/{gid}/state", params={"token": token})
    state = r.json()

    assert len(state["all_cities"]) == 7
    city_names = {c["name"] for c in state["all_cities"]}
    assert city_names == {"洛阳", "长安", "邺城", "宛城", "襄阳", "成都", "建业"}

    city_owners = {c["name"]: c["owner"] for c in state["all_cities"]}
    assert city_owners["洛阳"] == "魏"
    assert city_owners["长安"] == "魏"
    assert city_owners["邺城"] == "魏"
    assert city_owners["成都"] == "蜀"
    assert city_owners["建业"] == "吴"
    assert city_owners["宛城"] is None
    assert city_owners["襄阳"] is None

    for c in state["all_cities"]:
        if c["name"] in ("宛城", "襄阳"):
            assert c["troops"] == 500

    valid_actions = state["valid_actions"]
    attack_targets = [a["target"] for a in valid_actions if a["type"] == "attack"]
    assert "襄阳" in attack_targets
    assert "洛阳" not in attack_targets


def test_grain_increases_per_tick():
    setup()
    r = client.post("/games")
    gid = r.json()["game_id"]
    token_shu = _register_and_join("蜀", "刘备", gid)
    _register_and_join("魏", "曹操", gid)

    r = client.get(f"/games/{gid}/state", params={"token": token_shu})
    assert r.json()["your_resources"]["grain"] == 500

    for _ in range(3):
        client.post(f"/games/{gid}/tick")

    r = client.get(f"/games/{gid}/state", params={"token": token_shu})
    assert r.json()["your_resources"]["grain"] == 800


def test_create_join_action_tick():
    setup()
    r = client.post("/games")
    gid = r.json()["game_id"]
    token_shu = _register_and_join("蜀", "刘备", gid)
    _register_and_join("魏", "曹操", gid)

    r = client.get(f"/games/{gid}/state", params={"token": token_shu})
    assert r.status_code == 200
    state = r.json()
    assert state["current_tick"] == 0
    assert state["status"] == "waiting"

    # 先空过 3 回合攒粮草（500 + 3×100 = 800）
    for _ in range(3):
        _tick(gid)

    # 蜀攻击襄阳（中立城，邻接成都），出兵 550 需 550 粮草
    r = _submit(token_shu, gid, [
        {"type": "attack", "from": "成都", "target": "襄阳", "troops": 550},
    ])
    assert r.status_code == 200

    r = _tick(gid)
    assert r.status_code == 200

    r = client.get(f"/games/{gid}/state", params={"token": token_shu})
    state = r.json()
    xiangyang = [c for c in state["all_cities"] if c["name"] == "襄阳"][0]
    assert xiangyang["owner"] == "蜀"


def test_bad_token():
    setup()
    r = client.post("/games")
    gid = r.json()["game_id"]
    _register_and_join("蜀", "刘备", gid)
    r = client.get(f"/games/{gid}/state", params={"token": "wrong-token"})
    assert r.status_code == 401


def test_duplicate_faction():
    setup()
    r = client.post("/games")
    gid = r.json()["game_id"]
    _register_and_join("蜀", "刘备", gid)
    r2 = client.post("/agents/register", json={"agent_name": "刘禅"})
    reg2 = r2.json()
    r = client.post(f"/games/{gid}/join", json={
        "agent_id": reg2["agent_id"],
        "secret": reg2["secret"],
        "faction": "蜀",
    })
    assert r.status_code == 400
    assert "已被占用" in r.json()["detail"]


# ═══════════════════════════════════════════════════════════════
# Step 2 测试 —— 战斗结算
# ═══════════════════════════════════════════════════════════════

# ── 测试 S2-1: 单方攻击成功 ──────────────────────────────

def test_single_attack_success():
    """蜀攻击中立襄阳，兵力碾压，应获胜。"""
    setup()
    r = client.post("/games")
    gid = r.json()["game_id"]
    token_shu = _register_and_join("蜀", "刘备", gid)

    # 先攒 3 回合粮草（500 + 300 = 800），足够出 550 兵（需 550 粮草）
    for _ in range(3):
        _tick(gid)

    # 蜀从成都出兵 550 打中立襄阳（兵力 500），550 > 500 进攻方胜
    r = _submit(token_shu, gid, [
        {"type": "attack", "from": "成都", "target": "襄阳", "troops": 550},
    ])
    assert r.status_code == 200

    r = _tick(gid)
    assert r.status_code == 200

    r = client.get(f"/games/{gid}/state", params={"token": token_shu})
    state = r.json()
    xiangyang = [c for c in state["all_cities"] if c["name"] == "襄阳"][0]
    assert xiangyang["owner"] == "蜀"
    # 损失 30%，剩余 ≈ 385（550 * 0.7）
    assert xiangyang["troops"] >= 100

    events = state["last_tick_events"]
    battle = [e for e in events if e["type"] == "battle"][0]
    assert battle["result"] == "captured"
    assert battle["new_owner"] == "蜀"


# ── 测试 S2-2: 单方攻击失败 ──────────────────────────────

def test_single_attack_failure():
    """蜀兵太少打不动魏的洛阳，应失败。"""
    setup()
    r = client.post("/games")
    gid = r.json()["game_id"]
    token_shu = _register_and_join("蜀", "刘备", gid)

    # 攒粮草 3 回合
    for _ in range(3):
        _tick(gid)

    # 先拿下襄阳（中立 500 兵，出 550 兵花费 550 粮草，剩余 250）
    r = _submit(token_shu, gid, [
        {"type": "attack", "from": "成都", "target": "襄阳", "troops": 550},
    ])
    _tick(gid)

    # 再攒粮草攒够打宛城的（襄阳现属蜀，每 tick +200 粮草）
    for _ in range(2):
        _tick(gid)

    # 从襄阳打宛城（中立 500 兵），出 300 兵花费 300 粮草
    r = _submit(token_shu, gid, [
        {"type": "attack", "from": "襄阳", "target": "宛城", "troops": 300},
    ])
    _tick(gid)
    # 300 < 500，应该打不下来（宛城仍中立），但这是为了打通路
    # 我们换个策略：用很小的兵打洛阳，验证攻击失败

    # 从宛城方向打洛阳——但宛城还不是蜀的。换个思路：
    # 直接从襄阳用 50 兵打宛城（会失败），验证兵力不足时攻击失败

    # 重新攒粮草，再用很少的兵打一个必定失败的目标
    for _ in range(2):
        _tick(gid)

    # 用 20 兵打宛城（中立 500），必定失败
    r = _submit(token_shu, gid, [
        {"type": "attack", "from": "襄阳", "target": "宛城", "troops": 20},
    ])
    assert r.status_code == 200

    r = _tick(gid)
    assert r.status_code == 200

    # 宛城应仍属中立（20 vs 500，进攻失败，全军覆没）
    r = client.get(f"/games/{gid}/state", params={"token": token_shu})
    state = r.json()
    wancheng = [c for c in state["all_cities"] if c["name"] == "宛城"][0]
    assert wancheng["owner"] is None  # 仍中立

    events = state["last_tick_events"]
    battle = [e for e in events if e["type"] == "battle"][0]
    assert battle["result"] == "defended"


# ── 测试 S2-3: 多方攻击，最强者胜 ───────────────────────

def test_multi_attack_strongest_wins():
    """魏蜀同时打中立宛城，兵力多者得城。"""
    setup()
    r = client.post("/games")
    gid = r.json()["game_id"]
    token_shu = _register_and_join("蜀", "刘备", gid)
    token_wei = _register_and_join("魏", "曹操", gid)

    # 攒粮草 4 回合（魏 3 城 × 100 = 300/tick，4 ticks = +1200 = 1700 总）
    # 蜀 1 城 × 100 = 100/tick，4 ticks = +400 = 900 总
    for _ in range(4):
        _tick(gid)

    # 蜀先拿下襄阳，打通到宛城（550 兵 cost 550）
    r = _submit(token_shu, gid, [
        {"type": "attack", "from": "成都", "target": "襄阳", "troops": 550},
    ])
    _tick(gid)

    # 攒粮草 1 回合
    _tick(gid)

    # 魏从洛阳打宛城 400（花费 400 粮草），蜀从襄阳打宛城 150（花费 150 粮草）
    r = _submit(token_wei, gid, [
        {"type": "attack", "from": "洛阳", "target": "宛城", "troops": 400},
    ])
    assert r.status_code == 200

    r = _submit(token_shu, gid, [
        {"type": "attack", "from": "襄阳", "target": "宛城", "troops": 150},
    ])
    assert r.status_code == 200

    r = _tick(gid)
    assert r.status_code == 200

    # 宛城兵力 500，总进攻 400+150=550 > 500，进攻方胜
    # 魏 400 > 蜀 150，魏应得城
    r = client.get(f"/games/{gid}/state", params={"token": token_shu})
    state = r.json()
    wancheng = [c for c in state["all_cities"] if c["name"] == "宛城"][0]
    assert wancheng["owner"] == "魏"


# ── 测试 S2-4: 攻击中立城 ────────────────────────────────

def test_attack_neutral_city():
    """中立城无防守加成，攻击方应更容易获胜。"""
    setup()
    r = client.post("/games")
    gid = r.json()["game_id"]
    token_shu = _register_and_join("蜀", "刘备", gid)

    # 攒粮草 2 回合（500 + 200 = 700 粮草）
    for _ in range(2):
        _tick(gid)

    # 中立襄阳 500 兵，无防守加成。蜀出 510 兵（花费 510 粮草，剩余 190）
    r = _submit(token_shu, gid, [
        {"type": "attack", "from": "成都", "target": "襄阳", "troops": 510},
    ])
    _tick(gid)

    r = client.get(f"/games/{gid}/state", params={"token": token_shu})
    state = r.json()
    xiangyang = [c for c in state["all_cities"] if c["name"] == "襄阳"][0]
    assert xiangyang["owner"] == "蜀"
    # 510 * 0.7 ≈ 357
    assert 300 <= xiangyang["troops"] <= 510


# ── 测试 S2-5: 邻接限制（不邻接的攻击应被 reject）─────

def test_adjacency_restriction():
    """蜀的成都和魏的洛阳不邻接，应 reject 攻击。"""
    setup()
    r = client.post("/games")
    gid = r.json()["game_id"]
    token_shu = _register_and_join("蜀", "刘备", gid)

    # 成都 -> 洛阳不邻接
    r = _submit(token_shu, gid, [
        {"type": "attack", "from": "成都", "target": "洛阳", "troops": 500},
    ])
    assert r.status_code == 400
    assert "不邻接" in r.json()["detail"]


# ── 测试 S2-6: recruit 和 grain 消耗 ──────────────────────

def test_recruit_and_grain():
    """测试招募和粮草消耗联动。"""
    setup()
    r = client.post("/games")
    gid = r.json()["game_id"]
    token_shu = _register_and_join("蜀", "刘备", gid)

    # 招募 100 兵，消耗 200 粮草
    r = _submit(token_shu, gid, [
        {"type": "recruit", "target": "成都", "amount": 100},
    ])
    assert r.status_code == 200
    assert r.json()["grain_cost"] == 200
    assert r.json()["grain_remaining"] == 300  # 500 - 200

    _tick(gid)

    r = client.get(f"/games/{gid}/state", params={"token": token_shu})
    state = r.json()
    chengdu = [c for c in state["all_cities"] if c["name"] == "成都"][0]
    # 原有兵力 + 100 招募
    assert chengdu["troops"] >= 900  # 800-1200 + 100


# ── 测试 S2-7: march 调兵 ─────────────────────────────────

def test_march_between_own_cities():
    """测试行军调兵：战斗后调兵到邻接己方城。"""
    setup()
    r = client.post("/games")
    gid = r.json()["game_id"]
    token_shu = _register_and_join("蜀", "刘备", gid)

    # 攒粮草 3 回合
    for _ in range(3):
        _tick(gid)

    # 先拿下襄阳（550 兵花费 550 粮草）
    r = _submit(token_shu, gid, [
        {"type": "attack", "from": "成都", "target": "襄阳", "troops": 550},
    ])
    _tick(gid)

    # 从成都调兵 200 到襄阳（march 不消耗粮草）
    r = _submit(token_shu, gid, [
        {"type": "march", "from": "成都", "to": "襄阳", "troops": 200},
    ])
    assert r.status_code == 200
    assert r.json()["grain_cost"] == 0  # march 不消耗粮草

    _tick(gid)

    r = client.get(f"/games/{gid}/state", params={"token": token_shu})
    state = r.json()
    chengdu = [c for c in state["all_cities"] if c["name"] == "成都"][0]
    xiangyang = [c for c in state["all_cities"] if c["name"] == "襄阳"][0]
    assert xiangyang["owner"] == "蜀"
    assert chengdu["owner"] == "蜀"

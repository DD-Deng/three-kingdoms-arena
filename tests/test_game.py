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
# Step 1 测试
# ═══════════════════════════════════════════════════════════════

# ── 测试 1: agent 注册接口可用 ──────────────────────────────

def test_agent_register():
    setup()
    r = client.post("/agents/register", json={
        "agent_name": "刘备",
        "version": "v1",
    })
    assert r.status_code == 200
    data = r.json()
    assert "agent_id" in data
    assert len(data["agent_id"]) == 32  # UUID hex
    assert "secret" in data
    assert len(data["secret"]) == 64  # token_hex(32)
    assert "player_id" in data

    # 用已有 player_id 再注册第二个 agent
    r2 = client.post("/agents/register", json={
        "player_id": data["player_id"],
        "agent_name": "曹操",
    })
    assert r2.status_code == 200
    assert r2.json()["player_id"] == data["player_id"]


# ── 测试 2: join 必须带 agent_id + secret ───────────────────

def test_join_requires_agent_credentials():
    setup()
    # 先注册一个 agent
    r = client.post("/agents/register", json={"agent_name": "刘备"})
    reg = r.json()

    # 创建对局
    r = client.post("/games")
    gid = r.json()["game_id"]

    # 正确 join
    r = client.post(f"/games/{gid}/join", json={
        "agent_id": reg["agent_id"],
        "secret": reg["secret"],
        "faction": "蜀",
    })
    assert r.status_code == 200
    assert "token" in r.json()

    # 错误 secret 被拒
    r = client.post(f"/games/{gid}/join", json={
        "agent_id": reg["agent_id"],
        "secret": "wrong-secret",
        "faction": "魏",
    })
    assert r.status_code == 400
    assert "secret" in r.json()["detail"]

    # 未注册的 agent_id 被拒
    r = client.post(f"/games/{gid}/join", json={
        "agent_id": "nonexistent",
        "secret": "whatever",
        "faction": "魏",
    })
    assert r.status_code == 400


# ── 测试 3: 7 座城 + 邻接关系正确加载 ──────────────────────

def test_seven_cities_and_adjacency():
    setup()
    r = client.post("/games")
    gid = r.json()["game_id"]

    # 注册并加入
    r = client.post("/agents/register", json={"agent_name": "刘备"})
    reg = r.json()
    r = client.post(f"/games/{gid}/join", json={
        "agent_id": reg["agent_id"],
        "secret": reg["secret"],
        "faction": "蜀",
    })
    token = r.json()["token"]

    r = client.get(f"/games/{gid}/state", params={"token": token})
    state = r.json()

    # 检查 7 座城
    assert len(state["all_cities"]) == 7
    city_names = {c["name"] for c in state["all_cities"]}
    assert city_names == {"洛阳", "长安", "邺城", "宛城", "襄阳", "成都", "建业"}

    # 检查初始归属
    city_owners = {c["name"]: c["owner"] for c in state["all_cities"]}
    assert city_owners["洛阳"] == "魏"
    assert city_owners["长安"] == "魏"
    assert city_owners["邺城"] == "魏"
    assert city_owners["成都"] == "蜀"
    assert city_owners["建业"] == "吴"
    assert city_owners["宛城"] is None  # 中立
    assert city_owners["襄阳"] is None  # 中立

    # 中立城兵力应为 500
    for c in state["all_cities"]:
        if c["name"] in ("宛城", "襄阳"):
            assert c["troops"] == 500

    # 检查邻接关系（通过 valid_actions 验证）
    # 蜀只有成都，成都只邻接襄阳
    valid_actions = state["valid_actions"]
    attack_targets = [a["target"] for a in valid_actions if a["type"] == "attack"]
    assert "襄阳" in attack_targets  # 成都->襄阳 邻接
    # 成都不能攻击洛阳（不邻接）
    assert "洛阳" not in attack_targets


# ── 测试 4: 粮草随回合增长 ─────────────────────────────────

def test_grain_increases_per_tick():
    setup()
    r = client.post("/games")
    gid = r.json()["game_id"]

    # 注册并加入蜀
    r = client.post("/agents/register", json={"agent_name": "刘备"})
    reg_shu = r.json()
    r = client.post(f"/games/{gid}/join", json={
        "agent_id": reg_shu["agent_id"],
        "secret": reg_shu["secret"],
        "faction": "蜀",
    })
    token_shu = r.json()["token"]

    # 加入魏
    r = client.post("/agents/register", json={"agent_name": "曹操"})
    reg_wei = r.json()
    client.post(f"/games/{gid}/join", json={
        "agent_id": reg_wei["agent_id"],
        "secret": reg_wei["secret"],
        "faction": "魏",
    })

    # 初始粮草
    r = client.get(f"/games/{gid}/state", params={"token": token_shu})
    assert r.json()["your_resources"]["grain"] == 500

    # 推进 3 个 tick（蜀只有 1 城，魏有 3 城）
    for _ in range(3):
        client.post(f"/games/{gid}/tick")

    r = client.get(f"/games/{gid}/state", params={"token": token_shu})
    # 蜀每 tick 产 100 粮草（1 城）, 3 ticks = +300
    assert r.json()["your_resources"]["grain"] == 800


# ═══════════════════════════════════════════════════════════════
# 保留旧测试（适配新接口）
# ═══════════════════════════════════════════════════════════════

def _register_and_join(faction: str, name: str, game_id: int) -> str:
    """辅助函数：注册 agent 并加入对局。"""
    r = client.post("/agents/register", json={"agent_name": name})
    reg = r.json()
    r = client.post(f"/games/{game_id}/join", json={
        "agent_id": reg["agent_id"],
        "secret": reg["secret"],
        "faction": faction,
    })
    return r.json()["token"]


def test_create_join_action_tick():
    setup()
    r = client.post("/games")
    gid = r.json()["game_id"]

    token_shu = _register_and_join("蜀", "刘备", gid)
    token_wei = _register_and_join("魏", "曹操", gid)

    # 查看初始状态
    r = client.get(f"/games/{gid}/state", params={"token": token_shu})
    assert r.status_code == 200
    state = r.json()
    assert state["current_tick"] == 0
    assert state["status"] == "waiting"
    assert state["your_faction"] == "蜀"
    assert len(state["your_cities"]) == 1
    assert state["your_cities"][0]["name"] == "成都"

    # 蜀攻击襄阳（中立城，邻接成都）
    r = client.post(
        f"/games/{gid}/action",
        params={"token": token_shu},
        json={"type": "attack", "target": "襄阳"},
    )
    assert r.status_code == 200

    r = client.post(f"/games/{gid}/tick")
    assert r.status_code == 200
    result = r.json()
    assert result["tick"] == 1

    # 襄阳应被蜀攻陷（蜀 800-1200 兵 vs 中立 500 兵，攻击方优势 +200）
    r = client.get(f"/games/{gid}/state", params={"token": token_shu})
    state = r.json()
    xiangyang = [c for c in state["all_cities"] if c["name"] == "襄阳"][0]
    assert xiangyang["owner"] == "蜀"
    assert len(state["last_tick_events"]) > 0


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

    # 再用同一势力 join 应被拒
    r2 = client.post("/agents/register", json={"agent_name": "刘禅"})
    reg2 = r2.json()
    r = client.post(f"/games/{gid}/join", json={
        "agent_id": reg2["agent_id"],
        "secret": reg2["secret"],
        "faction": "蜀",
    })
    assert r.status_code == 400
    assert "已被占用" in r.json()["detail"]

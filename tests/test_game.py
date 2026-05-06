from fastapi.testclient import TestClient
from app.main import app
from app.database import init_db
from sqlmodel import SQLModel
from app.database import engine

client = TestClient(app)


def setup():
    SQLModel.metadata.drop_all(engine)
    init_db()


# ── 测试 1: 创建 → 加入 → 动作 → tick → 验证状态变更 ──────
def test_create_join_action_tick():
    setup()

    # 创建
    r = client.post("/games")
    assert r.status_code == 200
    gid = r.json()["game_id"]

    # 2 个势力加入 (只用蜀和魏，避免三方对称僵局)
    r = client.post(f"/games/{gid}/join", json={"agent_name": "刘备", "faction": "蜀"})
    assert r.status_code == 200
    token_shu = r.json()["token"]

    r = client.post(f"/games/{gid}/join", json={"agent_name": "曹操", "faction": "魏"})
    assert r.status_code == 200
    token_wei = r.json()["token"]

    # 查看初始状态
    r = client.get(f"/games/{gid}/state", params={"token": token_shu})
    assert r.status_code == 200
    state = r.json()
    assert state["tick"] == 0
    assert state["status"] == "waiting"
    assert len(state["cities"]) == 3
    # 成都归蜀，洛阳归魏，建业无主
    city_owners = {c["name"]: c["owner"] for c in state["cities"]}
    assert city_owners["成都"] == "蜀"
    assert city_owners["洛阳"] == "魏"
    assert city_owners["建业"] is None

    # 蜀攻击魏的洛阳
    r = client.post(
        f"/games/{gid}/action",
        params={"token": token_shu},
        json={"type": "attack", "target": "洛阳"},
    )
    assert r.status_code == 200

    # 魏不动作，直接推进
    r = client.post(f"/games/{gid}/tick")
    assert r.status_code == 200
    result = r.json()
    assert result["tick"] == 1

    # 洛阳应该被蜀攻陷 (1000 vs 1000, 攻击方优势 +200)
    r = client.get(f"/games/{gid}/state", params={"token": token_shu})
    state = r.json()
    luoyang = [c for c in state["cities"] if c["name"] == "洛阳"][0]
    assert luoyang["owner"] == "蜀"


# ── 测试 2: 无效 token 被拒 ──────────────────────────────────
def test_bad_token():
    setup()
    r = client.post("/games")
    gid = r.json()["game_id"]

    client.post(f"/games/{gid}/join", json={"agent_name": "刘备", "faction": "蜀"})

    r = client.get(f"/games/{gid}/state", params={"token": "wrong-token"})
    assert r.status_code == 401


# ── 测试 3: 同势力重复加入被拒 ──────────────────────────────
def test_duplicate_faction():
    setup()
    r = client.post("/games")
    gid = r.json()["game_id"]

    client.post(f"/games/{gid}/join", json={"agent_name": "刘备", "faction": "蜀"})
    r = client.post(f"/games/{gid}/join", json={"agent_name": "刘禅", "faction": "蜀"})
    assert r.status_code == 400
    assert "已被占用" in r.json()["detail"]

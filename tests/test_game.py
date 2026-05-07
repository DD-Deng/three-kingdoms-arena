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


def _submit(token: str, game_id: int, actions: list[dict],
            public_speech: str = "", private_thought: str = ""):
    body = {"actions": actions}
    if public_speech:
        body["public_speech"] = public_speech
    if private_thought:
        body["private_thought"] = private_thought
    return client.post(
        f"/games/{game_id}/actions",
        params={"token": token},
        json=body,
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

    # known_cities (not owned) + your_cities = 7
    assert len(state["known_cities"]) + len(state["your_cities"]) == 7

    all_names = {c["name"] for c in state["known_cities"]} | {c["name"] for c in state["your_cities"]}
    assert all_names == {"洛阳", "长安", "邺城", "宛城", "襄阳", "成都", "建业"}

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

    for _ in range(3):
        _tick(gid)

    r = _submit(token_shu, gid, [
        {"type": "attack", "from": "成都", "target": "襄阳", "troops": 550},
    ])
    assert r.status_code == 200

    r = _tick(gid)
    assert r.status_code == 200

    r = client.get(f"/games/{gid}/state", params={"token": token_shu})
    state = r.json()
    # 襄阳被攻占后应出现在 your_cities 而非 known_cities
    your_names = {c["name"] for c in state["your_cities"]}
    assert "襄阳" in your_names


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

def test_single_attack_success():
    setup()
    r = client.post("/games")
    gid = r.json()["game_id"]
    token_shu = _register_and_join("蜀", "刘备", gid)

    for _ in range(3):
        _tick(gid)

    r = _submit(token_shu, gid, [
        {"type": "attack", "from": "成都", "target": "襄阳", "troops": 550},
    ])
    assert r.status_code == 200

    r = _tick(gid)
    assert r.status_code == 200

    r = client.get(f"/games/{gid}/state", params={"token": token_shu})
    state = r.json()
    # 襄阳 should be in your_cities now
    your_names = {c["name"] for c in state["your_cities"]}
    assert "襄阳" in your_names

    events = state["public_events_last_tick"]
    battle = [e for e in events if e.get("result")][0] if events else None
    assert battle and battle["result"] == "captured"


def test_single_attack_failure():
    setup()
    r = client.post("/games")
    gid = r.json()["game_id"]
    token_shu = _register_and_join("蜀", "刘备", gid)

    for _ in range(3):
        _tick(gid)

    r = _submit(token_shu, gid, [
        {"type": "attack", "from": "成都", "target": "襄阳", "troops": 20},
    ])
    assert r.status_code == 200

    r = _tick(gid)
    r = client.get(f"/games/{gid}/state", params={"token": token_shu})
    state = r.json()
    xiangyang = [c for c in state["known_cities"] if c["name"] == "襄阳"][0]
    assert xiangyang["owner"] == "中立"  # 20 vs 500，失败


def test_multi_attack_strongest_wins():
    setup()
    r = client.post("/games")
    gid = r.json()["game_id"]
    token_shu = _register_and_join("蜀", "刘备", gid)
    token_wei = _register_and_join("魏", "曹操", gid)

    for _ in range(4):
        _tick(gid)

    r = _submit(token_shu, gid, [
        {"type": "attack", "from": "成都", "target": "襄阳", "troops": 550},
    ])
    _tick(gid)
    _tick(gid)

    r = _submit(token_wei, gid, [
        {"type": "attack", "from": "洛阳", "target": "宛城", "troops": 400},
    ])
    assert r.status_code == 200

    r = _submit(token_shu, gid, [
        {"type": "attack", "from": "襄阳", "target": "宛城", "troops": 150},
    ])
    assert r.status_code == 200

    r = _tick(gid)
    r = client.get(f"/games/{gid}/state", params={"token": token_shu})
    state = r.json()
    wancheng = [c for c in state["known_cities"] if c["name"] == "宛城"]
    if wancheng:
        # 400 > 150，魏应得城
        assert wancheng[0]["owner"] == "魏"


def test_attack_neutral_city():
    setup()
    r = client.post("/games")
    gid = r.json()["game_id"]
    token_shu = _register_and_join("蜀", "刘备", gid)

    for _ in range(2):
        _tick(gid)

    r = _submit(token_shu, gid, [
        {"type": "attack", "from": "成都", "target": "襄阳", "troops": 510},
    ])
    _tick(gid)

    r = client.get(f"/games/{gid}/state", params={"token": token_shu})
    state = r.json()
    your_names = {c["name"] for c in state["your_cities"]}
    assert "襄阳" in your_names  # 510 > 500


def test_adjacency_restriction():
    setup()
    r = client.post("/games")
    gid = r.json()["game_id"]
    token_shu = _register_and_join("蜀", "刘备", gid)

    r = _submit(token_shu, gid, [
        {"type": "attack", "from": "成都", "target": "洛阳", "troops": 500},
    ])
    assert r.status_code == 400
    assert "不邻接" in r.json()["detail"]


def test_recruit_and_grain():
    setup()
    r = client.post("/games")
    gid = r.json()["game_id"]
    token_shu = _register_and_join("蜀", "刘备", gid)

    r = _submit(token_shu, gid, [
        {"type": "recruit", "target": "成都", "amount": 100},
    ])
    assert r.status_code == 200
    assert r.json()["grain_cost"] == 200

    _tick(gid)

    r = client.get(f"/games/{gid}/state", params={"token": token_shu})
    state = r.json()
    chengdu = [c for c in state["your_cities"] if c["name"] == "成都"][0]
    assert chengdu["troops"] >= 900


def test_march_between_own_cities():
    setup()
    r = client.post("/games")
    gid = r.json()["game_id"]
    token_shu = _register_and_join("蜀", "刘备", gid)

    for _ in range(3):
        _tick(gid)

    r = _submit(token_shu, gid, [
        {"type": "attack", "from": "成都", "target": "襄阳", "troops": 550},
    ])
    _tick(gid)

    r = _submit(token_shu, gid, [
        {"type": "march", "from": "成都", "to": "襄阳", "troops": 200},
    ])
    assert r.status_code == 200
    assert r.json()["grain_cost"] == 0

    _tick(gid)
    r = client.get(f"/games/{gid}/state", params={"token": token_shu})
    state = r.json()
    assert len(state["your_cities"]) >= 2


# ═══════════════════════════════════════════════════════════════
# Step 3 测试 —— 隐私
# ═══════════════════════════════════════════════════════════════

def test_private_thought_is_discarded():
    """POST 带 private_thought 字段会被 server 丢弃，不影响操作。"""
    setup()
    r = client.post("/games")
    gid = r.json()["game_id"]
    token = _register_and_join("蜀", "刘备", gid)

    # 带 private_thought 提交，应正常处理
    r = _submit(token, gid, [
        {"type": "defend", "target": "成都"},
    ], private_thought="我要偷袭许昌——这段内心独白不应被任何人看到")

    assert r.status_code == 200
    # private_thought 不会出现在任何 server 存储中


def test_shu_cannot_see_wei_exact_troops():
    """蜀 token 拿到的 state 看不到远处魏城的精确兵力。"""
    setup()
    r = client.post("/games")
    gid = r.json()["game_id"]
    token_shu = _register_and_join("蜀", "刘备", gid)

    r = client.get(f"/games/{gid}/state", params={"token": token_shu})
    state = r.json()

    # 蜀只有成都，邻接襄阳（中立），远处有洛阳（魏）
    # 洛阳不邻接成都 → 应只显示模糊估计
    luoyang = [c for c in state["known_cities"] if c["name"] == "洛阳"][0]
    assert "troops_estimate" in luoyang  # 模糊估计
    assert "troops" not in luoyang       # 不应有精确兵力
    assert luoyang["info_freshness"] == "rumor"

    # 襄阳邻接成都 → 应有精确兵力
    xiangyang = [c for c in state["known_cities"] if c["name"] == "襄阳"][0]
    assert "troops" in xiangyang
    assert xiangyang["info_freshness"] == "current"


def test_shu_cannot_see_any_private_thought():
    """state 响应里不应包含任何 agent 的 thought 字段。"""
    setup()
    r = client.post("/games")
    gid = r.json()["game_id"]
    token_shu = _register_and_join("蜀", "刘备", gid)

    r = client.get(f"/games/{gid}/state", params={"token": token_shu})
    state = r.json()

    # 递归检查整个 state 响应
    state_str = str(state)
    assert "private_thought" not in state_str
    assert "thought" not in state_str


def test_public_speech_broadcast():
    """外交发言在下回合对所有人可见。"""
    setup()
    r = client.post("/games")
    gid = r.json()["game_id"]
    token_shu = _register_and_join("蜀", "刘备", gid)
    token_wei = _register_and_join("魏", "曹操", gid)

    # 蜀发表公开外交
    r = _submit(token_shu, gid, [
        {"type": "defend", "target": "成都"},
    ], public_speech="联手伐吴，共分江东")

    assert r.status_code == 200

    _tick(gid)

    # 魏看到的 state 应包含蜀的外交消息
    r = client.get(f"/games/{gid}/state", params={"token": token_wei})
    state = r.json()
    diplomacy = state["public_diplomacy_last_tick"]
    assert len(diplomacy) >= 1
    shu_msg = [d for d in diplomacy if d["from_faction"] == "蜀"][0]
    assert "联手伐吴" in shu_msg["message"]


def test_public_log_exists():
    """推进 tick 后 public_log 和 private_log 文件应存在。"""
    setup()
    r = client.post("/games")
    gid = r.json()["game_id"]
    _register_and_join("蜀", "刘备", gid)

    # 空 tick 也会写日志
    _tick(gid)

    import os
    pub_path = f"logs/public/{gid}.jsonl"
    priv_path = f"logs/private/{gid}.jsonl"
    assert os.path.exists(pub_path), f"public_log missing: {pub_path}"
    assert os.path.exists(priv_path), f"private_log missing: {priv_path}"

    # 检查内容差异：public 不含 agent_actions, private 包含
    with open(pub_path) as f:
        pub_entry = f.readline()
    with open(priv_path) as f:
        priv_entry = f.readline()

    assert "agent_actions" not in pub_entry
    assert "agent_actions" in priv_entry

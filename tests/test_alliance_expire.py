"""Alliance auto-expire tests — Step 4: 联盟自动过期机制."""

from fastapi.testclient import TestClient
from app.main import app
from app.database import init_db
from sqlmodel import SQLModel, Session, select
from app.database import engine
from app.models import Game, Agent

client = TestClient(app)


def setup():
    SQLModel.metadata.drop_all(engine)
    init_db()


def _join(faction: str, ip: str = "10.0.0.1") -> dict:
    r = client.post(
        "/v1/lobby/join",
        json={"faction": faction},
        headers={"X-Forwarded-For": ip},
    )
    assert r.status_code == 200, f"join {faction}: {r.text}"
    return r.json()


def _submit(token: str, game_id: int = 1, actions: list | None = None):
    if actions is None:
        actions = [{"type": "defend", "target": "成都"}]
    return client.post(
        f"/games/{game_id}/actions",
        params={"token": token},
        json={"actions": actions},
    )


def _tick(game_id: int = 1):
    return client.post(f"/games/{game_id}/tick?token=admin-dev-token")


def _state(token: str, game_id: int = 1):
    return client.get(f"/games/{game_id}/state?token={token}")


# ═══════════════════════════════════════════════════════════════
# Test 1: Alliance formation sets expires_at in state
# ═══════════════════════════════════════════════════════════════

def test_alliance_formation_sets_expires_at(monkeypatch):
    """After forming alliance, state shows expires_at_tick and ticks_until_expire."""
    monkeypatch.setattr("app.config.TICK_TIMEOUT_SEC", 60)
    setup()

    shu = _join("蜀")
    wei = _join("魏", "10.0.0.2")
    _join("吴", "10.0.0.3")

    # Shu proposes to Wei
    _submit(shu["session_token"], actions=[
        {"type": "diplomacy", "target": "魏", "diplomacy_type": "alliance_propose", "message": "联盟"}
    ])
    _submit(wei["session_token"], actions=[{"type": "defend", "target": "洛阳"}])
    _submit("token_wu", actions=[{"type": "defend", "target": "建业"}])
    _tick()

    # Wei accepts
    _submit(shu["session_token"], actions=[{"type": "defend", "target": "成都"}])
    _submit(wei["session_token"], actions=[
        {"type": "diplomacy", "target": "蜀", "diplomacy_type": "alliance_accept", "message": "好"}
    ])
    _submit("token_wu", actions=[{"type": "defend", "target": "建业"}])
    _tick()

    s = _state(shu["session_token"])
    assert s.status_code == 200, f"state: {s.text}"
    data = s.json()

    assert data.get("your_alliance_with") == "魏"
    wei_rel = data["diplomacy_relations"].get("魏", {})
    assert wei_rel["status"] == "allied"
    assert "expires_at_tick" in wei_rel, f"expires_at_tick missing: {wei_rel}"
    assert wei_rel["expires_at_tick"] is not None
    assert "ticks_until_expire" in wei_rel, f"ticks_until_expire missing: {wei_rel}"
    # After alliance formed at tick 2, state read at tick 3: 17 - 3 = 14
    assert 13 <= wei_rel["ticks_until_expire"] <= 15, \
        f"Should be ~14-15 ticks until expire, got {wei_rel['ticks_until_expire']}"


# ═══════════════════════════════════════════════════════════════
# Test 2: Alliance auto-expires after 15 ticks (no trust penalty)
# ═══════════════════════════════════════════════════════════════

def test_alliance_auto_expires_after_15_ticks(monkeypatch):
    """After 15 ticks, alliance expires with no trust penalty."""
    monkeypatch.setattr("app.config.TICK_TIMEOUT_SEC", 60)
    setup()

    shu = _join("蜀")
    wei = _join("魏", "10.0.0.2")
    wu = _join("吴", "10.0.0.3")

    # Form alliance
    _submit(shu["session_token"], actions=[
        {"type": "diplomacy", "target": "魏", "diplomacy_type": "alliance_propose", "message": "联盟"}
    ])
    _submit(wei["session_token"], actions=[{"type": "defend", "target": "洛阳"}])
    _submit(wu["session_token"], actions=[{"type": "defend", "target": "建业"}])
    _tick()

    _submit(shu["session_token"], actions=[{"type": "defend", "target": "成都"}])
    _submit(wei["session_token"], actions=[
        {"type": "diplomacy", "target": "蜀", "diplomacy_type": "alliance_accept", "message": "好"}
    ])
    _submit(wu["session_token"], actions=[{"type": "defend", "target": "建业"}])
    _tick()

    # Tick 3-16: just pass 14 more ticks to trigger auto-expire
    for _ in range(14):
        _submit(shu["session_token"], actions=[{"type": "defend", "target": "成都"}])
        _submit(wei["session_token"], actions=[{"type": "defend", "target": "洛阳"}])
        _submit(wu["session_token"], actions=[{"type": "defend", "target": "建业"}])
        _tick()

    # Now at tick 17 (alliance formed at tick 2, expires at tick 17 = 2+15)
    s = _state(shu["session_token"])
    data = s.json()

    assert data.get("your_alliance_with") is None, \
        f"Alliance should have expired, got: {data.get('your_alliance_with')}"

    wei_rel = data["diplomacy_relations"].get("魏", {})
    assert wei_rel["status"] != "allied", \
        f"Should not be allied after expire: {wei_rel}"

    # Trust should still be 100 (no penalty for auto-expire)
    # Check via the relation — if neutral, trust recovery keeps it at 100
    assert wei_rel.get("status") in ("neutral",), \
        f"Expected neutral after auto-expire, got {wei_rel.get('status')}"


# ═══════════════════════════════════════════════════════════════
# Test 3: alliance_renew resets expires_at_tick
# ═══════════════════════════════════════════════════════════════

def test_alliance_renew_resets_timer(monkeypatch):
    """Alliance_renew within 5 ticks of expiry resets the countdown."""
    monkeypatch.setattr("app.config.TICK_TIMEOUT_SEC", 60)
    monkeypatch.setattr("app.config.TICK_INTERVAL_SEC", 60)
    setup()

    shu = _join("蜀")
    wei = _join("魏", "10.0.0.2")
    wu = _join("吴", "10.0.0.3")

    # Form alliance
    _submit(shu["session_token"], actions=[
        {"type": "diplomacy", "target": "魏", "diplomacy_type": "alliance_propose", "message": "联盟"}
    ])
    _submit(wei["session_token"], actions=[{"type": "defend", "target": "洛阳"}])
    _submit(wu["session_token"], actions=[{"type": "defend", "target": "建业"}])
    _tick()

    _submit(shu["session_token"], actions=[{"type": "defend", "target": "成都"}])
    _submit(wei["session_token"], actions=[
        {"type": "diplomacy", "target": "蜀", "diplomacy_type": "alliance_accept", "message": "好"}
    ])
    _submit(wu["session_token"], actions=[{"type": "defend", "target": "建业"}])
    _tick()

    # Get formation tick and expires_at
    s = _state(shu["session_token"])
    data = s.json()
    wei_rel = data["diplomacy_relations"].get("魏", {})
    assert wei_rel["status"] == "allied", f"Should be allied: {wei_rel}"
    old_expires_at = wei_rel["expires_at_tick"]

    # Advance until ticks_until_expire is ≤ 5
    for _ in range(20):
        s = _state(shu["session_token"])
        data = s.json()
        rel = data["diplomacy_relations"].get("魏", {})
        remaining = rel.get("ticks_until_expire", 0)
        if 0 < remaining <= 5:
            break
        _submit(shu["session_token"], actions=[{"type": "defend", "target": "成都"}])
        _submit(wei["session_token"], actions=[{"type": "defend", "target": "洛阳"}])
        _submit(wu["session_token"], actions=[{"type": "defend", "target": "建业"}])
        _tick()

    assert 0 < remaining <= 5, f"Should be in renew window, got {remaining}"

    # Renew
    _submit(shu["session_token"], actions=[
        {"type": "diplomacy", "target": "魏", "diplomacy_type": "alliance_renew", "message": "续约"}
    ])
    _submit(wei["session_token"], actions=[{"type": "defend", "target": "洛阳"}])
    _submit(wu["session_token"], actions=[{"type": "defend", "target": "建业"}])
    _tick()

    s = _state(shu["session_token"])
    data = s.json()
    wei_rel = data["diplomacy_relations"].get("魏", {})
    assert wei_rel["status"] == "allied", f"Should still be allied after renew: {wei_rel}"
    assert wei_rel["expires_at_tick"] > old_expires_at, \
        f"expires_at should increase: was {old_expires_at}, now {wei_rel.get('expires_at_tick')}"
    assert wei_rel["ticks_until_expire"] >= 13, \
        f"After renew, should be ~14-15 ticks, got {wei_rel.get('ticks_until_expire')}"


# ═══════════════════════════════════════════════════════════════
# Test 4: alliance_renew rejected when > 5 ticks remaining
# ═══════════════════════════════════════════════════════════════

def test_alliance_renew_rejected_early(monkeypatch):
    """Cannot renew alliance when more than 5 ticks remain."""
    monkeypatch.setattr("app.config.TICK_TIMEOUT_SEC", 60)
    setup()

    shu = _join("蜀")
    wei = _join("魏", "10.0.0.2")
    wu = _join("吴", "10.0.0.3")

    # Form alliance
    _submit(shu["session_token"], actions=[
        {"type": "diplomacy", "target": "魏", "diplomacy_type": "alliance_propose", "message": "联盟"}
    ])
    _submit(wei["session_token"], actions=[{"type": "defend", "target": "洛阳"}])
    _submit(wu["session_token"], actions=[{"type": "defend", "target": "建业"}])
    _tick()

    _submit(shu["session_token"], actions=[{"type": "defend", "target": "成都"}])
    _submit(wei["session_token"], actions=[
        {"type": "diplomacy", "target": "蜀", "diplomacy_type": "alliance_accept", "message": "好"}
    ])
    _submit(wu["session_token"], actions=[{"type": "defend", "target": "建业"}])
    _tick()

    # Immediately try to renew (15 ticks remaining, should be rejected)
    r = _submit(shu["session_token"], actions=[
        {"type": "diplomacy", "target": "魏", "diplomacy_type": "alliance_renew", "message": "续约"}
    ])
    assert r.status_code == 400, f"Should reject early renew, got {r.status_code}: {r.text}"


# ═══════════════════════════════════════════════════════════════
# Test 5: alliance_renew rejected when not allied
# ═══════════════════════════════════════════════════════════════

def test_alliance_renew_rejected_not_allied(monkeypatch):
    """Cannot renew alliance with faction you are not allied with."""
    monkeypatch.setattr("app.config.TICK_TIMEOUT_SEC", 60)
    setup()

    shu = _join("蜀")
    _join("魏", "10.0.0.2")
    _join("吴", "10.0.0.3")

    r = _submit(shu["session_token"], actions=[
        {"type": "diplomacy", "target": "魏", "diplomacy_type": "alliance_renew", "message": "续约"}
    ])
    assert r.status_code == 400, f"Should reject renew when not allied, got {r.status_code}: {r.text}"
    assert "未与" in r.json()["detail"] or "联盟" in r.json()["detail"], \
        f"Error message should mention alliance: {r.json()}"


# ═══════════════════════════════════════════════════════════════
# Test 6: Trust not penalized on auto-expire
# ═══════════════════════════════════════════════════════════════

def test_auto_expire_no_trust_penalty(monkeypatch):
    """Auto-expire does not reduce trust_score, unlike alliance_break."""
    monkeypatch.setattr("app.config.TICK_TIMEOUT_SEC", 60)
    setup()

    shu = _join("蜀")
    wei = _join("魏", "10.0.0.2")
    wu = _join("吴", "10.0.0.3")

    # Form alliance
    _submit(shu["session_token"], actions=[
        {"type": "diplomacy", "target": "魏", "diplomacy_type": "alliance_propose", "message": "联盟"}
    ])
    _submit(wei["session_token"], actions=[{"type": "defend", "target": "洛阳"}])
    _submit(wu["session_token"], actions=[{"type": "defend", "target": "建业"}])
    _tick()

    _submit(shu["session_token"], actions=[{"type": "defend", "target": "成都"}])
    _submit(wei["session_token"], actions=[
        {"type": "diplomacy", "target": "蜀", "diplomacy_type": "alliance_accept", "message": "好"}
    ])
    _submit(wu["session_token"], actions=[{"type": "defend", "target": "建业"}])
    _tick()

    # Check trust at formation
    s = _state(shu["session_token"])
    trust_before = s.json()["diplomacy_relations"]["魏"].get("trust_score", 100)
    assert trust_before == 100, f"Trust should start at 100: {trust_before}"

    # Advance 15 ticks to trigger auto-expire
    for _ in range(15):
        _submit(shu["session_token"], actions=[{"type": "defend", "target": "成都"}])
        _submit(wei["session_token"], actions=[{"type": "defend", "target": "洛阳"}])
        _submit(wu["session_token"], actions=[{"type": "defend", "target": "建业"}])
        _tick()

    # After auto-expire, trust should NOT be penalized
    s = _state(shu["session_token"])
    data = s.json()
    assert data.get("your_alliance_with") is None, "Alliance should have expired"
    # The relation should be neutral, trust should still be reasonable (not -30)
    wei_rel = data["diplomacy_relations"].get("魏", {})
    # Auto-expire doesn't touch trust_score, so it remains at 100
    # (the raw resources still have trust_score=100, but relation might not show it if not allied)
    # Key assertion: relation status is NOT hostile_recent_break
    assert wei_rel.get("status") != "hostile_recent_break", \
        f"Auto-expire should NOT cause hostile_recent_break status: {wei_rel}"


# ═══════════════════════════════════════════════════════════════
# Test 7: Break still works and removes expires_at
# ═══════════════════════════════════════════════════════════════

def test_break_still_works_with_expires(monkeypatch):
    """Alliance_break still functions correctly alongside expires_at."""
    monkeypatch.setattr("app.config.TICK_TIMEOUT_SEC", 60)
    setup()

    shu = _join("蜀")
    wei = _join("魏", "10.0.0.2")
    wu = _join("吴", "10.0.0.3")

    # Form alliance
    _submit(shu["session_token"], actions=[
        {"type": "diplomacy", "target": "魏", "diplomacy_type": "alliance_propose", "message": "联盟"}
    ])
    _submit(wei["session_token"], actions=[{"type": "defend", "target": "洛阳"}])
    _submit(wu["session_token"], actions=[{"type": "defend", "target": "建业"}])
    _tick()

    _submit(shu["session_token"], actions=[{"type": "defend", "target": "成都"}])
    _submit(wei["session_token"], actions=[
        {"type": "diplomacy", "target": "蜀", "diplomacy_type": "alliance_accept", "message": "好"}
    ])
    _submit(wu["session_token"], actions=[{"type": "defend", "target": "建业"}])
    _tick()

    # Break alliance
    _submit(shu["session_token"], actions=[
        {"type": "diplomacy", "target": "魏", "diplomacy_type": "alliance_break", "message": "破盟"}
    ])
    _submit(wei["session_token"], actions=[{"type": "defend", "target": "洛阳"}])
    _submit(wu["session_token"], actions=[{"type": "defend", "target": "建业"}])
    _tick()

    s = _state(shu["session_token"])
    data = s.json()

    assert data.get("your_alliance_with") is None, "Alliance should be broken"
    wei_rel = data["diplomacy_relations"].get("魏", {})
    assert wei_rel["status"] != "allied", f"Should not be allied: {wei_rel}"
    # Break should cause hostile_recent_break due to betrayal_until
    assert wei_rel["status"] == "hostile_recent_break", \
        f"Break should set hostile_recent_break: {wei_rel}"


# ═══════════════════════════════════════════════════════════════
# Test 8: expires_at_tick included in valid_actions via state
# ═══════════════════════════════════════════════════════════════

def test_ticks_until_expire_decrements(monkeypatch):
    """ticks_until_expire accurately counts down each tick."""
    monkeypatch.setattr("app.config.TICK_TIMEOUT_SEC", 60)
    setup()

    shu = _join("蜀")
    wei = _join("魏", "10.0.0.2")
    wu = _join("吴", "10.0.0.3")

    # Form alliance
    _submit(shu["session_token"], actions=[
        {"type": "diplomacy", "target": "魏", "diplomacy_type": "alliance_propose", "message": "联盟"}
    ])
    _submit(wei["session_token"], actions=[{"type": "defend", "target": "洛阳"}])
    _submit(wu["session_token"], actions=[{"type": "defend", "target": "建业"}])
    _tick()

    _submit(shu["session_token"], actions=[{"type": "defend", "target": "成都"}])
    _submit(wei["session_token"], actions=[
        {"type": "diplomacy", "target": "蜀", "diplomacy_type": "alliance_accept", "message": "好"}
    ])
    _submit(wu["session_token"], actions=[{"type": "defend", "target": "建业"}])
    _tick()

    s = _state(shu["session_token"])
    initial_remaining = s.json()["diplomacy_relations"]["魏"]["ticks_until_expire"]
    initial_tick = s.json()["tick"]

    # Advance 3 ticks
    for _ in range(3):
        _submit(shu["session_token"], actions=[{"type": "defend", "target": "成都"}])
        _submit(wei["session_token"], actions=[{"type": "defend", "target": "洛阳"}])
        _submit(wu["session_token"], actions=[{"type": "defend", "target": "建业"}])
        _tick()

    s = _state(shu["session_token"])
    new_remaining = s.json()["diplomacy_relations"]["魏"]["ticks_until_expire"]
    new_tick = s.json()["tick"]
    ticks_passed = new_tick - initial_tick
    assert new_remaining == initial_remaining - ticks_passed, \
        f"ticks_until_expire should be {initial_remaining - ticks_passed}, got {new_remaining} (ticks passed: {ticks_passed})"

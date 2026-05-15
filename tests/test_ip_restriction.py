"""IP restriction tests — ENFORCE_ONE_FACTION_PER_IP toggle."""

from fastapi.testclient import TestClient
from app.main import app
from app.database import init_db
from sqlmodel import SQLModel
from app.database import engine

client = TestClient(app)


def setup():
    SQLModel.metadata.drop_all(engine)
    init_db()


def _join(faction: str, ip: str = "10.0.0.1") -> tuple:
    r = client.post(
        "/v1/lobby/join",
        json={"faction": faction},
        headers={"X-Forwarded-For": ip},
    )
    return r.status_code, r.json()


# ═══════════════════════════════════════════════════════════════
# Test 1: Same IP joins multiple factions when switch is OFF
# ═══════════════════════════════════════════════════════════════

def test_same_ip_multi_faction_allowed(monkeypatch):
    """ENFORCE_ONE_FACTION_PER_IP=False allows same IP to join all 3 factions."""
    monkeypatch.setattr("app.config.ENFORCE_ONE_FACTION_PER_IP", False)
    monkeypatch.setattr("app.config.TICK_TIMEOUT_SEC", 60)
    setup()

    s1, d1 = _join("蜀", "10.0.0.1")
    assert s1 == 200, f"first join failed: {d1}"

    s2, d2 = _join("魏", "10.0.0.1")
    assert s2 == 200, f"second join (same IP) should succeed: {d2}"

    s3, d3 = _join("吴", "10.0.0.1")
    assert s3 == 200, f"third join (same IP) should succeed: {d3}"


# ═══════════════════════════════════════════════════════════════
# Test 2: Same IP blocked when switch is ON
# ═══════════════════════════════════════════════════════════════

def test_same_ip_blocked_when_enforced(monkeypatch):
    """ENFORCE_ONE_FACTION_PER_IP=True blocks same IP from second faction."""
    monkeypatch.setattr("app.config.ENFORCE_ONE_FACTION_PER_IP", True)
    monkeypatch.setattr("app.config.TICK_TIMEOUT_SEC", 60)
    setup()

    s1, d1 = _join("蜀", "10.0.0.1")
    assert s1 == 200, f"first join failed: {d1}"

    s2, d2 = _join("魏", "10.0.0.1")
    assert s2 in (400, 429), f"second join (same IP) should be rejected, got {s2}: {d2}"


# ═══════════════════════════════════════════════════════════════
# Test 3: Different IPs always unaffected
# ═══════════════════════════════════════════════════════════════

def test_different_ips_always_work(monkeypatch):
    """Different IPs are always allowed regardless of the switch."""
    monkeypatch.setattr("app.config.ENFORCE_ONE_FACTION_PER_IP", True)
    monkeypatch.setattr("app.config.TICK_TIMEOUT_SEC", 60)
    setup()

    s1, d1 = _join("蜀", "10.0.0.1")
    assert s1 == 200, f"first join failed: {d1}"

    s2, d2 = _join("魏", "10.0.0.2")
    assert s2 == 200, f"different IP join should succeed: {d2}"

    s3, d3 = _join("吴", "10.0.0.3")
    assert s3 == 200, f"different IP join should succeed: {d3}"

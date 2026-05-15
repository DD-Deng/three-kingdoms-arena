"""Agent soft-delete tests — is_active lifecycle, ghost agent prevention."""

import time

from fastapi.testclient import TestClient
from app.main import app
from app.database import init_db
from sqlmodel import SQLModel, Session, select
from app.database import engine
from app.models import Agent

client = TestClient(app)


def setup():
    SQLModel.metadata.drop_all(engine)
    init_db()


# ═══════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════

def _join(faction: str, ip: str = "10.0.0.1") -> dict:
    r = client.post(
        "/v1/lobby/join",
        json={"faction": faction},
        headers={"X-Forwarded-For": ip},
    )
    assert r.status_code == 200, f"join {faction}: {r.text}"
    return r.json()


def _get_agents(game_id: int = 1) -> list:
    with Session(engine) as session:
        return session.exec(
            select(Agent).where(Agent.game_id == game_id)
        ).all()


def _get_active_agents(game_id: int = 1) -> list:
    with Session(engine) as session:
        return session.exec(
            select(Agent).where(
                Agent.game_id == game_id, Agent.is_active == True
            )
        ).all()


# ═══════════════════════════════════════════════════════════════
# Test 1: Join creates agent with is_active=True
# ═══════════════════════════════════════════════════════════════

def test_join_creates_active_agent(monkeypatch):
    """Joining a faction creates an Agent with is_active=True."""
    monkeypatch.setattr("app.config.TICK_TIMEOUT_SEC", 60)
    setup()

    _join("蜀", "10.0.0.1")

    agents = _get_agents()
    shu_agents = [a for a in agents if a.faction == "蜀"]
    # 1 deactivated managed agent + 1 active self_hosted agent
    assert len(shu_agents) == 2
    active = [a for a in shu_agents if a.is_active]
    assert len(active) == 1
    assert active[0].is_active is True
    assert active[0].deactivated_at is None
    assert active[0].deactivated_reason is None
    assert active[0].agent_mode == "self_hosted"


# ═══════════════════════════════════════════════════════════════
# Test 2: Slot release deactivates agent
# ═══════════════════════════════════════════════════════════════

def test_slot_release_deactivates_agent(monkeypatch):
    """When a slot is auto-released after grace period, agent is deactivated."""
    monkeypatch.setattr("app.config.TICK_TIMEOUT_SEC", 60)
    setup()

    _join("蜀", "10.0.0.1")

    # Verify agent is active
    agents = _get_active_agents()
    shu_active = [a for a in agents if a.faction == "蜀"]
    assert len(shu_active) == 1

    # Simulate grace period expiry by directly manipulating the slot
    # (testing get_lobby_status auto-release deactivation)
    with Session(engine) as session:
        from app.models import Slot
        from datetime import datetime, timezone, timedelta
        slot = session.exec(
            select(Slot).where(Slot.game_id == 1, Slot.faction == "蜀")
        ).first()
        # Set heartbeat to > 300s ago so grace period is expired
        old_time = datetime.now(timezone.utc) - timedelta(seconds=601)
        slot.last_heartbeat_at = old_time.isoformat()
        slot.status = "disconnected"
        session.add(slot)
        session.commit()

    # Poll lobby status to trigger auto-release
    r = client.get("/v1/lobby/status")
    assert r.status_code == 200

    # After auto-release, a managed agent is spawned for the open slot
    agents = _get_active_agents()
    shu_active = [a for a in agents if a.faction == "蜀"]
    assert len(shu_active) == 1, f"Expected 1 active managed agent, got {shu_active}"
    assert shu_active[0].agent_mode == "managed"

    # Original agent records still exist (soft delete)
    all_agents = _get_agents()
    shu_all = [a for a in all_agents if a.faction == "蜀"]
    assert len(shu_all) == 3, f"Expected 3 records, got {len(shu_all)}"  # managed(deactivated) + BYOA(deactivated) + managed(active)
    inactive = [a for a in shu_all if not a.is_active]
    assert len(inactive) == 2
    reasons = {a.deactivated_reason for a in inactive}
    assert "slot_released" in reasons


# ═══════════════════════════════════════════════════════════════
# Test 3: Re-join succeeds after deactivation (no ghost 409)
# ═══════════════════════════════════════════════════════════════

def test_rejoin_after_deactivation_succeeds(monkeypatch):
    """After agent deactivation, re-joining the same faction succeeds."""
    monkeypatch.setattr("app.config.TICK_TIMEOUT_SEC", 60)
    setup()

    # First join
    _join("蜀", "10.0.0.1")

    # Simulate disconnect + grace expiry + auto-release
    with Session(engine) as session:
        from app.models import Slot
        from datetime import datetime, timezone, timedelta
        slot = session.exec(
            select(Slot).where(Slot.game_id == 1, Slot.faction == "蜀")
        ).first()
        old_time = datetime.now(timezone.utc) - timedelta(seconds=601)
        slot.last_heartbeat_at = old_time.isoformat()
        slot.status = "disconnected"
        session.add(slot)
        session.commit()

    # Trigger auto-release via lobby status poll
    client.get("/v1/lobby/status")

    # Second join — should succeed (no ghost agent blocking)
    r = client.post(
        "/v1/lobby/join",
        json={"faction": "蜀"},
        headers={"X-Forwarded-For": "10.0.0.2"},
    )
    assert r.status_code == 200, f"Re-join should succeed, got {r.status_code}: {r.text}"

    # Multiple agent records: orig managed (deactivated) + BYOA (deactivated)
    # + managed spawned after release (deactivated by rejoin) + new BYOA (active)
    all_agents = _get_agents()
    shu_agents = [a for a in all_agents if a.faction == "蜀"]
    assert len(shu_agents) >= 3, f"Expected >=3 agent records, got {len(shu_agents)}"
    inactive = [a for a in shu_agents if not a.is_active]
    active = [a for a in shu_agents if a.is_active]
    assert len(active) == 1
    assert active[0].agent_mode == "self_hosted"


# ═══════════════════════════════════════════════════════════════
# Test 4: Historical queries include inactive agents
# ═══════════════════════════════════════════════════════════════

def test_historical_queries_include_inactive_agents(monkeypatch):
    """Queries without is_active filter return all agents (historical)."""
    monkeypatch.setattr("app.config.TICK_TIMEOUT_SEC", 60)
    setup()

    _join("蜀", "10.0.0.1")

    # Deactivate via slot release
    with Session(engine) as session:
        from app.models import Slot
        from datetime import datetime, timezone, timedelta
        slot = session.exec(
            select(Slot).where(Slot.game_id == 1, Slot.faction == "蜀")
        ).first()
        old_time = datetime.now(timezone.utc) - timedelta(seconds=601)
        slot.last_heartbeat_at = old_time.isoformat()
        slot.status = "disconnected"
        session.add(slot)
        session.commit()

    client.get("/v1/lobby/status")

    # Unfiltered query returns all agents (including inactive)
    # After release: managed(deactivated) + BYOA(deactivated) + managed(active, spawned for open slot)
    all_agents = _get_agents()
    shu_agents = [a for a in all_agents if a.faction == "蜀"]
    assert len(shu_agents) >= 2
    assert any(not a.is_active for a in shu_agents)


# ═══════════════════════════════════════════════════════════════
# Test 5: Active-only queries exclude deactivated agents
# ═══════════════════════════════════════════════════════════════

def test_active_only_queries_exclude_deactivated(monkeypatch):
    """Queries with is_active=True exclude deactivated agents."""
    monkeypatch.setattr("app.config.TICK_TIMEOUT_SEC", 60)
    setup()

    _join("蜀", "10.0.0.1")
    _join("魏", "10.0.0.2")

    # Deactivate 蜀 via slot release
    with Session(engine) as session:
        from app.models import Slot
        from datetime import datetime, timezone, timedelta
        slot = session.exec(
            select(Slot).where(Slot.game_id == 1, Slot.faction == "蜀")
        ).first()
        old_time = datetime.now(timezone.utc) - timedelta(seconds=601)
        slot.last_heartbeat_at = old_time.isoformat()
        slot.status = "disconnected"
        session.add(slot)
        session.commit()

    client.get("/v1/lobby/status")

    # A managed agent is spawned for the now-open 蜀 slot
    # Active-only query should include the managed agent
    active = _get_active_agents()
    active_factions = {a.faction for a in active}
    assert "蜀" in active_factions, f"Managed agent should fill open slot, got {active_factions}"
    assert "魏" in active_factions
    # The 蜀 active agent should be managed
    shu_agents = [a for a in active if a.faction == "蜀"]
    assert shu_agents[0].agent_mode == "managed"


# ═══════════════════════════════════════════════════════════════
# Test 6: Token auth rejects deactivated agent
# ═══════════════════════════════════════════════════════════════

def test_deactivated_agent_token_rejected(monkeypatch):
    """Deactivated agent's token should not authenticate."""
    monkeypatch.setattr("app.config.TICK_TIMEOUT_SEC", 60)
    setup()

    shu = _join("蜀", "10.0.0.1")

    # Deactivate via slot release
    with Session(engine) as session:
        from app.models import Slot
        from datetime import datetime, timezone, timedelta
        slot = session.exec(
            select(Slot).where(Slot.game_id == 1, Slot.faction == "蜀")
        ).first()
        old_time = datetime.now(timezone.utc) - timedelta(seconds=601)
        slot.last_heartbeat_at = old_time.isoformat()
        slot.status = "disconnected"
        session.add(slot)
        session.commit()

    client.get("/v1/lobby/status")

    # Old token should be rejected
    r = client.get(f"/games/1/state?token={shu['session_token']}")
    assert r.status_code in (401, 403), f"Expected 401/403, got {r.status_code}"

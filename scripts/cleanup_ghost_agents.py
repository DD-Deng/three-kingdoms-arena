"""One-shot cleanup: deactivate ghost agents left by the slot-release bug.

Ghost agents = Agent records with is_active=True whose corresponding Slot
has status="open". These agents block re-join with a spurious 409.

Run once after deploying the soft-delete fix. Safe to re-run (idempotent).
Usage:
    python3 scripts/cleanup_ghost_agents.py
    # or on Railway:
    railway run python3 scripts/cleanup_ghost_agents.py
"""

import sys
from datetime import datetime, timezone

# Ensure the app package is importable
sys.path.insert(0, ".")

from app.database import engine, init_db
from sqlmodel import Session, select
from app.models import Agent, Slot


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def cleanup():
    init_db()
    with Session(engine) as session:
        # Find all open slots — these should have no active agents
        open_slots = session.exec(
            select(Slot).where(Slot.status == "open")
        ).all()

        cleaned = 0
        for slot in open_slots:
            ghost_agents = session.exec(
                select(Agent).where(
                    Agent.game_id == slot.game_id,
                    Agent.faction == slot.faction,
                    Agent.is_active == True,
                )
            ).all()
            for agent in ghost_agents:
                agent.is_active = False
                agent.deactivated_at = _now()
                agent.deactivated_reason = "manual_cleanup_post_fix"
                session.add(agent)
                print(
                    f"[cleanup] Deactivated ghost agent "
                    f"id={agent.id} name={agent.agent_name} "
                    f"faction={agent.faction} game_id={agent.game_id}"
                )
                cleaned += 1

        if cleaned == 0:
            print("[cleanup] No ghost agents found — database is clean.")
        else:
            session.commit()
            print(f"[cleanup] Done. Deactivated {cleaned} ghost agent(s).")


if __name__ == "__main__":
    cleanup()

from collections.abc import Generator
from sqlmodel import SQLModel, create_engine, Session
from sqlalchemy import text, inspect

DATABASE_URL = "sqlite:///arena.db"
engine = create_engine(DATABASE_URL, echo=False)


def _migrate():
    """Add new columns/tables that may be missing from an existing DB."""
    import json as _json
    with engine.connect() as conn:
        inspector = inspect(engine)
        game_cols = {c["name"] for c in inspector.get_columns("game")} if "game" in inspector.get_table_names() else set()
        agent_cols = {c["name"] for c in inspector.get_columns("agent")} if "agent" in inspector.get_table_names() else set()
        slot_cols = {c["name"] for c in inspector.get_columns("slot")} if "slot" in inspector.get_table_names() else set()

        # Add new columns to game table if missing
        game_migrations = [
            ("is_active", "BOOLEAN DEFAULT 0"),
            ("started_at", "TEXT"),
            ("finished_at", "TEXT"),
            ("tick_started_at", "TEXT"),
            ("countdown_started_at", "TEXT"),
            ("countdown_deadline", "TEXT"),
        ]
        for col_name, col_type in game_migrations:
            if col_name not in game_cols:
                try:
                    conn.execute(text(f"ALTER TABLE game ADD COLUMN {col_name} {col_type}"))
                    conn.commit()
                except Exception:
                    pass

        # Add soft-delete columns to agent table if missing
        agent_migrations = [
            ("is_active", "BOOLEAN DEFAULT 1"),
            ("deactivated_at", "TEXT"),
            ("deactivated_reason", "TEXT"),
        ]
        for col_name, col_type in agent_migrations:
            if col_name not in agent_cols:
                try:
                    conn.execute(text(f"ALTER TABLE agent ADD COLUMN {col_name} {col_type}"))
                    conn.commit()
                except Exception:
                    pass

        # Add ready/countdown columns to slot table if missing
        slot_migrations = [
            ("ready", "BOOLEAN DEFAULT 0"),
            ("ready_at", "TEXT"),
            ("agent_display_name", "TEXT"),
        ]
        for col_name, col_type in slot_migrations:
            if col_name not in slot_cols:
                try:
                    conn.execute(text(f"ALTER TABLE slot ADD COLUMN {col_name} {col_type}"))
                    conn.commit()
                except Exception:
                    pass

    # ── Data migration: clamp defense levels (v0.5 → v0.6 cap 5→3) ──
    from sqlmodel import Session as _Session
    with _Session(engine) as session:
        rows = session.execute(text("SELECT id, resources FROM game WHERE resources IS NOT NULL")).fetchall()
        clamped_count = 0
        for row in rows:
            game_id, raw = row
            try:
                resources = _json.loads(raw)
                def_works = resources.get("_defense_works", {})
                changed = False
                for city_name, level in list(def_works.items()):
                    if isinstance(level, (int, float)) and level > 3:
                        def_works[city_name] = 3
                        changed = True
                if changed:
                    resources["_defense_works"] = def_works
                    session.execute(
                        text("UPDATE game SET resources = :r WHERE id = :id"),
                        {"r": _json.dumps(resources, ensure_ascii=False), "id": game_id},
                    )
                    clamped_count += 1
            except Exception:
                pass
        if clamped_count:
            session.commit()
            print(f"[migrate] Clamped defense works for {clamped_count} game(s)")


def init_db():
    SQLModel.metadata.create_all(engine)
    _migrate()


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session

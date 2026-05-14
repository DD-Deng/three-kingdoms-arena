from collections.abc import Generator
from sqlmodel import SQLModel, create_engine, Session
from sqlalchemy import text, inspect

DATABASE_URL = "sqlite:///arena.db"
engine = create_engine(DATABASE_URL, echo=False)


def _migrate():
    """Add new columns/tables that may be missing from an existing DB."""
    with engine.connect() as conn:
        # Check existing game columns
        inspector = inspect(engine)
        game_cols = {c["name"] for c in inspector.get_columns("game")} if "game" in inspector.get_table_names() else set()

        # Add new columns to game table if missing
        migrations = [
            ("is_active", "BOOLEAN DEFAULT 0"),
            ("started_at", "TEXT"),
            ("finished_at", "TEXT"),
            ("tick_started_at", "TEXT"),
        ]
        for col_name, col_type in migrations:
            if col_name not in game_cols:
                try:
                    conn.execute(text(f"ALTER TABLE game ADD COLUMN {col_name} {col_type}"))
                    conn.commit()
                except Exception:
                    pass


def init_db():
    SQLModel.metadata.create_all(engine)
    _migrate()


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session

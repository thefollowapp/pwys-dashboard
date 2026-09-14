import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./dev.db")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def run_column_migrations() -> None:
    """Add columns introduced after a table already existed in production.

    `Base.metadata.create_all` only creates missing tables, so a new column on an
    existing table needs to be added by hand here. Safe to run on every startup.
    """
    inspector = inspect(engine)
    if "sms_events" not in inspector.get_table_names():
        return
    columns = {col["name"]: col for col in inspector.get_columns("sms_events")}
    if "message_type" not in columns:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE sms_events ADD COLUMN message_type VARCHAR(64)"))
    elif not DATABASE_URL.startswith("sqlite") and columns["message_type"].get("type").length == 32:
        # Custom notice-type keys and recurring-notice slugs can run longer than the original limit.
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE sms_events ALTER COLUMN message_type TYPE VARCHAR(64)"))

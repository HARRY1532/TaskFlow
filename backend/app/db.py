import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./taskflow.db")
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)

if DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    with SessionLocal() as session:
        yield session


def migrate_sqlite_user_columns():
    """Apply the small additive migration for databases created before account profiles."""
    if not DATABASE_URL.startswith("sqlite") or "users" not in inspect(engine).get_table_names():
        return
    existing = {column["name"] for column in inspect(engine).get_columns("users")}
    additions = {
        "is_admin": "BOOLEAN NOT NULL DEFAULT 0",
        "is_active": "BOOLEAN NOT NULL DEFAULT 1",
        "avatar_data": "BLOB",
        "avatar_mime": "VARCHAR(32)",
    }
    with engine.begin() as connection:
        for name, definition in additions.items():
            if name not in existing:
                connection.execute(text(f"ALTER TABLE users ADD COLUMN {name} {definition}"))


def migrate_sqlite_project_columns():
    if not DATABASE_URL.startswith("sqlite") or "projects" not in inspect(engine).get_table_names():
        return
    existing = {column["name"] for column in inspect(engine).get_columns("projects")}
    with engine.begin() as connection:
        if "requirements" not in existing:
            connection.execute(text("ALTER TABLE projects ADD COLUMN requirements TEXT NOT NULL DEFAULT ''"))
        if "github_repo_url" not in existing:
            connection.execute(text("ALTER TABLE projects ADD COLUMN github_repo_url VARCHAR(300)"))


def migrate_sqlite_task_columns():
    if not DATABASE_URL.startswith("sqlite") or "tasks" not in inspect(engine).get_table_names():
        return
    existing = {column["name"] for column in inspect(engine).get_columns("tasks")}
    with engine.begin() as connection:
        if "estimated_hours" not in existing:
            connection.execute(text("ALTER TABLE tasks ADD COLUMN estimated_hours INTEGER"))
        if "required_skills" not in existing:
            connection.execute(text("ALTER TABLE tasks ADD COLUMN required_skills JSON NOT NULL DEFAULT '[]'"))
        if "code_url" not in existing:
            connection.execute(text("ALTER TABLE tasks ADD COLUMN code_url VARCHAR(2048)"))
        if "code_metadata" not in existing:
            connection.execute(text("ALTER TABLE tasks ADD COLUMN code_metadata JSON"))
        if "test_url" not in existing:
            connection.execute(text("ALTER TABLE tasks ADD COLUMN test_url VARCHAR(2048)"))
        if "test_note" not in existing:
            connection.execute(text("ALTER TABLE tasks ADD COLUMN test_note TEXT"))
        if "development_checklist" not in existing:
            connection.execute(text("ALTER TABLE tasks ADD COLUMN development_checklist JSON NOT NULL DEFAULT '[]'"))

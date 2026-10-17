from datetime import datetime
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    inspect,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker


class Base(DeclarativeBase):
    pass


class Profile(Base):
    __tablename__ = "profiles"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    profile_directory: Mapped[str] = mapped_column(String(64), nullable=False)
    user_data_dir: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    imported: Mapped[bool] = mapped_column(Boolean, default=False)
    important: Mapped[bool] = mapped_column(Boolean, default=False)
    browser_type: Mapped[str] = mapped_column(String(30), default="Google Chrome")
    browser_binary: Mapped[str] = mapped_column(String(500), nullable=False)
    color: Mapped[str] = mapped_column(String(20), default="#4285F4")
    notes: Mapped[str] = mapped_column(Text, default="")
    tags: Mapped[str] = mapped_column(Text, default="")
    purpose: Mapped[str] = mapped_column(String(120), default="")
    group_name: Mapped[str] = mapped_column(String(120), default="")
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    proxy_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    proxy_scheme: Mapped[str] = mapped_column(String(20), default="http")
    proxy_host: Mapped[str] = mapped_column(String(255), default="")
    proxy_port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    startup_urls: Mapped[str] = mapped_column(Text, default="")
    extra_arguments: Mapped[str] = mapped_column(Text, default="")
    remote_debugging: Mapped[bool] = mapped_column(Boolean, default=False)
    debug_port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    channel_url: Mapped[str] = mapped_column(String(500), default="")
    automation_config: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="STOPPED")
    pid: Mapped[int | None] = mapped_column(Integer, nullable=True)
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now
    )
    last_opened_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    tasks: Mapped[list["Task"]] = relationship(back_populates="profile")


class Task(Base):
    __tablename__ = "tasks"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    profile_id: Mapped[str] = mapped_column(ForeignKey("profiles.id"), nullable=False)
    action_type: Mapped[str] = mapped_column(String(30), nullable=False)
    payload: Mapped[str] = mapped_column(Text, default="")
    schedule_type: Mapped[str] = mapped_column(String(30), default="immediate")
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    interval_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # When set, the task runs for every profile in this group; profile_id is only an anchor.
    target_group: Mapped[str] = mapped_column(String(120), default="")
    max_retries: Mapped[int] = mapped_column(Integer, default=0)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(20), default="PENDING")
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now
    )
    profile: Mapped[Profile] = relationship(back_populates="tasks")


class TaskRun(Base):
    __tablename__ = "task_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    profile_id: Mapped[str] = mapped_column(String(36), nullable=False)
    profile_name: Mapped[str] = mapped_column(String(120), default="")
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="RUNNING")
    attempts: Mapped[int] = mapped_column(Integer, default=1)
    error: Mapped[str] = mapped_column(Text, default="")
    detail: Mapped[str] = mapped_column(Text, default="")


def create_session_factory(db_url: str):
    # timeout: the GUI, scheduler and CLI may write at the same time.
    engine = create_engine(db_url, connect_args={"check_same_thread": False, "timeout": 15})
    Base.metadata.create_all(engine)
    migrations = {
        "profiles": {
            "user_data_dir": "VARCHAR(1000)",
            "imported": "BOOLEAN NOT NULL DEFAULT 0",
            "important": "BOOLEAN NOT NULL DEFAULT 0",
            "purpose": "VARCHAR(120) NOT NULL DEFAULT ''",
            "group_name": "VARCHAR(120) NOT NULL DEFAULT ''",
            "pinned": "BOOLEAN NOT NULL DEFAULT 0",
            "remote_debugging": "BOOLEAN NOT NULL DEFAULT 0",
            "debug_port": "INTEGER",
            "channel_url": "VARCHAR(500) NOT NULL DEFAULT ''",
            "automation_config": "TEXT NOT NULL DEFAULT ''",
        },
        "tasks": {
            "target_group": "VARCHAR(120) NOT NULL DEFAULT ''",
            "max_retries": "INTEGER NOT NULL DEFAULT 0",
        },
        "task_runs": {"detail": "TEXT NOT NULL DEFAULT ''"},
    }
    with engine.begin() as connection:
        for table, columns in migrations.items():
            existing = {column["name"] for column in inspect(engine).get_columns(table)}
            for name, definition in columns.items():
                if name not in existing:
                    connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {definition}"))
    return sessionmaker(bind=engine, expire_on_commit=False)

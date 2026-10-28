"""Database configuration shared by the API and the standalone init command."""
from app.core.config import get_database_settings

from sqlalchemy import URL, create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    pass


def database_url():
    config = get_database_settings()
    return URL.create('postgresql+psycopg', username=config.username, password=config.password,
                      host=config.host, port=config.port, database=config.name)


def make_database():
    engine = create_engine(database_url(), pool_pre_ping=True)
    return engine, sessionmaker(engine, expire_on_commit=False)


def upgrade_database(engine):
    """Apply versioned migrations, serialized across API and worker startup."""
    from pathlib import Path
    from alembic import command
    from alembic.config import Config

    root = Path(__file__).resolve().parents[2]
    config = Config(str(root / "alembic.ini"))
    with engine.begin() as connection:
        if engine.dialect.name == "postgresql":
            connection.execute(text("SELECT pg_advisory_xact_lock(731904823)"))
        config.attributes["connection"] = connection
        command.upgrade(config, "head")

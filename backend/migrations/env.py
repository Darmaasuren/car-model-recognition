"""Alembic environment; credentials come only from centralized configuration."""
from alembic import context
from app.core.database import Base, make_database
import app.models.user
import app.models.recognition
import app.models.source_token
import app.models.sync_state
import app.models.video_session


def migrate(connection):
    context.configure(connection=connection, target_metadata=Base.metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    raise RuntimeError("Migrations require an online connection to inspect existing legacy tables.")
else:
    supplied = context.config.attributes.get("connection")
    if supplied is not None:
        migrate(supplied)
    else:
        from sqlalchemy import text
        engine, _ = make_database()
        try:
            with engine.begin() as connection:
                if connection.dialect.name == "postgresql":
                    connection.execute(text("SELECT pg_advisory_xact_lock(731904823)"))
                migrate(connection)
        finally:
            engine.dispose()

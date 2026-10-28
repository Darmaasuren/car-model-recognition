"""Apply schema migrations: python -m app.commands.migrate."""
from app.core.database import make_database, upgrade_database


def main():
    engine, _ = make_database()
    try:
        upgrade_database(engine)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()

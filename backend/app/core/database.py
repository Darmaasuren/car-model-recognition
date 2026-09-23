"""Database configuration shared by the API and the standalone init command."""
import os

from sqlalchemy import URL, create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    pass


def database_url():
    return URL.create(
        'postgresql+psycopg',
        username=os.getenv('DB_USER', 'vehicle_app'),
        password=os.environ['DB_PASSWORD'],
        host=os.getenv('DB_HOST', 'localhost'),
        port=int(os.getenv('DB_PORT', '5432')),
        database=os.getenv('DB_NAME', 'vehicle_recognition'),
    )


def make_database():
    engine = create_engine(database_url(), pool_pre_ping=True)
    return engine, sessionmaker(engine, expire_on_commit=False)

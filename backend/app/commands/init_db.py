from sqlalchemy import select

from app.core.database import Base, make_database
from app.models.user_model import User
import app.models.service_token  # Register the service token table.
import app.models.vehicle_recognition
from app.core.passwords import hasher


def main():
    engine, factory = make_database()
    try:
        Base.metadata.create_all(engine)
        username = input('Admin username: ').strip().lower()
        if not username:
            raise ValueError('Username is required.')
        with factory() as db:
            if db.scalar(select(User).where(User.username == username)):
                raise ValueError('Already exists user with this username.')
            password = input('Password: ')
            if not password:
                raise ValueError('Password is required.')
            if password != input('Confirm password: '):
                raise ValueError('Passwords do not match.')
            db.add(User(username=username, password_hash=hasher.hash(password), role='admin'))
            db.commit()
        print('Created admin user.')
    finally:
        engine.dispose()


if __name__ == '__main__':
    main()

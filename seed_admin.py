"""One-time script to create the first admin user."""
import os
import sys
import datetime as dt
from dotenv import load_dotenv

load_dotenv()

from DatabaseOperation.SQLAlchemy.ConnectionFactory import ConnectionFactory
from DatabaseOperation.DatabaseModels.master_models import Base, Users
from werkzeug.security import generate_password_hash

USERNAME = os.getenv("SEED_USERNAME", "admin")
PASSWORD = os.getenv("SEED_PASSWORD", "Welcome@123")
FIRSTNAME = os.getenv("SEED_FIRSTNAME", "Admin")
ROLE = "admin"

conn = ConnectionFactory()
conn.create_all_tables(base=Base)

session = conn.get_session()
try:
    existing = session.query(Users).filter_by(username=USERNAME, role=ROLE).one_or_none()
    if existing:
        print(f"User '{USERNAME}' with role '{ROLE}' already exists (id={existing.id}). Nothing to do.")
        sys.exit(0)

    now = dt.datetime.now(tz=dt.timezone.utc)
    user = Users(
        username=USERNAME,
        role=ROLE,
        firstname=FIRSTNAME,
        password=generate_password_hash(PASSWORD, method="pbkdf2:sha256"),
        active=True,
        reset_password=False,
        create_date=now,
        modify_date=now,
    )
    session.add(user)
    session.commit()
    print(f"Admin user created — username: {USERNAME}  password: {PASSWORD}")
finally:
    session.close()

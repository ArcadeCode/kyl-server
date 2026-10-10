"""
./src/app.py

Starting point of the KYL-server
"""

from os import getenv

from flask import Flask

from src.dbsetup import db
from src.routes.sign import sign
from src.routes.token import token

PG_HOST = getenv("POSTGRES_HOST")
PG_PORT = getenv("POSTGRES_PORT")
PG_DB = getenv("POSTGRES_DATABASE")
PG_USER = getenv("POSTGRES_USERNAME")
PG_PASSWORD = getenv("POSTGRES_PASSWORD")

print(f"Connecting to Postgres at {PG_HOST}:{PG_PORT}/{PG_DB} as {PG_USER}")

if None in [PG_HOST, PG_PORT, PG_DB, PG_USER, PG_PASSWORD]:
    raise ValueError(
        "Missing one or more required environment variables: "
        "POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DATABASE, POSTGRES_USERNAME, POSTGRES_PASSWORD"
    )

# 1. Initialize the Flask App
app = Flask(__name__)
# 2. Add SqlAlchemy connexion
app.config["SQLALCHEMY_DATABASE_URI"] = (
    f"postgresql+psycopg2://{PG_USER}:{PG_PASSWORD}@{PG_HOST}:{PG_PORT}/{PG_DB}"
)
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_pre_ping": True
}  # pool_pre_ping avoids dead connection errors after a Postgres restart.
db.init_app(app)

# 3. Add blueprints
app.register_blueprint(sign)
app.register_blueprint(token)

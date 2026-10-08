"""
./src/app.py

Starting point of the KYL-server
"""

from os import getenv

from flask import Flask

from routes.sign import sign
from routes.token import token

PG_HOST = getenv("POSTGRES_HOST")
PG_PORT = getenv("POSTGRES_PORT")
PG_DB = getenv("POSTGRES_DATABASE")
PG_USER = getenv("POSTGRES_USER")
PG_PASSWORD = getenv("POSTGRES_PASSWORD")

# 1. Initialize the Flask App
app = Flask(__name__)
# 2. Add SqlAlchemy connexion
app.config["SQLALCHEMY_DATABASE_URI"] = (
    f"postgresql+psycopg2://{PG_USER}:{PG_PASSWORD}@{PG_HOST}:{PG_PORT}/{PG_DB}"
)
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_pre_ping": True
}  # pool_pre_ping avoids dead connection errors after a Postgres restart.

# 3. Add blueprints
app.register_blueprint(sign)
app.register_blueprint(token)

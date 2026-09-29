"""
./src/app.py

Starting point of the KYL-server
"""

from os import getenv

from flask import Flask

from routes.sign import sign

PG_HOST = getenv("POSTGRES_HOST")
PG_PORT = getenv("POSTGRES_PORT")
PG_DB = getenv("POSTGRES_DATABASE")
PG_USER = getenv("POSTGRES_USER")
PG_PASSWORD = getenv("POSTGRES_PASSWORD")

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = f"postgresql+psycopg2://{PG_USER}:{PG_PASSWORD}@{PG_HOST}:{PG_PORT}/{PG_DB}"
app.register_blueprint(sign)
'''
pool_pre_ping avoids dead connection errors after a Postgres restart.
If the password contains special characters, use sqlalchemy.engine.URL.create(...)
instead of an f-string.
'''
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True}
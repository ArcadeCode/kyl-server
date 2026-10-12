"""
./src/app.py

Starting point of the KYL-server: `create_app()` is an app factory, so tests
can build an app with their own configuration.

    flask --app app run --debug       # development
    gunicorn "app:create_app()"       # production
    flask --app app init-db           # create the tables
"""

from os import getenv

import click
from flask import Flask
from sqlalchemy.engine import URL

import models  # noqa: F401  (registers every table on the metadata)
from database import db
from routes.sign import sign
from routes.token import token


def _database_url() -> URL:
    port = getenv("POSTGRES_PORT")
    return URL.create(
        "postgresql+psycopg2",
        username=getenv("POSTGRES_USERNAME"),
        password=getenv("POSTGRES_PASSWORD"),
        host=getenv("POSTGRES_HOST"),
        port=int(port) if port else None,
        database=getenv("POSTGRES_DATABASE"),
    )


def create_app(config: dict | None = None) -> Flask:
    # 1. Initialize the Flask App
    app = Flask(__name__)

    # 2. Configuration (overridable, e.g. by the tests)
    app.config["SQLALCHEMY_DATABASE_URI"] = _database_url()
    # pool_pre_ping avoids dead connection errors after a Postgres restart.
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True}
    if config:
        app.config.update(config)

    # 3. Add SQLAlchemy
    db.init_app(app)

    # 4. Add blueprints
    app.register_blueprint(sign)
    app.register_blueprint(token)

    # 5. CLI
    @app.cli.command("init-db")
    def init_db_command():
        """Create every missing table."""
        db.create_all()
        click.echo("Tables created.")

    return app

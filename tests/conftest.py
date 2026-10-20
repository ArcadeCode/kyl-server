"""
Shared fixtures.

Unit tests (tests/unit) need nothing. Integration tests (tests/integration) need
a PostgreSQL reachable at TEST_DATABASE_URL (default: the one started by
`docker compose -f compose.test.yml up -d`). Run only the unit tests with:

    uv run pytest -m "not integration"
"""

import os
from datetime import datetime, timedelta, timezone

import bcrypt
import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError

from app import create_app
from database import db
from models import Account, Token
from services.token import generate_and_hash_token

DEFAULT_TEST_DATABASE_URL = "postgresql+psycopg2://kyl_test:kyl_test@localhost:5433/kyl_test"


def pytest_collection_modifyitems(items):
    """Everything under tests/integration is automatically marked `integration`."""
    for item in items:
        if "/integration/" in str(item.fspath).replace(os.sep, "/"):
            item.add_marker(pytest.mark.integration)


def fast_hash(password: str) -> str:
    """bcrypt hash with the minimum cost: fixtures must not spend ~250 ms per account."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=4)).decode()


@pytest.fixture(scope="session")
def database_url() -> str:
    url = os.getenv("TEST_DATABASE_URL", DEFAULT_TEST_DATABASE_URL)
    # The fixtures below wipe every table: refuse to run on anything that
    # is not clearly a test database.
    if not (make_url(url).database or "").endswith("_test"):
        pytest.exit(
            f"Refusing to run: database name of TEST_DATABASE_URL must end with '_test' ({url})",
            returncode=2,
        )
    return url


@pytest.fixture(scope="session")
def app(database_url):
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": database_url})
    with app.app_context():
        try:
            db.session.execute(text("SELECT 1"))
        except OperationalError as exc:
            pytest.fail(
                "Test PostgreSQL unreachable. Start it with "
                "`docker compose -f compose.test.yml up -d` "
                f"(or set TEST_DATABASE_URL).\n{exc}",
                pytrace=False,
            )
        db.drop_all()
        db.create_all()
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture(autouse=True)
def _clean_tables(request):
    """Empty every table after each integration test (unit tests never touch the DB)."""
    yield
    if "app" not in request.fixturenames:
        return
    app = request.getfixturevalue("app")
    with app.app_context():
        db.session.rollback()
        for table in reversed(db.metadata.sorted_tables):
            db.session.execute(table.delete())
        db.session.commit()
        db.session.remove()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def make_account(app):
    """Insert an account directly in DB. Returns its plain credentials."""

    def _make(email="user@example.com", password="abc12", name="User"):
        with app.app_context():
            db.session.add(Account(email=email, name=name, password=fast_hash(password)))
            db.session.commit()
        return {"email": email, "password": password, "name": name}

    return _make


@pytest.fixture
def make_token(app):
    """Insert a token directly in DB. Returns the RAW token (what a client holds)."""

    def _make(email, *, expires_in=timedelta(days=30), revoked=False):
        key, key_hash = generate_and_hash_token()
        now = datetime.now(timezone.utc)
        with app.app_context():
            db.session.add(
                Token(
                    token_hash=key_hash,
                    created_at=now,
                    expires_at=now + expires_in,
                    revoked_at=now if revoked else None,
                    account_email=email,
                )
            )
            db.session.commit()
        return key

    return _make


def bearer(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}

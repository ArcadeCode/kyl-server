# Writing integration tests for kyl-server

This guide explains how the test suite is organised, which fixtures and helpers
exist, and how to add a new integration test for a route.

---

## 1. Test layout

```
tests/
  conftest.py                 # shared fixtures and helpers (read this first)
  unit/                       # pure logic, no database
  integration/                # HTTP routes + database, needs PostgreSQL
    test_auth.py              # @require_token behaviour (on a throw-away route)
    test_sign_routes.py       # POST /api/v1/connexion/signup
    test_token_routes.py      # POST /api/v1/token/create and /revoke
    test_models.py            # schema, constraints, cascades
    test_app.py               # CLI commands
    test_deck_routes.py       # GET/POST /decks, PATCH/DELETE /deck/<id>
    test_deck_cards_routes.py # GET/POST /deck/<id>/cards
    test_card_routes.py       # GET/PATCH/DELETE /card/<id>
    test_protected_routes.py  # every deck/card route rejects anonymous callers
```

Rule of thumb:

- **`unit/`**: no `app`, no `client`, no database fixture. Fast.
- **`integration/`**: anything that uses `app`, `client`, or the `make_*` fixtures.
  Files there are automatically marked `integration` by `conftest.py`.

---

## 2. Running the tests

The integration tests need the throw-away PostgreSQL defined in `compose.test.yml`
(port `5433`, data in RAM, database `kyl_test`).

```bash
# Start the test database (once per work session)
docker compose -f compose.test.yml up -d

# Everything
uv run pytest

# Unit tests only (no database needed)
uv run pytest -m "not integration"

# One file, verbose
uv run pytest tests/integration/test_token_routes.py -v

# One test
uv run pytest tests/integration/test_token_routes.py::TestRevoke::test_revokes_the_token_used_for_the_request

# With coverage
uv run pytest --cov=src --cov-report=term-missing

# Stop the database
docker compose -f compose.test.yml down
```

The connection string defaults to
`postgresql+psycopg2://kyl_test:kyl_test@localhost:5433/kyl_test`.
Override it with `TEST_DATABASE_URL` if needed.

**Safety guard:** the database name **must end with `_test`**. If it does not, the
session stops immediately with `Refusing to run`. This protects you from wiping a
development database, because the fixtures drop and empty every table.

---

## 3. How the database lifecycle works

| When | What happens | Fixture |
|---|---|---|
| Once per test run | Tables are dropped and recreated (`drop_all` / `create_all`) | `app` (session scope) |
| After every integration test | Every table is emptied, in reverse dependency order | `_clean_tables` (autouse) |
| Per test | Only the data the test creates exists | `make_*` fixtures |

Consequences:

- **Never rely on data from another test.** Each test must create what it needs.
- **Never rely on a particular order** between tests.
- **Do not seed a "complete" demo database.** It couples tests to each other:
  adding one row to the seed breaks unrelated assertions.

---

## 4. Fixtures

All fixtures live in `tests/conftest.py`.

### `database_url` (session)

Returns the test database URL and checks that its name ends with `_test`.
You rarely need it directly.

### `app` (session)

A Flask application built with `create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": ...})`.
It drops and recreates the schema once for the whole run.
Use it when you need to touch the database directly, inside `app.app_context()`.

```python
def test_something_in_the_db(app):
    with app.app_context():
        ...
```

### `client` (function)

`app.test_client()`. It is what you use to call routes:

```python
response = client.post("/api/v1/token/create", json={...})
```

### `make_account` (function)

Inserts an `Account` directly in the database. The password is hashed with
bcrypt at the minimum cost, so fixtures stay fast.

```python
def test_something(make_account):
    user = make_account()                                   # user@example.com / abc12
    other = make_account(email="b@example.com", password="xyz99", name="B")
```

Returns a dict: `{"email", "password", "name"}`. The password is the **raw** one,
so you can log in with it.

### `make_token` (function)

Inserts a `Token` row for an account and returns the **raw** token, the one a
client would hold.

```python
key = make_token("user@example.com")                        # valid for 30 days
expired = make_token("user@example.com", expires_in=timedelta(seconds=-1))
revoked = make_token("user@example.com", revoked=True)
```

Use it instead of calling `/token/create` when a test is not about login. It is
faster and it isolates the test from the login route.

### `_clean_tables` (autouse)

You never request it. It empties every table after each integration test.

---

## 5. Helpers

### `bearer(key)` (in `tests/conftest.py`)

Builds the `Authorization` header for a protected route:

```python
from tests.conftest import bearer

client.get("/api/v1/decks", headers=bearer(key))
```

### `make_deck` (function)

Inserts a deck (with optional cards) for an **existing** account and returns its
`deck_id`. Cards are given as `(question, answer)` tuples; their `position` follows
the order of the list.

```python
deck_id = make_deck("user@example.com", name="Maths", cards=[("1+1 ?", "2")])
```

The owner must exist (foreign key on `deck.owner_email`): call `make_account` first.

### `make_card` (function)

Inserts one card in an existing deck and returns its `card_id`.

```python
card_id = make_card(deck_id, question="Q", answer="A", is_tolerant=False, position=3)
```

---

## 6. Anatomy of an integration test

Use the existing files as models. Test **classes** group the behaviour of one
route; **methods** name one precise expectation.

```python
"""POST /api/v1/token/revoke (logout)"""

from datetime import datetime, timezone

from database import db
from models import Token
from tests.conftest import bearer

REVOKE = "/api/v1/token/revoke"


class TestRevoke:
    def test_revokes_the_token_used_for_the_request(self, client, app, make_account, make_token):
        make_account()
        key = make_token("user@example.com")

        response = client.post(REVOKE, headers=bearer(key))

        assert response.status_code == 200
        assert response.get_json() == {"status": "ok"}
        with app.app_context():
            stored = db.session.scalars(db.select(Token)).one()
            assert stored.revoked_at is not None

    def test_requires_authentication(self, client, make_account):
        make_account()
        assert client.post(REVOKE).status_code == 401
```

Structure of a test, in four steps:

1. **Arrange**: create the data (`make_account`, `make_token`, `make_deck`...).
2. **Act**: make one request (`client.get/post/put/delete`).
3. **Assert on the response**: status code, JSON body, headers.
4. **Assert on the database** when the route changes state: open
   `app.app_context()` and query the row.

Keep one behaviour per test. If a test name needs "and", split it.

---

## 7. Assertions: what to check

For every route, check the parts of the contract that matter:

- **Status code**: `200`, `201`, `400`, `401`, `404`, `409`, `405`...
- **Body shape**: use `set(body) == {...}` to make sure no field is missing or leaked.
  The sign-up tests check that the password hash is never returned, this is the
  pattern to follow.
- **Error body**: every error is `{"error": "<Code>", "message": "..."}`. Check the
  `error` code, not the message text, so you can reword messages later.
- **Headers** when they matter: `WWW-Authenticate` on 401, `Cache-Control: no-store`
  on tokens.
- **Database state** after a write: the row exists, or is revoked, or is unchanged
  after a failed request.

Compare values with `datetime` tolerance when the server sets the time:

```python
assert abs(datetime.now(timezone.utc) - stored.revoked_at) < timedelta(minutes=1)
```

---

## 8. Checklist for a new route

For each new endpoint, write tests for these cases, in this order.

**Happy path**
- Returns the expected status and body.
- Writes the expected row(s), if it writes.
- Returns the right data when several users exist (no leaking between accounts).

**Input validation**
- Missing field → `400 InvalidRequest`.
- Wrong type (`int`, `null`, list) → `400`.
- Body that is not a JSON object → `400`.
- Business rule violated (invalid email, too long, too many cards...) → the specific error code.

**Security (only what is specific to the route)**
- Missing token → `401 MissingToken`.
- Invalid, expired or revoked token → `401 InvalidToken`.
- The caller cannot read or modify another user's resource. Use `404` for another
  user's id, so you do not reveal that the id exists.

**Method and existence**
- Wrong HTTP method → `405`.
- Unknown id → `404`.

Do **not** re-test the internals of `require_token` on every route. The decorator
is tested once in `test_auth.py`. Per route, test only that the route is protected
and that it filters by owner.

A parametrized guard that covers the whole API is worth adding once:

```python
@pytest.mark.parametrize("method, path", [
    ("get", "/api/v1/decks"),
    ("post", "/api/v1/decks"),
    ("post", "/api/v1/token/revoke"),
    # ... every protected route
])
def test_protected_routes_reject_anonymous(client, method, path):
    assert getattr(client, method)(path).status_code == 401
```

---

## 9. Useful patterns

### Parametrize repeated cases

```python
@pytest.mark.parametrize("missing", ["email", "password"])
def test_missing_field(self, client, make_account, missing):
    body = {k: v for k, v in {"email": "user@example.com", "password": "abc12"}.items() if k != missing}
    assert client.post(CREATE, json=body).status_code == 400
```

### Mock a collaborator to test a branch

Used in `test_token_routes.py` to check that unknown emails still pay the bcrypt cost:

```python
from unittest import mock
import routes.token as token_routes

with mock.patch.object(token_routes, "fake_verify") as fake:
    login(client, email="ghost@example.com")
fake.assert_called_once()
```

Patch where the name is **used** (`routes.token.fake_verify`), not where it is defined.

### Compare two responses to prove indistinguishability

```python
a = client.post(CREATE, json={...}).get_data()
b = client.post(CREATE, json={...}).get_data()
assert a == b
```

### Build a second app for a throw-away route

See `protected_client` in `test_auth.py`. Use it when you need a route that exists
only for the test.

---

## 10. Gotchas

- **Objects from a previous app context are detached.** Re-read them inside the
  context, or return plain values (ids, strings) from fixtures, as `make_deck`
  should do.
- **Forgetting `db.session.commit()`** in a fixture makes the route see nothing.
- **Writing to the DB in the test** requires `with app.app_context():`. Reading
  inside a route does not, because the test client creates its own context.
- **Stale cache of SQLAlchemy objects:** after a request changed a row, call
  `db.session.expire_all()` or query again before asserting.
- **`Refusing to run: database name ...`**: your `TEST_DATABASE_URL` does not end
  with `_test`. Fix the name, do not bypass the guard.
- **`Test PostgreSQL unreachable`**: the container is not running. Run
  `docker compose -f compose.test.yml up -d` and check `docker ps`.
- **Tests pass alone but fail together**: a test relies on state from another one.
  Make it create its own data.
- **Passwords:** the fixtures hash with bcrypt rounds=4 for speed. Do not use that
  cost for anything that tests the real hashing parameters.
- **Expired tokens:** use `expires_in=timedelta(seconds=-1)` rather than mocking
  the clock.

---

## 11. Quick template for a new test file

```python
"""GET /api/v1/decks — list the decks of the authenticated user."""

import pytest

from tests.conftest import bearer

URL = "/api/v1/decks"


@pytest.fixture
def user(make_account):
    return make_account()


class TestList:
    def test_returns_only_my_decks(self, client, user, make_account, make_token, make_deck):
        other = make_account(email="other@example.com")
        make_deck(user["email"], name="Maths")
        make_deck(other["email"], name="Secret")
        key = make_token(user["email"])

        response = client.get(URL, headers=bearer(key))

        assert response.status_code == 200
        assert [d["name"] for d in response.get_json()] == ["Maths"]

    def test_empty_list_when_the_user_has_no_deck(self, client, user, make_token):
        key = make_token(user["email"])

        response = client.get(URL, headers=bearer(key))

        assert response.status_code == 200
        assert response.get_json() == []

    def test_requires_authentication(self, client):
        assert client.get(URL).status_code == 401
```

Note: `make_deck` needs its owner account to exist, because of the foreign key
on `deck.owner_email`. Create it with `make_account` first.
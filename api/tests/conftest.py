"""Test setup.

Tests run against a real Postgres (the code relies on JSONB, advisory locks and
triggers) in a separate `<name>_test` database, which is rebuilt from the
Alembic migrations once per run. Object storage is in-memory and the Celery
queue is replaced by running the validation pipeline inline.
"""

import os

from sqlalchemy.engine import make_url

# Must happen before anything from `app` is imported, because settings are read at import time.
_main_url = make_url(os.environ["DATABASE_URL"])
_test_url = _main_url.set(database=f"{_main_url.database}_test")
os.environ["DATABASE_URL"] = _test_url.render_as_string(hide_password=False)
os.environ["STORAGE_BACKEND"] = "memory"
os.environ["JWT_SECRET"] = "test-secret-not-used-anywhere-else"

import csv  # noqa: E402
import io  # noqa: E402
import random  # noqa: E402

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

from app import worker  # noqa: E402
from app.apaar import verhoeff_check_digit  # noqa: E402
from app.db import SessionLocal, engine  # noqa: E402
from app.deps import CSRF_HEADER  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Institute, InstituteStatus, Programme, ProgrammeIntake, Role, User  # noqa: E402
from app.pipeline.parser import COLUMNS  # noqa: E402
from app.pipeline.runner import run_validation  # noqa: E402
from app.security import hash_password  # noqa: E402

YEAR = "2026-27"
PASSWORD = "correct-horse-battery"
# hashing is deliberately slow, so do it once
_PASSWORD_HASH = hash_password(PASSWORD)

_TABLES = (
    "verification_grants, upload_rows, students, uploads, programme_intakes, programmes,"
    " audit_log, users, institutes"
)


@pytest.fixture(scope="session", autouse=True)
def _database():
    assert _test_url.database.endswith("_test"), "refusing to wipe a non-test database"
    admin = create_engine(_main_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        exists = conn.scalar(
            text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": _test_url.database}
        )
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{_test_url.database}"'))
    admin.dispose()

    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    command.upgrade(Config("alembic.ini"), "head")
    yield
    engine.dispose()


@pytest.fixture(autouse=True)
def _clean_tables(_database):
    yield
    with engine.begin() as conn:
        # audit_log refuses TRUNCATE by design; only the test suite switches that off
        conn.execute(text("ALTER TABLE audit_log DISABLE TRIGGER USER"))
        conn.execute(text(f"TRUNCATE {_TABLES} RESTART IDENTITY CASCADE"))
        conn.execute(text("ALTER TABLE audit_log ENABLE TRIGGER USER"))
        conn.execute(text("REFRESH MATERIALIZED VIEW programme_enrolment"))


@pytest.fixture(autouse=True)
def _inline_queue(monkeypatch):
    monkeypatch.setattr(worker, "enqueue_validation", run_validation)


@pytest.fixture
def db():
    with SessionLocal() as session:
        yield session


def make_client() -> TestClient:
    # the header the web app sends on every request; see deps.require_csrf_header
    return TestClient(app, headers={CSRF_HEADER: "acadledger-tests"})


def login(email: str) -> TestClient:
    client = make_client()
    response = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return client


def create_user(db, email: str, role: Role, institute: Institute | None = None) -> User:
    user = User(
        email=email, password_hash=_PASSWORD_HASH, full_name=email, role=role, institute=institute
    )
    db.add(user)
    db.commit()
    return user


def create_institute(db, slug: str, programmes: dict[str, int]) -> Institute:
    """An active institute with an admin `admin@<slug>.example` and {code: approved intake}."""
    institute = Institute(
        aicte_id=f"1-{slug}",
        name=f"{slug} institute",
        state="Kerala",
        status=InstituteStatus.ACTIVE,
    )
    db.add(institute)
    for code, approved in programmes.items():
        programme = Programme(institute=institute, code=code, name=f"B.Tech {code}", level="ug")
        db.add(programme)
        db.add(ProgrammeIntake(programme=programme, academic_year=YEAR, approved_intake=approved))
    db.commit()
    create_user(db, f"admin@{slug}.example", Role.INSTITUTE_ADMIN, institute)
    return institute


@pytest.fixture
def officer(db) -> TestClient:
    create_user(db, "officer@aicte.example", Role.AICTE_OFFICER)
    return login("officer@aicte.example")


@pytest.fixture
def alpha(db) -> TestClient:
    """Logged-in admin of institute `alpha` (CSE intake 5, ECE intake 3)."""
    create_institute(db, "alpha", {"CSE": 5, "ECE": 3})
    return login("admin@alpha.example")


@pytest.fixture
def beta(db) -> TestClient:
    create_institute(db, "beta", {"CSE": 5})
    return login("admin@beta.example")


_rng = random.Random(7)


def apaar_id() -> str:
    """A fresh APAAR ID that the mock registry treats as registered."""
    body = str(_rng.randint(1, 9)) + "".join(str(_rng.randint(0, 9)) for _ in range(10))
    return body + verhoeff_check_digit(body)


def student(n: int, **overrides: str) -> dict[str, str]:
    row = {
        "apaar_id": apaar_id(),
        "full_name": f"Student {n}",
        "date_of_birth": "2007-04-18",
        "gender": "female",
        "programme_code": "CSE",
        "enrolment_no": f"ENR{n:06d}",
    }
    return row | overrides


def to_csv(rows: list[dict[str, str]]) -> bytes:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=COLUMNS)
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode()


def upload(client: TestClient, rows: list[dict[str, str]], filename: str = "students.csv") -> dict:
    response = client.post(
        "/api/v1/uploads",
        data={"academic_year": YEAR},
        files={"file": (filename, to_csv(rows), "text/csv")},
    )
    assert response.status_code == 202, response.text
    # the queue runs inline in tests, so the upload is already validated; re-read it
    return client.get(f"/api/v1/uploads/{response.json()['id']}").json()


def errors_by_row(client: TestClient, upload_id: str) -> dict[int, set[str]]:
    page = client.get(f"/api/v1/uploads/{upload_id}/rows", params={"limit": 500}).json()
    return {row["row_number"]: {e["code"] for e in row["errors"]} for row in page["items"]}

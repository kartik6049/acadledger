import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app import audit
from app.db import engine
from tests.conftest import student, upload


def test_actions_are_recorded_in_order_and_the_chain_verifies(alpha, officer):
    result = upload(alpha, [student(1)])
    alpha.post(f"/api/v1/uploads/{result['id']}/commit")

    page = officer.get("/api/v1/audit").json()
    actions = [entry["action"] for entry in reversed(page["items"])]
    assert actions == [
        "auth.login",  # alpha
        "auth.login",  # officer
        "upload.created",
        "upload.validated",
        "upload.committed",
    ]
    committed = page["items"][0]
    assert committed["payload"]["students_added"] == 1
    assert committed["prev_hash"] == page["items"][1]["hash"]

    report = officer.get("/api/v1/audit/verify").json()
    assert report == {"ok": True, "entries_checked": 5, "first_broken_id": None, "reason": None}


def test_first_entry_links_to_the_genesis_hash(db):
    entry = audit.append(db, action="test", entity_type="test", entity_id="1")
    db.commit()
    assert entry.prev_hash == audit.GENESIS_HASH


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE audit_log SET action = 'edited'",
        "DELETE FROM audit_log",
        "TRUNCATE audit_log",
    ],
)
def test_database_refuses_to_change_audit_entries(db, statement):
    audit.append(db, action="test", entity_type="test", entity_id="1")
    db.commit()

    with pytest.raises(DBAPIError, match="append-only"):
        db.execute(text(statement))
    db.rollback()

    assert audit.verify_chain(db).entries_checked == 1


def _tamper(statement: str) -> None:
    """Change the log the way someone with direct database access could."""
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE audit_log DISABLE TRIGGER USER"))
        conn.execute(text(statement))
        conn.execute(text("ALTER TABLE audit_log ENABLE TRIGGER USER"))


@pytest.mark.parametrize(
    ("statement", "broken_id"),
    [
        ("""UPDATE audit_log SET payload = '{"n": 99}' WHERE id = 2""", 2),
        ("DELETE FROM audit_log WHERE id = 2", 3),
    ],
)
def test_tampering_behind_the_triggers_is_detected(db, statement, broken_id):
    for n in range(4):
        audit.append(db, action="test", entity_type="test", entity_id=str(n), payload={"n": n})
    db.commit()
    assert audit.verify_chain(db).ok

    _tamper(statement)
    db.expire_all()

    report = audit.verify_chain(db)
    assert not report.ok
    assert report.first_broken_id == broken_id

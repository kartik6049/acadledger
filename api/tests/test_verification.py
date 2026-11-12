import time
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, update

from app.models import VerificationGrant
from tests.conftest import PASSWORD, login, make_client, student, upload

REFUSED = {"detail": "This verification link is invalid, expired or revoked"}


@pytest.fixture
def enrolled(alpha) -> dict:
    """One committed student of institute alpha, as the API returns it."""
    result = upload(alpha, [student(1, full_name="Asha Verma")])
    alpha.post(f"/api/v1/uploads/{result['id']}/commit")
    (record,) = alpha.get("/api/v1/students").json()["items"]
    return record


@pytest.fixture
def verifier(officer):
    created = officer.post(
        "/api/v1/verifiers",
        json={
            "full_name": "Hiring Team",
            "organisation": "Acme Corp",
            "email": "hr@acme.example",
            "password": PASSWORD,
        },
    )
    assert created.status_code == 201, created.text
    return login("hr@acme.example")


def create_link(client, student_id: str, **body) -> dict:
    response = client.post(f"/api/v1/students/{student_id}/verification-links", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def verify(client, token: str):
    return client.post("/api/v1/verify", json={"token": token})


def test_verifier_with_the_token_gets_the_record_and_the_lookup_is_audited(
    alpha, enrolled, verifier, officer
):
    link = create_link(alpha, enrolled["id"])

    started = time.perf_counter()
    response = verify(verifier, link["token"])
    elapsed = time.perf_counter() - started

    assert response.status_code == 200
    record = response.json()
    assert record["full_name"] == "Asha Verma"
    assert record["apaar_last4"] == enrolled["apaar_id"][-4:]
    assert record["institute_name"] == "alpha institute"
    assert record["programme_code"] == "CSE"
    # minimal disclosure: nothing beyond what confirms enrolment
    assert "date_of_birth" not in record and "apaar_id" not in record
    # success criterion: the verification API answers in under 500 ms
    assert elapsed < 0.5

    latest = officer.get("/api/v1/audit").json()["items"][0]
    assert latest["action"] == "verification.lookup"
    assert latest["entity_id"] == enrolled["id"]
    assert latest["payload"]["organisation"] == "Acme Corp"

    (listed,) = alpha.get(f"/api/v1/students/{enrolled['id']}/verification-links").json()
    assert listed["lookup_count"] == 1
    assert "token" not in listed


def test_only_a_hash_of_the_token_is_stored(alpha, enrolled, db):
    link = create_link(alpha, enrolled["id"])
    stored = db.scalar(select(VerificationGrant.token_hash))
    assert stored != link["token"] and len(stored) == 64


def test_unknown_revoked_and_expired_links_are_refused_identically(
    alpha, enrolled, verifier, officer, db
):
    revoked = create_link(alpha, enrolled["id"])
    expired = create_link(alpha, enrolled["id"])
    assert alpha.delete(f"/api/v1/verification-links/{revoked['id']}").status_code == 204
    db.execute(
        update(VerificationGrant)
        .where(VerificationGrant.id == expired["id"])
        .values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
    )
    db.commit()

    for token in ("x" * 43, revoked["token"], expired["token"]):
        response = verify(verifier, token)
        assert response.status_code == 404
        assert response.json() == REFUSED

    actions = [e["action"] for e in officer.get("/api/v1/audit").json()["items"][:3]]
    assert actions == ["verification.lookup_refused"] * 3


def test_verification_needs_an_authorised_verifier(alpha, enrolled):
    token = create_link(alpha, enrolled["id"])["token"]
    assert verify(make_client(), token).status_code == 401
    # an institute cannot use the endpoint to look students up
    assert verify(alpha, token).status_code == 403


def test_institute_can_only_issue_links_for_its_own_students(alpha, beta, enrolled, verifier):
    path = f"/api/v1/students/{enrolled['id']}/verification-links"
    assert beta.post(path, json={}).status_code == 404
    assert beta.get(path).status_code == 404
    link = create_link(alpha, enrolled["id"])
    assert beta.delete(f"/api/v1/verification-links/{link['id']}").status_code == 404
    assert verify(verifier, link["token"]).status_code == 200


def test_only_officers_manage_verifiers(alpha, officer, verifier):
    assert alpha.get("/api/v1/verifiers").status_code == 403
    assert verifier.get("/api/v1/verifiers").status_code == 403
    listed = officer.get("/api/v1/verifiers").json()
    assert [(v["email"], v["organisation"]) for v in listed] == [("hr@acme.example", "Acme Corp")]
    duplicate = officer.post(
        "/api/v1/verifiers",
        json={
            "full_name": "Again",
            "organisation": "Acme Corp",
            "email": "HR@acme.example",
            "password": PASSWORD,
        },
    )
    assert duplicate.status_code == 409


def test_students_can_be_searched(alpha):
    target = student(1, full_name="Asha Verma")
    result = upload(alpha, [target, student(2, full_name="Ravi Kumar")])
    alpha.post(f"/api/v1/uploads/{result['id']}/commit")

    def names(q):
        page = alpha.get("/api/v1/students", params={"q": q}).json()
        return [s["full_name"] for s in page["items"]]

    assert names("verma") == ["Asha Verma"]
    assert names(target["apaar_id"]) == ["Asha Verma"]
    assert names("ENR000002") == ["Ravi Kumar"]
    assert names("100%") == []

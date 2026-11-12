from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.main import app
from app.models import Role, UploadRow, User
from app.routers.auth import MAX_FAILED_LOGINS
from tests.conftest import PASSWORD, create_user, login, make_client, student, upload

EMAIL = "officer@aicte.example"


def attempt(client, password):
    return client.post("/api/v1/auth/login", json={"email": EMAIL, "password": password})


def test_repeated_wrong_passwords_lock_the_account(db):
    create_user(db, EMAIL, Role.AICTE_OFFICER)
    client = make_client()

    for _ in range(MAX_FAILED_LOGINS):
        assert attempt(client, "wrong-password").status_code == 401

    # even the right password is refused while the lock lasts
    locked = attempt(client, PASSWORD)
    assert locked.status_code == 429
    assert "Try again in" in locked.json()["detail"]

    # ...and works again once it has passed
    user = db.scalar(select(User).where(User.email == EMAIL))
    user.locked_until = None
    db.commit()
    assert attempt(client, PASSWORD).status_code == 200


def test_a_successful_login_resets_the_count(db):
    create_user(db, EMAIL, Role.AICTE_OFFICER)
    client = make_client()

    for _ in range(MAX_FAILED_LOGINS - 1):
        attempt(client, "wrong-password")
    assert attempt(client, PASSWORD).status_code == 200
    for _ in range(MAX_FAILED_LOGINS - 1):
        attempt(client, "wrong-password")

    assert attempt(client, PASSWORD).status_code == 200


def test_cookie_session_cannot_change_anything_without_the_csrf_header(alpha):
    # the same signed-in session, as a form on another site would use it: cookie, no header
    forged = TestClient(app, cookies=dict(alpha.cookies))

    assert forged.get("/api/v1/auth/me").status_code == 200
    assert forged.post("/api/v1/auth/logout").status_code == 403
    changed = forged.post(
        "/api/v1/auth/change-password",
        json={"current_password": PASSWORD, "new_password": "attacker-chosen-1"},
    )
    assert changed.status_code == 403
    assert login("admin@alpha.example")  # the password is unchanged


def test_bearer_token_requests_do_not_need_the_csrf_header(db):
    create_user(db, EMAIL, Role.AICTE_OFFICER)
    token = attempt(make_client(), PASSWORD).json()["access_token"]

    response = TestClient(app).post(
        "/api/v1/verifiers",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "full_name": "Script User",
            "organisation": "Acme",
            "email": "s@acme.example",
            "password": PASSWORD,
        },
    )

    assert response.status_code == 201


def test_user_can_change_their_own_password(db):
    create_user(db, EMAIL, Role.AICTE_OFFICER)
    client = login(EMAIL)
    path = "/api/v1/auth/change-password"

    wrong = client.post(path, json={"current_password": "nope", "new_password": "brand-new-pass-1"})
    assert wrong.status_code == 400
    short = client.post(path, json={"current_password": PASSWORD, "new_password": "short"})
    assert short.status_code == 422
    same = client.post(path, json={"current_password": PASSWORD, "new_password": PASSWORD})
    assert same.status_code == 400

    changed = client.post(
        path, json={"current_password": PASSWORD, "new_password": "brand-new-pass-1"}
    )
    assert changed.status_code == 204
    assert attempt(make_client(), PASSWORD).status_code == 401
    assert attempt(make_client(), "brand-new-pass-1").status_code == 200


def test_staging_rows_are_deleted_once_an_upload_is_committed(alpha, db):
    result = upload(alpha, [student(1), student(2)])
    assert db.scalar(select(func.count()).select_from(UploadRow)) == 2

    alpha.post(f"/api/v1/uploads/{result['id']}/commit")

    assert db.scalar(select(func.count()).select_from(UploadRow)) == 0
    # the upload still reports what it contained
    after = alpha.get(f"/api/v1/uploads/{result['id']}").json()
    assert (after["status"], after["total_rows"]) == ("committed", 2)

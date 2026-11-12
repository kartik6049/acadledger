from app.models import Role
from tests.conftest import PASSWORD, create_user, login, make_client


def test_login_sets_a_session_and_me_returns_the_user(db):
    create_user(db, "officer@aicte.example", Role.AICTE_OFFICER)
    client = make_client()

    response = client.post(
        "/api/v1/auth/login", json={"email": "Officer@AICTE.example", "password": PASSWORD}
    )

    assert response.status_code == 200
    assert response.json()["user"]["role"] == "aicte_officer"
    assert "httponly" in response.headers["set-cookie"].lower()
    assert client.get("/api/v1/auth/me").json()["email"] == "officer@aicte.example"


def test_bearer_token_works_without_the_cookie(db):
    create_user(db, "officer@aicte.example", Role.AICTE_OFFICER)
    token = (
        make_client()
        .post("/api/v1/auth/login", json={"email": "officer@aicte.example", "password": PASSWORD})
        .json()["access_token"]
    )

    response = make_client().get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200


def test_wrong_password_and_unknown_email_look_the_same(db):
    create_user(db, "officer@aicte.example", Role.AICTE_OFFICER)
    client = make_client()

    wrong = client.post(
        "/api/v1/auth/login", json={"email": "officer@aicte.example", "password": "nope-nope-nope"}
    )
    unknown = client.post(
        "/api/v1/auth/login", json={"email": "ghost@aicte.example", "password": PASSWORD}
    )

    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


def test_requests_without_or_with_a_bad_token_are_rejected():
    client = make_client()
    assert client.get("/api/v1/auth/me").status_code == 401
    assert (
        client.get("/api/v1/auth/me", headers={"Authorization": "Bearer garbage"}).status_code
        == 401
    )


def test_deactivated_user_loses_access(db):
    user = create_user(db, "officer@aicte.example", Role.AICTE_OFFICER)
    client = login("officer@aicte.example")
    user.is_active = False
    db.commit()

    assert client.get("/api/v1/auth/me").status_code == 401


def test_logout_clears_the_session(db):
    create_user(db, "officer@aicte.example", Role.AICTE_OFFICER)
    client = login("officer@aicte.example")

    assert client.post("/api/v1/auth/logout").status_code == 204
    assert client.get("/api/v1/auth/me").status_code == 401


def test_institute_admin_cannot_use_officer_endpoints(alpha):
    assert alpha.get("/api/v1/institutes").status_code == 403
    assert alpha.get("/api/v1/audit").status_code == 403
    assert alpha.get("/api/v1/audit/verify").status_code == 403

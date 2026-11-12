from tests.conftest import YEAR, login, make_client, student, to_csv

REGISTRATION = {
    "aicte_id": "1-4455667",
    "name": "Narmada Institute of Technology",
    "state": "Gujarat",
    "admin": {
        "full_name": "Data Entry Admin",
        "email": "admin@narmada.example",
        "password": "correct-horse-battery",
    },
}


def post_file(client):
    return client.post(
        "/api/v1/uploads",
        data={"academic_year": YEAR},
        files={"file": ("s.csv", to_csv([student(1)]), "text/csv")},
    )


def test_institute_is_pending_until_an_officer_approves_it(officer):
    registered = make_client().post("/api/v1/institutes/register", json=REGISTRATION)
    assert registered.status_code == 201
    institute = registered.json()
    assert institute["status"] == "pending"

    admin = login("admin@narmada.example")
    assert admin.get("/api/v1/institutes/me").json()["status"] == "pending"
    assert post_file(admin).status_code == 403

    pending = officer.get("/api/v1/institutes", params={"status": "pending"}).json()
    assert [i["id"] for i in pending] == [institute["id"]]
    approved = officer.post(
        f"/api/v1/institutes/{institute['id']}/status", json={"status": "active"}
    )
    assert approved.json()["status"] == "active"

    assert post_file(admin).status_code == 202


def test_duplicate_aicte_id_or_email_is_refused():
    client = make_client()
    assert client.post("/api/v1/institutes/register", json=REGISTRATION).status_code == 201

    same_id = REGISTRATION | {"admin": REGISTRATION["admin"] | {"email": "other@narmada.example"}}
    same_email = REGISTRATION | {"aicte_id": "1-9999999"}

    assert client.post("/api/v1/institutes/register", json=same_id).status_code == 409
    assert client.post("/api/v1/institutes/register", json=same_email).status_code == 409


def test_short_password_is_refused():
    body = REGISTRATION | {"admin": REGISTRATION["admin"] | {"password": "short"}}
    assert make_client().post("/api/v1/institutes/register", json=body).status_code == 422


def test_officer_manages_programmes_and_intake(officer, alpha):
    institute_id = alpha.get("/api/v1/institutes/me").json()["id"]

    created = officer.post(
        f"/api/v1/institutes/{institute_id}/programmes",
        json={"code": "me", "name": "B.Tech Mechanical", "level": "ug"},
    )
    assert created.status_code == 201
    programme = created.json()
    assert programme["code"] == "ME"

    updated = officer.put(
        f"/api/v1/programmes/{programme['id']}/intakes/{YEAR}", json={"approved_intake": 60}
    )
    assert updated.json()["intakes"] == [{"academic_year": YEAR, "approved_intake": 60}]

    # the institute can read its programmes but not change them
    listed = alpha.get(f"/api/v1/institutes/{institute_id}/programmes").json()
    assert [p["code"] for p in listed] == ["CSE", "ECE", "ME"]
    forbidden = alpha.put(
        f"/api/v1/programmes/{programme['id']}/intakes/{YEAR}", json={"approved_intake": 999}
    )
    assert forbidden.status_code == 403


def test_institute_cannot_see_another_institutes_programmes(alpha, beta):
    alpha_id = alpha.get("/api/v1/institutes/me").json()["id"]
    assert beta.get(f"/api/v1/institutes/{alpha_id}/programmes").status_code == 404

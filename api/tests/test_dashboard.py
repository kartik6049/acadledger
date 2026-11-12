from tests.conftest import YEAR, student, upload


def commit_students(client, numbers, **overrides):
    result = upload(client, [student(n, **overrides) for n in numbers])
    assert client.post(f"/api/v1/uploads/{result['id']}/commit").status_code == 200


def summary(officer):
    return officer.get("/api/v1/dashboard/summary", params={"academic_year": YEAR}).json()


def intake(officer, **params):
    response = officer.get("/api/v1/dashboard/intake", params={"academic_year": YEAR, **params})
    return response.json()


def test_dashboard_flags_every_programme_over_its_approved_intake(alpha, beta, officer):
    # approved intake: alpha CSE 5 and ECE 3, beta CSE 5
    commit_students(alpha, range(1, 5))
    assert summary(officer)["programmes_over_intake"] == 0

    commit_students(alpha, range(5, 8))  # alpha CSE: 7 of 5
    commit_students(alpha, range(20, 24), programme_code="ECE")  # alpha ECE: 4 of 3
    commit_students(beta, range(50, 55))  # beta CSE: 5 of 5, full but not over

    assert summary(officer) == {
        "academic_year": YEAR,
        "institutes_active": 2,
        "institutes_pending": 0,
        "programmes": 3,
        "approved_intake": 13,
        "enrolled": 16,
        "programmes_over_intake": 2,
        "excess_students": 3,
    }

    page = intake(officer)
    assert page["total"] == 3
    assert [
        (r["institute_name"], r["programme_code"], r["enrolled"], r["excess"])
        for r in page["items"]
    ] == [
        ("alpha institute", "CSE", 7, 2),
        ("alpha institute", "ECE", 4, 1),
        ("beta institute", "CSE", 5, 0),
    ]

    flagged = intake(officer, only_excess=True)
    assert flagged["total"] == 2
    assert {r["programme_code"] for r in flagged["items"]} == {"CSE", "ECE"}


def test_raising_the_approved_intake_clears_the_flag(alpha, officer):
    commit_students(alpha, range(1, 8))  # CSE: 7 of 5
    (row,) = intake(officer, only_excess=True)["items"]
    institute_id = row["institute_id"]
    programmes = officer.get(f"/api/v1/institutes/{institute_id}/programmes").json()
    cse = next(p for p in programmes if p["code"] == "CSE")

    officer.put(f"/api/v1/programmes/{cse['id']}/intakes/{YEAR}", json={"approved_intake": 10})

    assert intake(officer, only_excess=True) == {"total": 0, "items": []}
    assert summary(officer)["approved_intake"] == 13


def test_other_years_are_not_mixed_in(alpha, officer):
    commit_students(alpha, range(1, 8))
    response = officer.get("/api/v1/dashboard/summary", params={"academic_year": "2025-26"})
    assert response.json()["enrolled"] == 0
    assert response.json()["programmes"] == 0


def test_dashboard_is_for_officers_only(alpha):
    params = {"academic_year": YEAR}
    assert alpha.get("/api/v1/dashboard/summary", params=params).status_code == 403
    assert alpha.get("/api/v1/dashboard/intake", params=params).status_code == 403

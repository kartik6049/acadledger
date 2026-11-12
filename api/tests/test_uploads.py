import time

import pytest
from sqlalchemy import func, select

from app.models import Student
from tests.conftest import YEAR, apaar_id, errors_by_row, student, to_csv, upload


def commit(client, upload_id):
    return client.post(f"/api/v1/uploads/{upload_id}/commit")


def test_clean_file_validates_and_commits(alpha, db):
    rows = [student(1), student(2, programme_code="ECE")]

    result = upload(alpha, rows)
    assert result["status"] == "validated"
    assert (result["total_rows"], result["valid_rows"], result["error_rows"]) == (2, 2, 0)

    committed = commit(alpha, result["id"])
    assert committed.status_code == 200
    assert committed.json()["status"] == "committed"
    assert db.scalar(select(func.count()).select_from(Student)) == 2

    listed = alpha.get("/api/v1/students").json()
    assert listed["total"] == 2
    assert {s["apaar_id"] for s in listed["items"]} == {r["apaar_id"] for r in rows}

    # committing twice must not add the students twice
    assert commit(alpha, result["id"]).status_code == 409
    assert db.scalar(select(func.count()).select_from(Student)) == 2


def test_every_kind_of_row_error_is_reported_against_its_row(alpha):
    shared = apaar_id()
    registered = apaar_id()
    unregistered = registered[:-1] + str((int(registered[-1]) + 1) % 10)
    rows = [
        student(1),  # row 2: fine
        student(2, apaar_id="12345"),  # row 3
        student(3, apaar_id=unregistered),  # row 4
        student(4, full_name=""),  # row 5
        student(5, date_of_birth="31/02/2007"),  # row 6
        student(6, date_of_birth="2020-01-01"),  # row 7: a six-year-old
        student(7, gender="unknown"),  # row 8
        student(8, programme_code="XYZ"),  # row 9
        student(9, apaar_id=shared),  # row 10
        student(10, apaar_id=shared),  # row 11
        student(11, enrolment_no="ENR000001"),  # row 12: same enrolment_no as row 2
        student(12, apaar_id="", gender="x", programme_code="XYZ"),  # row 13: three problems
    ]

    result = upload(alpha, rows)

    assert result["status"] == "validated"
    assert errors_by_row(alpha, result["id"]) == {
        2: {"DUPLICATE_ENROLMENT_IN_FILE"},
        3: {"INVALID_APAAR_FORMAT"},
        4: {"APAAR_NOT_FOUND"},
        5: {"REQUIRED"},
        6: {"INVALID_DATE"},
        7: {"DOB_OUT_OF_RANGE"},
        8: {"INVALID_GENDER"},
        9: {"UNKNOWN_PROGRAMME"},
        10: {"DUPLICATE_APAAR_IN_FILE"},
        11: {"DUPLICATE_APAAR_IN_FILE"},
        12: {"DUPLICATE_ENROLMENT_IN_FILE"},
        13: {"REQUIRED", "INVALID_GENDER", "UNKNOWN_PROGRAMME"},
    }
    assert result["error_rows"] == 12
    assert result["summary"]["errors_by_stage"]["schema"] == 6

    # nothing can be committed while any row has errors
    assert commit(alpha, result["id"]).status_code == 409


def test_values_are_normalised_before_they_are_stored(alpha):
    raw = apaar_id()
    spaced = f"{raw[:4]} {raw[4:8]}-{raw[8:]}"
    rows = [
        student(
            1,
            apaar_id=spaced,
            full_name="  Asha   Verma ",
            date_of_birth="18/04/2007",
            gender="F",
            programme_code="cse",
        )
    ]

    result = upload(alpha, rows)
    assert result["error_rows"] == 0
    commit(alpha, result["id"])

    (stored,) = alpha.get("/api/v1/students").json()["items"]
    assert stored["apaar_id"] == raw
    assert stored["full_name"] == "Asha Verma"
    assert stored["date_of_birth"] == "2007-04-18"
    assert stored["gender"] == "female"


def test_error_report_csv_lists_each_error_and_defuses_formulas(alpha):
    rows = [student(1, apaar_id="=1+1"), student(2, gender="x")]
    result = upload(alpha, rows)

    report = alpha.get(f"/api/v1/uploads/{result['id']}/errors.csv")

    assert report.status_code == 200
    assert report.headers["content-type"].startswith("text/csv")
    lines = report.text.strip().splitlines()
    assert lines[0] == "row_number,field,value,code,message,stage"
    assert lines[1].startswith("2,apaar_id,'=1+1,INVALID_APAAR_FORMAT,")
    assert lines[2].startswith("3,gender,x,INVALID_GENDER,")


def test_duplicate_apaar_id_in_another_institute_is_caught(alpha, beta):
    first = student(1)
    done = upload(alpha, [first])
    assert commit(alpha, done["id"]).status_code == 200

    # beta tries to enrol the same person, under its own enrolment number
    result = upload(beta, [student(50, apaar_id=first["apaar_id"]), student(51)])

    assert errors_by_row(beta, result["id"]) == {2: {"APAAR_AT_ANOTHER_INSTITUTE"}}
    assert commit(beta, result["id"]).status_code == 409
    assert beta.get("/api/v1/students").json()["total"] == 0


def test_reuploading_committed_students_is_caught(alpha):
    first = student(1)
    commit(alpha, upload(alpha, [first])["id"])

    result = upload(alpha, [first])

    assert errors_by_row(alpha, result["id"]) == {
        2: {"APAAR_ALREADY_ENROLLED", "ENROLMENT_NO_EXISTS"}
    }


def test_duplicate_that_appears_between_validation_and_commit_is_caught(alpha, beta, db):
    contested = apaar_id()
    alpha_upload = upload(alpha, [student(1, apaar_id=contested), student(2)])
    beta_upload = upload(beta, [student(50, apaar_id=contested)])
    assert alpha_upload["error_rows"] == beta_upload["error_rows"] == 0

    assert commit(beta, beta_upload["id"]).status_code == 200
    late = commit(alpha, alpha_upload["id"])

    assert late.status_code == 409
    assert errors_by_row(alpha, alpha_upload["id"]) == {2: {"APAAR_AT_ANOTHER_INSTITUTE"}}
    assert alpha.get(f"/api/v1/uploads/{alpha_upload['id']}").json()["error_rows"] == 1
    assert db.scalar(select(func.count()).select_from(Student)) == 1


def test_enrolment_beyond_approved_intake_is_flagged_not_rejected(alpha):
    # alpha's approved intake: CSE 5, ECE 3
    first = upload(alpha, [student(n) for n in range(1, 5)])
    assert first["summary"]["intake"] == [
        {
            "programme_code": "CSE",
            "programme_name": "B.Tech CSE",
            "approved_intake": 5,
            "already_enrolled": 0,
            "in_this_upload": 4,
            "excess": 0,
        }
    ]
    commit(alpha, first["id"])

    second = upload(
        alpha, [student(n) for n in range(10, 13)] + [student(20, programme_code="ECE")]
    )

    assert second["error_rows"] == 0
    by_code = {f["programme_code"]: f for f in second["summary"]["intake"]}
    assert by_code["CSE"]["already_enrolled"] == 4
    assert by_code["CSE"]["excess"] == 2
    assert by_code["ECE"]["excess"] == 0
    assert commit(alpha, second["id"]).status_code == 200


def test_programme_without_intake_for_the_year_is_rejected(alpha):
    response = alpha.post(
        "/api/v1/uploads",
        data={"academic_year": "2025-26"},
        files={"file": ("s.csv", to_csv([student(1)]), "text/csv")},
    )
    assert response.status_code == 202
    assert errors_by_row(alpha, response.json()["id"]) == {2: {"NO_APPROVED_INTAKE"}}


def test_unreadable_file_fails_with_a_reason(alpha):
    response = alpha.post(
        "/api/v1/uploads",
        data={"academic_year": YEAR},
        files={"file": ("s.csv", b"apaar_id,full_name\n1,2\n", "text/csv")},
    )
    result = alpha.get(f"/api/v1/uploads/{response.json()['id']}").json()

    assert result["status"] == "failed"
    assert "Missing column(s): date_of_birth" in result["failure_reason"]


@pytest.mark.parametrize(
    ("filename", "content", "year", "expected"),
    [
        ("s.pdf", b"x", YEAR, 415),
        ("s.csv", b"", YEAR, 400),
        ("s.csv", b"x", "2026-28", 422),
    ],
)
def test_bad_upload_requests_are_refused(alpha, filename, content, year, expected):
    response = alpha.post(
        "/api/v1/uploads",
        data={"academic_year": year},
        files={"file": (filename, content, "application/octet-stream")},
    )
    assert response.status_code == expected


def test_uploads_are_private_to_their_institute(alpha, beta, officer):
    result = upload(alpha, [student(1)])
    path = f"/api/v1/uploads/{result['id']}"

    assert beta.get(path).status_code == 404
    assert beta.get(f"{path}/rows").status_code == 404
    assert beta.get(f"{path}/errors.csv").status_code == 404
    assert beta.post(f"{path}/commit").status_code == 404
    assert beta.get("/api/v1/uploads").json() == []

    # the regulator can read any upload but cannot commit on an institute's behalf
    assert officer.get(path).status_code == 200
    assert officer.post(f"{path}/commit").status_code == 403


def test_template_has_the_expected_columns(alpha):
    template = alpha.get("/api/v1/uploads/template.csv")
    assert template.text.splitlines()[0] == (
        "apaar_id,full_name,date_of_birth,gender,programme_code,enrolment_no"
    )


@pytest.mark.slow
def test_ten_thousand_rows_validate_well_inside_a_minute(alpha):
    """Success criterion: 10,000 rows validated in under 60 s with a row-level report."""
    rows = [student(n) for n in range(1, 10_001)]
    rows[4999]["apaar_id"] = "123"

    started = time.perf_counter()
    result = upload(alpha, rows)
    elapsed = time.perf_counter() - started

    assert result["status"] == "validated"
    assert (result["total_rows"], result["error_rows"]) == (10_000, 1)
    assert errors_by_row(alpha, result["id"]) == {5001: {"INVALID_APAAR_FORMAT"}}
    assert elapsed < 60

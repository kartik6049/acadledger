"""The validation stages, run in order over every row of an upload.

A row keeps going through later stages after it fails one, so a single pass
reports everything wrong with it. A later stage only skips the specific field
an earlier stage already rejected.

Database checks are done with one query per check, never one per row; that is
what keeps a 10,000-row file well inside the time budget.
"""

import re
import uuid
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import String, any_, func, literal, select
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Session

from app.apaar import ApaarClient, ApaarStatus
from app.models import Programme, ProgrammeIntake, Student
from app.pipeline.parser import COLUMNS, ParsedRow

STAGES = ("schema", "apaar_format", "apaar_registry", "duplicates", "intake")

_APAAR_RE = re.compile(r"\d{12}")
_ISO_DATE_RE = re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2})")  # YYYY-MM-DD
_INDIAN_DATE_RE = re.compile(r"(\d{1,2})[-/](\d{1,2})[-/](\d{4})")  # DD-MM-YYYY or DD/MM/YYYY
_GENDERS = {
    "m": "male",
    "male": "male",
    "f": "female",
    "female": "female",
    "o": "other",
    "other": "other",
    "transgender": "other",
}
_MAX_LENGTH = {"full_name": 200, "programme_code": 20, "enrolment_no": 40}
_MIN_AGE, _MAX_AGE = 14, 100


@dataclass
class RowState:
    row_number: int
    data: dict[str, str]
    errors: list[dict[str, str]] = field(default_factory=list)
    bad_fields: set[str] = field(default_factory=set)

    def fail(self, stage: str, column: str, code: str, message: str) -> None:
        self.errors.append({"stage": stage, "field": column, "code": code, "message": message})
        self.bad_fields.add(column)

    def usable(self, column: str) -> bool:
        return column not in self.bad_fields

    @property
    def is_valid(self) -> bool:
        return not self.errors


@dataclass
class Context:
    db: Session
    institute_id: uuid.UUID
    academic_year: str
    apaar: ApaarClient
    today: date


def run_stages(parsed: Sequence[ParsedRow], ctx: Context) -> tuple[list[RowState], dict]:
    """Validate all rows. Returns the per-row results and an upload-level summary."""
    rows = [RowState(p.row_number, dict(p.values)) for p in parsed]
    check_schema(rows, ctx)
    check_apaar_format(rows)
    check_apaar_registry(rows, ctx)
    check_duplicates(rows, ctx)
    intake = check_intake(rows, ctx)

    by_code = Counter(e["code"] for row in rows for e in row.errors)
    by_stage = Counter(e["stage"] for row in rows for e in row.errors)
    summary = {
        "errors_by_code": dict(by_code),
        "errors_by_stage": {stage: by_stage.get(stage, 0) for stage in STAGES},
        "intake": intake,
    }
    return rows, summary


# --- stage 1: schema ------------------------------------------------------------------------


def _parse_date(value: str) -> date | None:
    # regexes rather than strptime, which dominated this stage on large files
    try:
        if match := _ISO_DATE_RE.fullmatch(value):
            return date(int(match[1]), int(match[2]), int(match[3]))
        if match := _INDIAN_DATE_RE.fullmatch(value):
            return date(int(match[3]), int(match[2]), int(match[1]))
    except ValueError:  # right shape, impossible date (31/02/2007)
        pass
    return None


def _age(born: date, today: date) -> int:
    return today.year - born.year - ((today.month, today.day) < (born.month, born.day))


def check_schema(rows: Iterable[RowState], ctx: Context) -> None:
    for row in rows:
        d = row.data
        # normalise first, so "1234 5678 9012" and " cse " are not rejected for formatting
        d["apaar_id"] = re.sub(r"[\s-]", "", d["apaar_id"])
        d["full_name"] = " ".join(d["full_name"].split())
        d["programme_code"] = d["programme_code"].upper()

        for column in COLUMNS:
            if not d[column]:
                row.fail("schema", column, "REQUIRED", f"{column} is required")
        for column, limit in _MAX_LENGTH.items():
            if len(d[column]) > limit:
                row.fail(
                    "schema", column, "TOO_LONG", f"{column} is longer than {limit} characters"
                )

        if d["date_of_birth"]:
            born = _parse_date(d["date_of_birth"])
            if born is None:
                row.fail(
                    "schema",
                    "date_of_birth",
                    "INVALID_DATE",
                    "date_of_birth must be YYYY-MM-DD or DD-MM-YYYY",
                )
            elif not _MIN_AGE <= _age(born, ctx.today) <= _MAX_AGE:
                row.fail(
                    "schema",
                    "date_of_birth",
                    "DOB_OUT_OF_RANGE",
                    f"date_of_birth gives an age outside {_MIN_AGE}-{_MAX_AGE} years",
                )
            else:
                d["date_of_birth"] = born.isoformat()

        if d["gender"]:
            gender = _GENDERS.get(d["gender"].lower())
            if gender is None:
                row.fail(
                    "schema", "gender", "INVALID_GENDER", "gender must be male, female or other"
                )
            else:
                d["gender"] = gender


# --- stage 2: APAAR format ------------------------------------------------------------------


def check_apaar_format(rows: Iterable[RowState]) -> None:
    for row in rows:
        if row.usable("apaar_id") and not _APAAR_RE.fullmatch(row.data["apaar_id"]):
            row.fail(
                "apaar_format",
                "apaar_id",
                "INVALID_APAAR_FORMAT",
                "apaar_id must be exactly 12 digits",
            )


# --- stage 3: APAAR registry ----------------------------------------------------------------


def check_apaar_registry(rows: Iterable[RowState], ctx: Context) -> None:
    candidates = [row for row in rows if row.usable("apaar_id")]
    results = ctx.apaar.lookup_many(sorted({row.data["apaar_id"] for row in candidates}))
    for row in candidates:
        if results[row.data["apaar_id"]].status is not ApaarStatus.FOUND:
            row.fail(
                "apaar_registry",
                "apaar_id",
                "APAAR_NOT_FOUND",
                "apaar_id is not registered with APAAR",
            )


# --- stage 4: duplicates --------------------------------------------------------------------


def _any_of(values: Iterable[str]):
    """`column = ANY(array)`: all values travel as one array parameter.

    `column IN (...)` would send one parameter per value, which is slow to build
    for a whole file's worth and capped at 65,535 parameters per query.
    """
    return any_(literal(sorted(values), ARRAY(String)))


def _flag_repeats_in_file(rows: Iterable[RowState], column: str, code: str) -> None:
    seen: dict[str, list[RowState]] = defaultdict(list)
    for row in rows:
        if row.usable(column):
            seen[row.data[column]].append(row)
    for group in seen.values():
        if len(group) < 2:
            continue
        # Flag every occurrence: we cannot know which of the rows is the right one.
        for row in group:
            others = [str(other.row_number) for other in group if other is not row]
            listed = ", ".join(others[:5]) + (" ..." if len(others) > 5 else "")
            row.fail("duplicates", column, code, f"same {column} as row {listed} in this file")


def check_duplicates(rows: Sequence[RowState], ctx: Context) -> None:
    _flag_repeats_in_file(rows, "apaar_id", "DUPLICATE_APAAR_IN_FILE")
    _flag_repeats_in_file(rows, "enrolment_no", "DUPLICATE_ENROLMENT_IN_FILE")

    # against the central repository: one APAAR ID may exist only once, in any institute
    apaar_ids = {row.data["apaar_id"] for row in rows if row.usable("apaar_id")}
    owner: dict[str, uuid.UUID] = dict(
        ctx.db.execute(
            select(Student.apaar_id, Student.institute_id).where(
                Student.apaar_id == _any_of(apaar_ids)
            )
        ).all()
    )
    for row in rows:
        if not row.usable("apaar_id") or row.data["apaar_id"] not in owner:
            continue
        if owner[row.data["apaar_id"]] == ctx.institute_id:
            row.fail(
                "duplicates",
                "apaar_id",
                "APAAR_ALREADY_ENROLLED",
                "this APAAR ID is already in your institute's records",
            )
        else:
            # deliberately does not say which institute: that is for AICTE to see, not a peer
            row.fail(
                "duplicates",
                "apaar_id",
                "APAAR_AT_ANOTHER_INSTITUTE",
                "this APAAR ID is already enrolled at another institute",
            )

    enrolment_nos = {row.data["enrolment_no"] for row in rows if row.usable("enrolment_no")}
    taken = set(
        ctx.db.scalars(
            select(Student.enrolment_no).where(
                Student.institute_id == ctx.institute_id,
                Student.enrolment_no == _any_of(enrolment_nos),
            )
        )
    )
    for row in rows:
        if row.usable("enrolment_no") and row.data["enrolment_no"] in taken:
            row.fail(
                "duplicates",
                "enrolment_no",
                "ENROLMENT_NO_EXISTS",
                "this enrolment_no is already in your institute's records",
            )


# --- stage 5: programme and approved intake -------------------------------------------------


def check_intake(rows: Sequence[RowState], ctx: Context) -> list[dict]:
    """Reject rows for programmes AICTE has not approved, and measure enrolment against intake.

    Exceeding the approved intake does not reject rows. The data is accepted and the
    excess is reported, because surfacing it to AICTE is the point of the platform.
    """
    programmes = {
        p.code: p
        for p in ctx.db.scalars(select(Programme).where(Programme.institute_id == ctx.institute_id))
    }
    approved = dict(
        ctx.db.execute(
            select(ProgrammeIntake.programme_id, ProgrammeIntake.approved_intake)
            .join(Programme)
            .where(
                Programme.institute_id == ctx.institute_id,
                ProgrammeIntake.academic_year == ctx.academic_year,
            )
        ).all()
    )
    known_codes = ", ".join(sorted(programmes)[:10]) or "none yet"

    for row in rows:
        if not row.usable("programme_code"):
            continue
        programme = programmes.get(row.data["programme_code"])
        if programme is None:
            row.fail(
                "intake",
                "programme_code",
                "UNKNOWN_PROGRAMME",
                f"programme_code is not one of your approved programmes ({known_codes})",
            )
        elif programme.id not in approved:
            row.fail(
                "intake",
                "programme_code",
                "NO_APPROVED_INTAKE",
                f"this programme has no approved intake for {ctx.academic_year}",
            )

    in_upload = Counter(row.data["programme_code"] for row in rows if row.is_valid)
    if not in_upload:
        return []
    enrolled = dict(
        ctx.db.execute(
            select(Student.programme_id, func.count())
            .where(
                Student.institute_id == ctx.institute_id,
                Student.academic_year == ctx.academic_year,
            )
            .group_by(Student.programme_id)
        ).all()
    )
    findings = []
    for code in sorted(in_upload):
        programme = programmes[code]
        already = enrolled.get(programme.id, 0)
        total = already + in_upload[code]
        findings.append(
            {
                "programme_code": code,
                "programme_name": programme.name,
                "approved_intake": approved[programme.id],
                "already_enrolled": already,
                "in_this_upload": in_upload[code],
                "excess": max(0, total - approved[programme.id]),
            }
        )
    return findings

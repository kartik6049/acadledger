"""Create demo accounts and reference data for local development.

    docker compose exec api python -m app.seed

Safe to run more than once: anything that already exists is left alone. Every
account gets the password in SEED_PASSWORD. Never run this against a real
deployment.
"""

import os
from datetime import date

from sqlalchemy import select

from app.db import SessionLocal
from app.enrolment import refresh_enrolment_view
from app.models import Institute, InstituteStatus, Programme, ProgrammeIntake, Role, User
from app.security import hash_password


def current_academic_year(today: date) -> str:
    """Academic years start in July: November 2026 falls in 2026-27."""
    start = today.year if today.month >= 7 else today.year - 1
    return f"{start}-{(start + 1) % 100:02d}"


ACADEMIC_YEAR = current_academic_year(date.today())

OFFICER = ("officer@aicte.example", "Regulation Bureau Officer")
VERIFIER = ("verifier@employer.example", "Campus Hiring Verifier")

# (aicte_id, name, state, admin email, [(code, name, level, approved intake)])
INSTITUTES = [
    (
        "1-1000001",
        "Sahyadri Institute of Technology",
        "Maharashtra",
        "admin@sahyadri.example",
        [
            ("CSE", "B.Tech Computer Science and Engineering", "ug", 120),
            ("ECE", "B.Tech Electronics and Communication Engineering", "ug", 60),
            ("ME", "B.Tech Mechanical Engineering", "ug", 60),
        ],
    ),
    (
        "1-1000002",
        "Kaveri College of Engineering",
        "Karnataka",
        "admin@kaveri.example",
        [
            ("CSE", "B.Tech Computer Science and Engineering", "ug", 60),
            ("MBA", "Master of Business Administration", "pg", 60),
        ],
    ),
]


def seed() -> None:
    password_hash = hash_password(os.environ.get("SEED_PASSWORD", "acadledger-demo-1"))
    with SessionLocal() as db:

        def ensure_user(
            email: str, full_name: str, role: Role, institute: Institute | None
        ) -> None:
            if db.scalar(select(User.id).where(User.email == email)) is None:
                db.add(
                    User(
                        email=email,
                        password_hash=password_hash,
                        full_name=full_name,
                        role=role,
                        institute=institute,
                    )
                )
                print(f"  user       {email} ({role.value})")

        ensure_user(*OFFICER, Role.AICTE_OFFICER, None)
        ensure_user(*VERIFIER, Role.VERIFIER, None)

        for aicte_id, name, state, admin_email, programmes in INSTITUTES:
            institute = db.scalar(select(Institute).where(Institute.aicte_id == aicte_id))
            if institute is None:
                institute = Institute(
                    aicte_id=aicte_id, name=name, state=state, status=InstituteStatus.ACTIVE
                )
                db.add(institute)
                db.flush()
                print(f"  institute  {name}")
            ensure_user(admin_email, f"{name} Admin", Role.INSTITUTE_ADMIN, institute)

            for code, programme_name, level, approved_intake in programmes:
                programme = db.scalar(
                    select(Programme).where(
                        Programme.institute_id == institute.id, Programme.code == code
                    )
                )
                if programme is None:
                    programme = Programme(
                        institute_id=institute.id, code=code, name=programme_name, level=level
                    )
                    db.add(programme)
                    db.flush()
                if db.get(ProgrammeIntake, (programme.id, ACADEMIC_YEAR)) is None:
                    db.add(
                        ProgrammeIntake(
                            programme_id=programme.id,
                            academic_year=ACADEMIC_YEAR,
                            approved_intake=approved_intake,
                        )
                    )
        refresh_enrolment_view(db)
        db.commit()
    print("Seed complete.")


if __name__ == "__main__":
    seed()

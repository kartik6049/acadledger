import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app import audit
from app.db import get_db
from app.deps import get_current_user, require_role
from app.enrolment import refresh_enrolment_view
from app.models import Institute, InstituteStatus, Programme, ProgrammeIntake, Role, User
from app.schemas import (
    AcademicYear,
    InstituteOut,
    InstituteRegistration,
    InstituteStatusUpdate,
    IntakeUpdate,
    ProgrammeCreate,
    ProgrammeOut,
)
from app.security import hash_password

router = APIRouter(tags=["institutes"])


@router.post(
    "/institutes/register", response_model=InstituteOut, status_code=status.HTTP_201_CREATED
)
def register_institute(body: InstituteRegistration, db: Session = Depends(get_db)) -> Institute:
    """Public. Creates the institute as `pending`; it cannot upload until AICTE approves it."""
    email = body.admin.email.lower()
    if db.scalar(select(Institute.id).where(Institute.aicte_id == body.aicte_id)):
        raise HTTPException(
            status.HTTP_409_CONFLICT, "An institute with this AICTE ID is already registered"
        )
    if db.scalar(select(User.id).where(func.lower(User.email) == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "This email address is already in use")

    institute = Institute(aicte_id=body.aicte_id, name=body.name, state=body.state)
    admin = User(
        email=email,
        password_hash=hash_password(body.admin.password),
        full_name=body.admin.full_name,
        role=Role.INSTITUTE_ADMIN,
        institute=institute,
    )
    db.add_all([institute, admin])
    try:
        db.flush()
    except IntegrityError:
        # lost a race with an identical registration
        raise HTTPException(
            status.HTTP_409_CONFLICT, "This institute or email is already registered"
        ) from None
    audit.append(
        db,
        action="institute.registered",
        entity_type="institute",
        entity_id=institute.id,
        actor=admin,
        institute_id=institute.id,
        payload={"aicte_id": institute.aicte_id, "name": institute.name},
    )
    db.commit()
    return institute


@router.get("/institutes", response_model=list[InstituteOut])
def list_institutes(
    status_filter: InstituteStatus | None = Query(None, alias="status"),
    db: Session = Depends(get_db),
    _: User = Depends(require_role(Role.AICTE_OFFICER)),
) -> list[Institute]:
    query = select(Institute).order_by(Institute.created_at.desc())
    if status_filter:
        query = query.where(Institute.status == status_filter)
    return list(db.scalars(query))


@router.get("/institutes/me", response_model=InstituteOut)
def my_institute(
    db: Session = Depends(get_db), user: User = Depends(require_role(Role.INSTITUTE_ADMIN))
) -> Institute:
    return db.get(Institute, user.institute_id)


@router.post("/institutes/{institute_id}/status", response_model=InstituteOut)
def set_institute_status(
    institute_id: uuid.UUID,
    body: InstituteStatusUpdate,
    db: Session = Depends(get_db),
    officer: User = Depends(require_role(Role.AICTE_OFFICER)),
) -> Institute:
    institute = db.get(Institute, institute_id, with_for_update=True)
    if institute is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Institute not found")
    previous = institute.status
    if previous != body.status:
        institute.status = body.status
        audit.append(
            db,
            action="institute.status_changed",
            entity_type="institute",
            entity_id=institute.id,
            actor=officer,
            institute_id=institute.id,
            payload={"from": previous, "to": body.status},
        )
        db.commit()
    return institute


def _visible_institute(institute_id: uuid.UUID, user: User, db: Session) -> Institute:
    """Officers see every institute; an institute admin sees only their own."""
    institute = db.get(Institute, institute_id)
    allowed = user.role == Role.AICTE_OFFICER or user.institute_id == institute_id
    if institute is None or not allowed:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Institute not found")
    return institute


@router.get("/institutes/{institute_id}/programmes", response_model=list[ProgrammeOut])
def list_programmes(
    institute_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[Programme]:
    _visible_institute(institute_id, user, db)
    return list(
        db.scalars(
            select(Programme)
            .where(Programme.institute_id == institute_id)
            .options(selectinload(Programme.intakes))
            .order_by(Programme.code)
        )
    )


@router.post(
    "/institutes/{institute_id}/programmes",
    response_model=ProgrammeOut,
    status_code=status.HTTP_201_CREATED,
)
def create_programme(
    institute_id: uuid.UUID,
    body: ProgrammeCreate,
    db: Session = Depends(get_db),
    officer: User = Depends(require_role(Role.AICTE_OFFICER)),
) -> Programme:
    _visible_institute(institute_id, officer, db)
    code = body.code.upper()
    if db.scalar(
        select(Programme.id).where(Programme.institute_id == institute_id, Programme.code == code)
    ):
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"Programme {code} already exists for this institute"
        )
    programme = Programme(institute_id=institute_id, code=code, name=body.name, level=body.level)
    db.add(programme)
    db.flush()
    audit.append(
        db,
        action="programme.created",
        entity_type="programme",
        entity_id=programme.id,
        actor=officer,
        institute_id=institute_id,
        payload={"code": code, "name": body.name, "level": body.level},
    )
    db.commit()
    return programme


@router.put("/programmes/{programme_id}/intakes/{academic_year}", response_model=ProgrammeOut)
def set_approved_intake(
    programme_id: uuid.UUID,
    academic_year: AcademicYear,
    body: IntakeUpdate,
    db: Session = Depends(get_db),
    officer: User = Depends(require_role(Role.AICTE_OFFICER)),
) -> Programme:
    programme = db.get(Programme, programme_id, with_for_update=True)
    if programme is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Programme not found")
    intake = db.get(ProgrammeIntake, (programme_id, academic_year))
    previous = intake.approved_intake if intake else None
    if intake is None:
        db.add(
            ProgrammeIntake(
                programme_id=programme_id,
                academic_year=academic_year,
                approved_intake=body.approved_intake,
            )
        )
    else:
        intake.approved_intake = body.approved_intake
    audit.append(
        db,
        action="programme.intake_set",
        entity_type="programme",
        entity_id=programme.id,
        actor=officer,
        institute_id=programme.institute_id,
        payload={"academic_year": academic_year, "from": previous, "to": body.approved_intake},
    )
    refresh_enrolment_view(db)
    db.commit()
    db.refresh(programme, ["intakes"])
    return programme

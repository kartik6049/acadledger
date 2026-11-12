import re

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.db import get_db
from app.deps import require_role
from app.models import Role, Student, User
from app.schemas import StudentPage

router = APIRouter(prefix="/students", tags=["students"])


@router.get("", response_model=StudentPage)
def list_students(
    q: str | None = Query(None, max_length=100, description="APAAR ID, enrolment no. or name"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(require_role(Role.INSTITUTE_ADMIN, Role.AICTE_OFFICER)),
) -> StudentPage:
    """Committed records. Institute admins see only their own institute's students."""
    conditions = []
    if user.role == Role.INSTITUTE_ADMIN:
        conditions.append(Student.institute_id == user.institute_id)
    if q and (q := q.strip()):
        if re.fullmatch(r"\d{12}", q):
            conditions.append(Student.apaar_id == q)
        else:
            conditions.append(
                or_(
                    Student.enrolment_no.istartswith(q, autoescape=True),
                    Student.full_name.icontains(q, autoescape=True),
                )
            )
    total = db.scalar(select(func.count()).select_from(Student).where(*conditions))
    students = db.scalars(
        select(Student)
        .where(*conditions)
        .options(joinedload(Student.programme))
        .order_by(Student.enrolment_no)
        .limit(limit)
        .offset(offset)
    )
    return StudentPage(total=total, items=list(students))

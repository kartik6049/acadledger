from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import require_role
from app.models import Role, User
from app.schemas import AcademicYear, DashboardSummary, IntakeRow, IntakeRowPage

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

_SUMMARY = text(
    """
    SELECT
        (SELECT count(*) FROM institutes WHERE status = 'active')  AS institutes_active,
        (SELECT count(*) FROM institutes WHERE status = 'pending') AS institutes_pending,
        count(*)                                                    AS programmes,
        coalesce(sum(approved_intake), 0)                           AS approved_intake,
        coalesce(sum(enrolled), 0)                                  AS enrolled,
        count(*) FILTER (WHERE enrolled > approved_intake)          AS programmes_over_intake,
        coalesce(sum(greatest(enrolled - approved_intake, 0)), 0)   AS excess_students
    FROM programme_enrolment
    WHERE academic_year = :academic_year
    """
)

_INTAKE_ROWS = text(
    """
    SELECT i.id AS institute_id, i.name AS institute_name, i.aicte_id, i.state,
           p.code AS programme_code, p.name AS programme_name,
           e.academic_year, e.approved_intake, e.enrolled,
           greatest(e.enrolled - e.approved_intake, 0) AS excess,
           count(*) OVER () AS total
    FROM programme_enrolment e
    JOIN programmes p ON p.id = e.programme_id
    JOIN institutes i ON i.id = e.institute_id
    WHERE e.academic_year = :academic_year
      AND (NOT :only_excess OR e.enrolled > e.approved_intake)
    -- worst offenders first, then the fullest programmes
    ORDER BY excess DESC,
             e.enrolled::float / nullif(e.approved_intake, 0) DESC NULLS LAST,
             i.name, p.code
    LIMIT :limit OFFSET :offset
    """
)


@router.get("/summary", response_model=DashboardSummary)
def summary(
    academic_year: AcademicYear,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(Role.AICTE_OFFICER)),
) -> dict:
    row = db.execute(_SUMMARY, {"academic_year": academic_year}).one()
    return {"academic_year": academic_year, **row._mapping}


@router.get("/intake", response_model=IntakeRowPage)
def intake_against_enrolment(
    academic_year: AcademicYear,
    only_excess: bool = False,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _: User = Depends(require_role(Role.AICTE_OFFICER)),
) -> IntakeRowPage:
    """Every programme with an approved intake for the year, programmes over intake first."""
    rows = db.execute(
        _INTAKE_ROWS,
        {
            "academic_year": academic_year,
            "only_excess": only_excess,
            "limit": limit,
            "offset": offset,
        },
    ).all()
    return IntakeRowPage(
        total=rows[0].total if rows else 0,
        items=[IntakeRow.model_validate(row._mapping) for row in rows],
    )

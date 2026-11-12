from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import audit
from app.db import get_db
from app.deps import require_role
from app.models import AuditLog, Role, User
from app.schemas import AuditPage, ChainReportOut

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("", response_model=AuditPage)
def list_audit_entries(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _: User = Depends(require_role(Role.AICTE_OFFICER)),
) -> AuditPage:
    total = db.scalar(select(func.count()).select_from(AuditLog))
    entries = db.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(limit).offset(offset))
    return AuditPage(total=total, items=list(entries))


@router.get("/verify", response_model=ChainReportOut)
def verify_audit_chain(
    db: Session = Depends(get_db), _: User = Depends(require_role(Role.AICTE_OFFICER))
) -> audit.ChainReport:
    """Recompute every hash in the chain and report the first entry that does not fit."""
    return audit.verify_chain(db)

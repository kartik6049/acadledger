"""Consent-based verification.

A student who wants an employer or university to confirm their record asks
their institute for a verification link. The link (also shown as a QR code)
carries a random token; handing it over is the student's consent. An authorised
verifier who presents the token gets that one student's record and nothing
else, and every attempt is written to the audit log.
"""

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app import audit
from app.db import get_db
from app.deps import require_active_institute, require_role
from app.models import Institute, Programme, Role, Student, User, VerificationGrant
from app.schemas import (
    VerificationLinkCreate,
    VerificationLinkCreated,
    VerificationLinkOut,
    VerifiedRecord,
    VerifierCreate,
    VerifierOut,
    VerifyRequest,
)
from app.security import hash_password

router = APIRouter(tags=["verification"])


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# --- institutes issue and revoke links -------------------------------------------------------


def _own_student(student_id: uuid.UUID, institute: Institute, db: Session) -> Student:
    student = db.get(Student, student_id)
    if student is None or student.institute_id != institute.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Student not found")
    return student


@router.post(
    "/students/{student_id}/verification-links",
    response_model=VerificationLinkCreated,
    status_code=status.HTTP_201_CREATED,
)
def create_verification_link(
    student_id: uuid.UUID,
    body: VerificationLinkCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(Role.INSTITUTE_ADMIN)),
    institute: Institute = Depends(require_active_institute),
) -> VerificationLinkCreated:
    """Issue a link at the student's request. The token is returned once and never stored."""
    student = _own_student(student_id, institute, db)
    token = secrets.token_urlsafe(32)
    grant = VerificationGrant(
        student_id=student.id,
        token_hash=_hash_token(token),
        created_by=user.id,
        expires_at=datetime.now(UTC) + timedelta(days=body.expires_in_days),
    )
    db.add(grant)
    db.flush()
    audit.append(
        db,
        action="verification.link_created",
        entity_type="student",
        entity_id=student.id,
        actor=user,
        institute_id=institute.id,
        payload={"grant_id": str(grant.id), "expires_in_days": body.expires_in_days},
    )
    db.commit()
    return VerificationLinkCreated(
        token=token, **VerificationLinkOut.model_validate(grant).model_dump()
    )


@router.get("/students/{student_id}/verification-links", response_model=list[VerificationLinkOut])
def list_verification_links(
    student_id: uuid.UUID,
    db: Session = Depends(get_db),
    institute: Institute = Depends(require_active_institute),
) -> list[VerificationGrant]:
    student = _own_student(student_id, institute, db)
    return list(
        db.scalars(
            select(VerificationGrant)
            .where(VerificationGrant.student_id == student.id)
            .order_by(VerificationGrant.created_at.desc())
        )
    )


@router.delete("/verification-links/{grant_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_verification_link(
    grant_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(Role.INSTITUTE_ADMIN)),
    institute: Institute = Depends(require_active_institute),
) -> None:
    grant = db.scalar(
        select(VerificationGrant)
        .join(Student)
        .where(VerificationGrant.id == grant_id, Student.institute_id == institute.id)
        .with_for_update(of=VerificationGrant)
    )
    if grant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Verification link not found")
    if grant.revoked_at is None:
        grant.revoked_at = datetime.now(UTC)
        audit.append(
            db,
            action="verification.link_revoked",
            entity_type="student",
            entity_id=grant.student_id,
            actor=user,
            institute_id=institute.id,
            payload={"grant_id": str(grant.id)},
        )
        db.commit()


# --- verifiers look a student up -------------------------------------------------------------


@router.post("/verify", response_model=VerifiedRecord)
def verify(
    body: VerifyRequest,
    db: Session = Depends(get_db),
    verifier: User = Depends(require_role(Role.VERIFIER, Role.AICTE_OFFICER)),
) -> VerifiedRecord:
    """Confirm one student's record. POST, not GET: each call is a logged lookup, and the
    token stays out of URLs and therefore out of server logs."""
    now = datetime.now(UTC)
    grant = db.scalar(
        select(VerificationGrant)
        .where(VerificationGrant.token_hash == _hash_token(body.token))
        .options(
            joinedload(VerificationGrant.student)
            .joinedload(Student.programme)
            .joinedload(Programme.institute)
        )
        .with_for_update(of=VerificationGrant)
    )
    usable = grant is not None and grant.revoked_at is None and grant.expires_at > now
    if not usable:
        audit.append(
            db,
            action="verification.lookup_refused",
            entity_type="verification_grant",
            entity_id=grant.id if grant else "unknown",
            actor=verifier,
            payload={"reason": "unknown" if grant is None else "expired_or_revoked"},
        )
        db.commit()
        # one message for every cause, so a guess learns nothing about which tokens exist
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "This verification link is invalid, expired or revoked"
        )

    student = grant.student
    institute = student.programme.institute
    grant.lookup_count += 1
    grant.last_used_at = now
    audit.append(
        db,
        action="verification.lookup",
        entity_type="student",
        entity_id=student.id,
        actor=verifier,
        institute_id=institute.id,
        payload={"grant_id": str(grant.id), "organisation": verifier.organisation},
    )
    db.commit()
    # deliberately minimal: enough to confirm enrolment, no date of birth, no full APAAR ID
    return VerifiedRecord(
        full_name=student.full_name,
        apaar_last4=student.apaar_id[-4:],
        enrolment_no=student.enrolment_no,
        academic_year=student.academic_year,
        programme_code=student.programme.code,
        programme_name=student.programme.name,
        institute_name=institute.name,
        institute_aicte_id=institute.aicte_id,
        institute_state=institute.state,
        institute_status=institute.status,
        verified_at=now,
        link_expires_at=grant.expires_at,
    )


# --- AICTE authorises verifiers --------------------------------------------------------------


@router.get("/verifiers", response_model=list[VerifierOut])
def list_verifiers(
    db: Session = Depends(get_db), _: User = Depends(require_role(Role.AICTE_OFFICER))
) -> list[User]:
    return list(
        db.scalars(select(User).where(User.role == Role.VERIFIER).order_by(User.created_at.desc()))
    )


@router.post("/verifiers", response_model=VerifierOut, status_code=status.HTTP_201_CREATED)
def create_verifier(
    body: VerifierCreate,
    db: Session = Depends(get_db),
    officer: User = Depends(require_role(Role.AICTE_OFFICER)),
) -> User:
    email = body.email.lower()
    if db.scalar(select(User.id).where(func.lower(User.email) == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "This email address is already in use")
    verifier = User(
        email=email,
        password_hash=hash_password(body.password),
        full_name=body.full_name,
        organisation=body.organisation,
        role=Role.VERIFIER,
    )
    db.add(verifier)
    db.flush()
    audit.append(
        db,
        action="verifier.created",
        entity_type="user",
        entity_id=verifier.id,
        actor=officer,
        payload={"email": email, "organisation": body.organisation},
    )
    db.commit()
    return verifier

import uuid
from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Role(StrEnum):
    AICTE_OFFICER = "aicte_officer"
    INSTITUTE_ADMIN = "institute_admin"
    VERIFIER = "verifier"


class InstituteStatus(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    REJECTED = "rejected"


class UploadStatus(StrEnum):
    QUEUED = "queued"
    VALIDATING = "validating"
    VALIDATED = "validated"
    FAILED = "failed"
    COMMITTED = "committed"


def _in(column: str, enum: type[StrEnum]) -> str:
    return f"{column} IN ({', '.join(repr(m.value) for m in enum)})"


class Institute(Base):
    __tablename__ = "institutes"
    __table_args__ = (CheckConstraint(_in("status", InstituteStatus), name="status"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    aicte_id: Mapped[str] = mapped_column(String(30), unique=True)
    name: Mapped[str] = mapped_column(String(300))
    state: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20), default=InstituteStatus.PENDING)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    programmes: Mapped[list["Programme"]] = relationship(back_populates="institute")


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(_in("role", Role), name="role"),
        # an institute admin always belongs to an institute; nobody else does
        CheckConstraint(
            "(role = 'institute_admin') = (institute_id IS NOT NULL)", name="institute_scope"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    full_name: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(20))
    # who a verifier works for (an employer, a university); unused for other roles
    organisation: Mapped[str | None] = mapped_column(String(200))
    institute_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("institutes.id"), index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # wrong passwords in a row, and the lockout they lead to (see routers/auth.py)
    failed_logins: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    institute: Mapped[Institute | None] = relationship()


class Programme(Base):
    __tablename__ = "programmes"
    __table_args__ = (UniqueConstraint("institute_id", "code"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    institute_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("institutes.id"))
    code: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(200))
    level: Mapped[str] = mapped_column(String(20))

    institute: Mapped[Institute] = relationship(back_populates="programmes")
    intakes: Mapped[list["ProgrammeIntake"]] = relationship(
        back_populates="programme", order_by="ProgrammeIntake.academic_year"
    )


class ProgrammeIntake(Base):
    """AICTE-approved first-year intake for one programme in one academic year."""

    __tablename__ = "programme_intakes"
    __table_args__ = (CheckConstraint("approved_intake >= 0", name="non_negative"),)

    programme_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("programmes.id"), primary_key=True)
    academic_year: Mapped[str] = mapped_column(String(7), primary_key=True)
    approved_intake: Mapped[int] = mapped_column(Integer)

    programme: Mapped[Programme] = relationship(back_populates="intakes")


class Upload(Base):
    __tablename__ = "uploads"
    __table_args__ = (
        CheckConstraint(_in("status", UploadStatus), name="status"),
        Index("ix_uploads_institute_id_created_at", "institute_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    institute_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("institutes.id"))
    uploaded_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    academic_year: Mapped[str] = mapped_column(String(7))
    original_filename: Mapped[str] = mapped_column(String(255))
    storage_key: Mapped[str] = mapped_column(String(300))
    file_sha256: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20), default=UploadStatus.QUEUED)
    total_rows: Mapped[int] = mapped_column(Integer, default=0)
    valid_rows: Mapped[int] = mapped_column(Integer, default=0)
    error_rows: Mapped[int] = mapped_column(Integer, default=0)
    # error counts per code/stage, intake findings, validation duration
    summary: Mapped[dict] = mapped_column(JSONB, default=dict)
    failure_reason: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    committed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    institute: Mapped[Institute] = relationship()


class UploadRow(Base):
    """Staging table: one row per spreadsheet row, with its validation result."""

    __tablename__ = "upload_rows"
    __table_args__ = (Index("ix_upload_rows_upload_id_is_valid", "upload_id", "is_valid"),)

    upload_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("uploads.id", ondelete="CASCADE"), primary_key=True
    )
    # the row number as the user sees it in their spreadsheet (header is row 1)
    row_number: Mapped[int] = mapped_column(Integer, primary_key=True)
    data: Mapped[dict] = mapped_column(JSONB)
    is_valid: Mapped[bool] = mapped_column(Boolean)
    errors: Mapped[list] = mapped_column(JSONB, default=list)


class Student(Base):
    """The central repository: exactly one record per APAAR ID across all institutes."""

    __tablename__ = "students"
    __table_args__ = (
        UniqueConstraint("institute_id", "enrolment_no"),
        Index("ix_students_programme_id_academic_year", "programme_id", "academic_year"),
        CheckConstraint("apaar_id ~ '^[0-9]{12}$'", name="apaar_format"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    apaar_id: Mapped[str] = mapped_column(String(12), unique=True)
    institute_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("institutes.id"))
    programme_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("programmes.id"))
    # year of admission: the year whose approved intake this student counts against
    academic_year: Mapped[str] = mapped_column(String(7))
    enrolment_no: Mapped[str] = mapped_column(String(40))
    full_name: Mapped[str] = mapped_column(String(200))
    date_of_birth: Mapped[date] = mapped_column(Date)
    gender: Mapped[str] = mapped_column(String(10))
    source_upload_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("uploads.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    programme: Mapped[Programme] = relationship()

    @property
    def programme_code(self) -> str:
        return self.programme.code


class VerificationGrant(Base):
    """Consent to verify one student: whoever holds the token may look that student up.

    Only a hash of the token is stored, so a copy of this table cannot be used to
    verify anyone. The token itself is shown once, as a link and QR code.
    """

    __tablename__ = "verification_grants"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    student_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("students.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lookup_count: Mapped[int] = mapped_column(Integer, default=0)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    student: Mapped[Student] = relationship()


class AuditLog(Base):
    """Append-only, hash-chained. See app/audit.py; UPDATE/DELETE are blocked by a trigger."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    actor_role: Mapped[str | None] = mapped_column(String(20))
    action: Mapped[str] = mapped_column(String(60), index=True)
    entity_type: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[str] = mapped_column(String(64))
    institute_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("institutes.id"), index=True)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    prev_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64), unique=True)

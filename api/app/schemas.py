import re
import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, EmailStr, Field, StringConstraints

from app.models import InstituteStatus

Trimmed = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


def _academic_year(value: str) -> str:
    match = re.fullmatch(r"(\d{4})-(\d{2})", value)
    if not match or (int(match[1]) + 1) % 100 != int(match[2]):
        raise ValueError("academic year must look like 2026-27")
    return value


AcademicYear = Annotated[str, AfterValidator(_academic_year)]


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- auth -----------------------------------------------------------------------------------


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class PasswordChange(BaseModel):
    current_password: str
    new_password: Annotated[str, Field(min_length=10, max_length=128)]


class UserOut(ORMModel):
    id: uuid.UUID
    email: str
    full_name: str
    role: str
    institute_id: uuid.UUID | None


class LoginResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    user: UserOut


# --- institutes -----------------------------------------------------------------------------


class AdminAccount(BaseModel):
    full_name: Annotated[Trimmed, Field(max_length=200)]
    email: EmailStr
    password: Annotated[str, Field(min_length=10, max_length=128)]


class InstituteRegistration(BaseModel):
    aicte_id: Annotated[Trimmed, Field(max_length=30)]
    name: Annotated[Trimmed, Field(max_length=300)]
    state: Annotated[Trimmed, Field(max_length=100)]
    admin: AdminAccount


class InstituteOut(ORMModel):
    id: uuid.UUID
    aicte_id: str
    name: str
    state: str
    status: str
    created_at: datetime


class InstituteStatusUpdate(BaseModel):
    status: Literal[InstituteStatus.ACTIVE, InstituteStatus.SUSPENDED, InstituteStatus.REJECTED]


# --- programmes -----------------------------------------------------------------------------


class ProgrammeCreate(BaseModel):
    code: Annotated[Trimmed, Field(max_length=20, pattern=r"^[A-Za-z0-9_-]+$")]
    name: Annotated[Trimmed, Field(max_length=200)]
    level: Literal["diploma", "ug", "pg"]


class IntakeOut(ORMModel):
    academic_year: str
    approved_intake: int


class IntakeUpdate(BaseModel):
    approved_intake: Annotated[int, Field(ge=0, le=100_000)]


class ProgrammeOut(ORMModel):
    id: uuid.UUID
    institute_id: uuid.UUID
    code: str
    name: str
    level: str
    intakes: list[IntakeOut]


# --- uploads --------------------------------------------------------------------------------


class UploadOut(ORMModel):
    id: uuid.UUID
    institute_id: uuid.UUID
    academic_year: str
    original_filename: str
    status: str
    total_rows: int
    valid_rows: int
    error_rows: int
    summary: dict
    failure_reason: str | None
    created_at: datetime
    finished_at: datetime | None
    committed_at: datetime | None


class RowError(BaseModel):
    stage: str
    field: str
    code: str
    message: str


class UploadRowOut(ORMModel):
    row_number: int
    data: dict[str, str]
    is_valid: bool
    errors: list[RowError]


class UploadRowPage(BaseModel):
    total: int
    items: list[UploadRowOut]


# --- students -------------------------------------------------------------------------------


class StudentOut(ORMModel):
    id: uuid.UUID
    apaar_id: str
    institute_id: uuid.UUID
    programme_id: uuid.UUID
    programme_code: str
    academic_year: str
    enrolment_no: str
    full_name: str
    date_of_birth: date
    gender: str


class StudentPage(BaseModel):
    total: int
    items: list[StudentOut]


# --- audit ----------------------------------------------------------------------------------


class AuditEntryOut(ORMModel):
    id: int
    occurred_at: datetime
    actor_user_id: uuid.UUID | None
    actor_role: str | None
    action: str
    entity_type: str
    entity_id: str
    institute_id: uuid.UUID | None
    payload: dict
    prev_hash: str
    hash: str


class AuditPage(BaseModel):
    total: int
    items: list[AuditEntryOut]


class ChainReportOut(ORMModel):
    ok: bool
    entries_checked: int
    first_broken_id: int | None
    reason: str | None


# --- dashboard ------------------------------------------------------------------------------


class DashboardSummary(BaseModel):
    academic_year: str
    institutes_active: int
    institutes_pending: int
    programmes: int
    approved_intake: int
    enrolled: int
    programmes_over_intake: int
    excess_students: int


class IntakeRow(BaseModel):
    institute_id: uuid.UUID
    institute_name: str
    aicte_id: str
    state: str
    programme_code: str
    programme_name: str
    academic_year: str
    approved_intake: int
    enrolled: int
    excess: int


class IntakeRowPage(BaseModel):
    total: int
    items: list[IntakeRow]


# --- verification ---------------------------------------------------------------------------


class VerificationLinkCreate(BaseModel):
    expires_in_days: Annotated[int, Field(ge=1, le=365)] = 30


class VerificationLinkOut(ORMModel):
    id: uuid.UUID
    created_at: datetime
    expires_at: datetime
    revoked_at: datetime | None
    lookup_count: int
    last_used_at: datetime | None


class VerificationLinkCreated(VerificationLinkOut):
    # the only time the token is ever sent; the server keeps just its hash
    token: str


class VerifyRequest(BaseModel):
    token: Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{20,100}$")]


class VerifiedRecord(BaseModel):
    full_name: str
    apaar_last4: str
    enrolment_no: str
    academic_year: str
    programme_code: str
    programme_name: str
    institute_name: str
    institute_aicte_id: str
    institute_state: str
    institute_status: str
    verified_at: datetime
    link_expires_at: datetime


class VerifierCreate(BaseModel):
    full_name: Annotated[Trimmed, Field(max_length=200)]
    organisation: Annotated[Trimmed, Field(max_length=200)]
    email: EmailStr
    password: Annotated[str, Field(min_length=10, max_length=128)]


class VerifierOut(ORMModel):
    id: uuid.UUID
    email: str
    full_name: str
    organisation: str | None
    is_active: bool
    created_at: datetime

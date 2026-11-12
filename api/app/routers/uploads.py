import csv
import hashlib
import io
import logging
import uuid
from collections.abc import Iterator
from pathlib import PurePath
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import Response, StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import audit, worker
from app.config import get_settings
from app.db import SessionLocal, get_db
from app.deps import get_current_user, require_active_institute, require_role
from app.models import Institute, Role, Upload, UploadRow, UploadStatus, User
from app.pipeline.commit import CommitError, commit_upload
from app.pipeline.parser import ALLOWED_EXTENSIONS, COLUMNS
from app.schemas import AcademicYear, UploadOut, UploadRowPage
from app.storage import get_storage

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/uploads", tags=["uploads"])

_CONTENT_TYPES = {
    ".csv": "text/csv",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}
_TEMPLATE_EXAMPLE = ("123456789012", "Asha Verma", "2007-04-18", "female", "CSE", "2026CSE001")


@router.get("/template.csv")
def download_template() -> Response:
    """The spreadsheet layout institutes should fill in. Delete the example row before uploading."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(COLUMNS)
    writer.writerow(_TEMPLATE_EXAMPLE)
    return Response(
        buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="acadledger-template.csv"'},
    )


@router.post("", response_model=UploadOut, status_code=status.HTTP_202_ACCEPTED)
def create_upload(
    # Annotated form, not `= Form()`: the default-value style drops AcademicYear's validator
    academic_year: Annotated[AcademicYear, Form()],
    file: UploadFile = File(),
    db: Session = Depends(get_db),
    user: User = Depends(require_role(Role.INSTITUTE_ADMIN)),
    institute: Institute = Depends(require_active_institute),
) -> Upload:
    """Store the file and queue it for validation. Poll GET /uploads/{id} for the result."""
    settings = get_settings()
    filename = PurePath(file.filename or "").name
    extension = PurePath(filename).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Upload a .csv or .xlsx file")

    content = file.file.read(settings.max_upload_bytes + 1)
    if len(content) > settings.max_upload_bytes:
        limit_mb = settings.max_upload_bytes // (1024 * 1024)
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, f"The file is larger than {limit_mb} MB"
        )
    if not content:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The file is empty")

    upload_id = uuid.uuid4()
    # The key is built from ids only; the user's filename never becomes part of a storage path.
    storage_key = f"uploads/{institute.id}/{upload_id}{extension}"
    get_storage().put(storage_key, content, _CONTENT_TYPES[extension])

    upload = Upload(
        id=upload_id,
        institute_id=institute.id,
        uploaded_by=user.id,
        academic_year=academic_year,
        original_filename=filename[:255],
        storage_key=storage_key,
        file_sha256=hashlib.sha256(content).hexdigest(),
    )
    db.add(upload)
    db.flush()
    audit.append(
        db,
        action="upload.created",
        entity_type="upload",
        entity_id=upload.id,
        actor=user,
        institute_id=institute.id,
        payload={
            "filename": upload.original_filename,
            "academic_year": academic_year,
            "file_sha256": upload.file_sha256,
            "bytes": len(content),
        },
    )
    db.commit()

    try:
        worker.enqueue_validation(upload.id)
    except Exception:
        logger.exception("could not queue upload %s", upload.id)
        upload.status = UploadStatus.FAILED
        upload.failure_reason = "The validation queue is unavailable. Upload the file again later."
        db.commit()
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, upload.failure_reason) from None
    return upload


@router.get("", response_model=list[UploadOut])
def list_uploads(
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(require_role(Role.INSTITUTE_ADMIN, Role.AICTE_OFFICER)),
) -> list[Upload]:
    query = select(Upload).order_by(Upload.created_at.desc()).limit(limit)
    if user.role == Role.INSTITUTE_ADMIN:
        query = query.where(Upload.institute_id == user.institute_id)
    return list(db.scalars(query))


def _visible_upload(
    upload_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> Upload:
    """Officers see every upload; an institute admin sees only their institute's."""
    upload = db.get(Upload, upload_id)
    allowed = user.role == Role.AICTE_OFFICER or (
        user.role == Role.INSTITUTE_ADMIN and upload and upload.institute_id == user.institute_id
    )
    if upload is None or not allowed:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Upload not found")
    return upload


@router.get("/{upload_id}", response_model=UploadOut)
def get_upload(upload: Upload = Depends(_visible_upload)) -> Upload:
    return upload


@router.get("/{upload_id}/rows", response_model=UploadRowPage)
def list_upload_rows(
    only_invalid: bool = True,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    upload: Upload = Depends(_visible_upload),
    db: Session = Depends(get_db),
) -> UploadRowPage:
    conditions = [UploadRow.upload_id == upload.id]
    if only_invalid:
        conditions.append(UploadRow.is_valid.is_(False))
    total = db.scalar(select(func.count()).select_from(UploadRow).where(*conditions))
    rows = db.scalars(
        select(UploadRow)
        .where(*conditions)
        .order_by(UploadRow.row_number)
        .limit(limit)
        .offset(offset)
    )
    return UploadRowPage(total=total, items=list(rows))


def _csv_safe(value: str) -> str:
    # The report echoes user-supplied cells. Neutralise ones a spreadsheet would run as a formula.
    return "'" + value if value[:1] in ("=", "+", "-", "@", "\t", "\r") else value


def _error_report(upload_id: uuid.UUID) -> Iterator[str]:
    buffer = io.StringIO()
    writer = csv.writer(buffer)

    def flush() -> str:
        chunk = buffer.getvalue()
        buffer.seek(0)
        buffer.truncate()
        return chunk

    writer.writerow(["row_number", "field", "value", "code", "message", "stage"])
    yield flush()
    # Own session: this generator runs while the response streams, after the
    # request-scoped session may already have been closed.
    with SessionLocal() as db:
        rows = db.scalars(
            select(UploadRow)
            .where(UploadRow.upload_id == upload_id, UploadRow.is_valid.is_(False))
            .order_by(UploadRow.row_number)
            .execution_options(yield_per=1000)
        )
        for row in rows:
            for error in row.errors:
                writer.writerow(
                    [
                        row.row_number,
                        error["field"],
                        _csv_safe(row.data.get(error["field"], "")),
                        error["code"],
                        error["message"],
                        error["stage"],
                    ]
                )
            yield flush()


@router.get("/{upload_id}/errors.csv")
def download_error_report(upload: Upload = Depends(_visible_upload)) -> StreamingResponse:
    return StreamingResponse(
        _error_report(upload.id),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="errors-{upload.id}.csv"'},
    )


@router.post("/{upload_id}/commit", response_model=UploadOut)
def commit(
    upload: Upload = Depends(_visible_upload),
    db: Session = Depends(get_db),
    user: User = Depends(require_role(Role.INSTITUTE_ADMIN)),
    _: Institute = Depends(require_active_institute),
) -> Upload:
    """Add every row of a fully valid upload to the central repository. All or nothing."""
    try:
        return commit_upload(db, upload.id, user)
    except CommitError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None

"""Moves a fully valid upload from the staging table into the central repository."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import audit
from app.enrolment import refresh_enrolment_view
from app.models import Upload, UploadStatus, User


class CommitError(Exception):
    """The upload cannot be committed. The message is shown to the user."""


# Rows can go stale between validation and commit (another upload may have been
# committed in the meantime), so the repository-level duplicate checks run again here.
_STALE_ROWS = text(
    """
    WITH stale AS (
        SELECT r.row_number,
               jsonb_build_object(
                   'stage', 'duplicates',
                   'field', 'apaar_id',
                   'code', CASE WHEN s.institute_id = :institute_id
                                THEN 'APAAR_ALREADY_ENROLLED' ELSE 'APAAR_AT_ANOTHER_INSTITUTE' END,
                   'message', CASE WHEN s.institute_id = :institute_id
                                THEN 'this APAAR ID is already in your institute''s records'
                                ELSE 'this APAAR ID is already enrolled at another institute' END
               ) AS error
        FROM upload_rows r
        JOIN students s ON s.apaar_id = r.data->>'apaar_id'
        WHERE r.upload_id = :upload_id
        UNION ALL
        SELECT r.row_number,
               jsonb_build_object(
                   'stage', 'duplicates',
                   'field', 'enrolment_no',
                   'code', 'ENROLMENT_NO_EXISTS',
                   'message', 'this enrolment_no is already in your institute''s records'
               )
        FROM upload_rows r
        JOIN students s ON s.institute_id = :institute_id
                       AND s.enrolment_no = r.data->>'enrolment_no'
        WHERE r.upload_id = :upload_id
    ),
    per_row AS (
        SELECT row_number, jsonb_agg(error) AS errors FROM stale GROUP BY row_number
    )
    UPDATE upload_rows r
    SET is_valid = false, errors = r.errors || per_row.errors
    FROM per_row
    WHERE r.upload_id = :upload_id AND r.row_number = per_row.row_number
    """
)

_INSERT_STUDENTS = text(
    """
    INSERT INTO students (id, apaar_id, institute_id, programme_id, academic_year,
                          enrolment_no, full_name, date_of_birth, gender, source_upload_id)
    SELECT gen_random_uuid(), r.data->>'apaar_id', :institute_id, p.id, :academic_year,
           r.data->>'enrolment_no', r.data->>'full_name', (r.data->>'date_of_birth')::date,
           r.data->>'gender', :upload_id
    FROM upload_rows r
    JOIN programmes p ON p.institute_id = :institute_id AND p.code = r.data->>'programme_code'
    WHERE r.upload_id = :upload_id
    """
)


def commit_upload(db: Session, upload_id: uuid.UUID, actor: User) -> Upload:
    upload = db.get(Upload, upload_id, with_for_update=True)
    if upload.status == UploadStatus.COMMITTED:
        raise CommitError("This upload has already been committed.")
    if upload.status != UploadStatus.VALIDATED:
        raise CommitError("This upload has not finished validating.")
    if upload.error_rows:
        raise CommitError("Fix the rows with errors and upload the file again before committing.")

    params = {
        "upload_id": upload.id,
        "institute_id": upload.institute_id,
        "academic_year": upload.academic_year,
    }
    stale = db.execute(_STALE_ROWS, params).rowcount
    if stale:
        upload.error_rows = stale
        upload.valid_rows = upload.total_rows - stale
        db.commit()
        raise CommitError(
            f"{stale} row(s) now clash with records committed after this file was validated. "
            "See the error report."
        )

    try:
        inserted = db.execute(_INSERT_STUDENTS, params).rowcount
    except IntegrityError:
        # A concurrent commit inserted one of the same students after our check above.
        db.rollback()
        raise CommitError("Another upload was committed at the same moment. Try again.") from None
    if inserted != upload.total_rows:
        db.rollback()
        raise CommitError("The programme list changed since validation. Upload the file again.")

    # The staging rows are a second copy of every student's personal details and have
    # now served their purpose; the counts stay on the upload itself.
    db.execute(text("DELETE FROM upload_rows WHERE upload_id = :upload_id"), params)

    upload.status = UploadStatus.COMMITTED
    upload.committed_at = datetime.now(UTC)
    audit.append(
        db,
        action="upload.committed",
        entity_type="upload",
        entity_id=upload.id,
        actor=actor,
        institute_id=upload.institute_id,
        payload={
            "students_added": inserted,
            "academic_year": upload.academic_year,
            "file_sha256": upload.file_sha256,
        },
    )
    refresh_enrolment_view(db)
    db.commit()
    return upload

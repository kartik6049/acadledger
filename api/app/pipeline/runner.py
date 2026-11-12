"""Runs the validation pipeline for one upload and stores the per-row results."""

import logging
import time
import uuid
from datetime import UTC, datetime

from psycopg.types.json import Jsonb
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app import audit
from app.apaar import ApaarUnavailableError, get_apaar_client
from app.config import get_settings
from app.db import SessionLocal
from app.models import Upload, UploadRow, UploadStatus
from app.pipeline.parser import FileFormatError, parse_upload
from app.pipeline.stages import Context, RowState, run_stages
from app.storage import get_storage

logger = logging.getLogger(__name__)


def _store_rows(db: Session, upload_id: uuid.UUID, rows: list[RowState]) -> None:
    # COPY instead of INSERT: this step took 45 s -> 19 s on a 100,000-row file. It runs
    # on the session's own connection, so it is part of the same transaction.
    cursor = db.connection().connection.cursor()
    with cursor.copy(
        "COPY upload_rows (upload_id, row_number, data, is_valid, errors) FROM STDIN"
    ) as copy:
        for row in rows:
            copy.write_row(
                (upload_id, row.row_number, Jsonb(row.data), row.is_valid, Jsonb(row.errors))
            )


def run_validation(upload_id: uuid.UUID) -> None:
    with SessionLocal() as db:
        upload = db.get(Upload, upload_id, with_for_update=True)
        # VALIDATING is accepted too: it means a worker died mid-run and the task was redelivered.
        if upload is None or upload.status not in (UploadStatus.QUEUED, UploadStatus.VALIDATING):
            logger.warning("upload %s is not waiting for validation; skipping", upload_id)
            return
        upload.status = UploadStatus.VALIDATING
        upload.started_at = datetime.now(UTC)
        db.commit()

        started = time.perf_counter()
        try:
            content = get_storage().get(upload.storage_key)
            parsed = parse_upload(upload.original_filename, content, get_settings().max_upload_rows)
            ctx = Context(
                db=db,
                institute_id=upload.institute_id,
                academic_year=upload.academic_year,
                apaar=get_apaar_client(),
                today=datetime.now(UTC).date(),
            )
            rows, summary = run_stages(parsed, ctx)

            db.execute(delete(UploadRow).where(UploadRow.upload_id == upload.id))
            _store_rows(db, upload.id, rows)

            upload.total_rows = len(rows)
            upload.valid_rows = sum(row.is_valid for row in rows)
            upload.error_rows = upload.total_rows - upload.valid_rows
            upload.summary = summary | {
                "validation_ms": int((time.perf_counter() - started) * 1000)
            }
            upload.status = UploadStatus.VALIDATED
            upload.finished_at = datetime.now(UTC)
            audit.append(
                db,
                action="upload.validated",
                entity_type="upload",
                entity_id=upload.id,
                institute_id=upload.institute_id,
                payload={
                    "total_rows": upload.total_rows,
                    "valid_rows": upload.valid_rows,
                    "error_rows": upload.error_rows,
                },
            )
            db.commit()
            logger.info(
                "upload %s validated: %d rows, %d with errors, %d ms",
                upload.id,
                upload.total_rows,
                upload.error_rows,
                upload.summary["validation_ms"],
            )
        except FileFormatError as exc:
            _mark_failed(db, upload_id, str(exc))
        except ApaarUnavailableError:
            _mark_failed(
                db, upload_id, "The APAAR service is unavailable. Upload the file again later."
            )
        except Exception:
            logger.exception("validation of upload %s crashed", upload_id)
            _mark_failed(db, upload_id, "Validation failed unexpectedly. Please try again.")


def _mark_failed(db, upload_id: uuid.UUID, reason: str) -> None:
    db.rollback()
    upload = db.get(Upload, upload_id)
    upload.status = UploadStatus.FAILED
    upload.failure_reason = reason[:500]
    upload.finished_at = datetime.now(UTC)
    audit.append(
        db,
        action="upload.failed",
        entity_type="upload",
        entity_id=upload.id,
        institute_id=upload.institute_id,
        payload={"reason": upload.failure_reason},
    )
    db.commit()

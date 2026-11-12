import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, FastAPI
from sqlalchemy import text

from app.db import SessionLocal
from app.deps import require_csrf_header
from app.routers import audit, auth, dashboard, institutes, students, uploads, verification
from app.storage import S3Storage, get_storage

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def _ensure_bucket(attempts: int = 10) -> None:
    storage = get_storage()
    if not isinstance(storage, S3Storage):
        return
    # MinIO may still be starting when the API container comes up.
    for attempt in range(1, attempts + 1):
        try:
            storage.ensure_bucket()
            return
        except Exception as exc:
            if attempt == attempts:
                raise
            logger.warning("object storage not ready (%s); retrying", exc.__class__.__name__)
            time.sleep(1)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    _ensure_bucket()
    yield


app = FastAPI(
    title="AcadLedger API",
    version="0.1.0",
    description="APAAR-linked student records and verification platform (SIH26263).",
    lifespan=lifespan,
)

api = APIRouter(prefix="/api/v1", dependencies=[Depends(require_csrf_header)])
for module in (auth, institutes, uploads, students, verification, dashboard, audit):
    api.include_router(module.router)
app.include_router(api)


@app.get("/healthz", tags=["ops"])
def healthz() -> dict[str, str]:
    with SessionLocal() as db:
        db.execute(text("SELECT 1"))
    return {"status": "ok"}

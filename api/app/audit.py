"""Hash-chained audit trail.

Every entry stores the hash of the entry before it, and its own hash covers that
value plus all of its own fields. Changing or removing any past entry therefore
breaks every hash after it, which `verify_chain` detects.

Entries are written in the same transaction as the change they describe, so an
action and its audit record commit or roll back together.
"""

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AuditLog, User

GENESIS_HASH = "0" * 64
# Arbitrary constant; all audit writers take this advisory lock so the chain has one tail.
_CHAIN_LOCK_KEY = 0x41434144


def _digest(entry: AuditLog) -> str:
    body = {
        "prev_hash": entry.prev_hash,
        "occurred_at": entry.occurred_at.astimezone(UTC).isoformat(timespec="microseconds"),
        "actor_user_id": str(entry.actor_user_id) if entry.actor_user_id else None,
        "actor_role": entry.actor_role,
        "action": entry.action,
        "entity_type": entry.entity_type,
        "entity_id": entry.entity_id,
        "institute_id": str(entry.institute_id) if entry.institute_id else None,
        "payload": entry.payload,
    }
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def append(
    db: Session,
    *,
    action: str,
    entity_type: str,
    entity_id: uuid.UUID | str,
    actor: User | None = None,
    institute_id: uuid.UUID | None = None,
    payload: dict[str, Any] | None = None,
) -> AuditLog:
    """Add an entry to the chain. The caller commits.

    `payload` must contain only JSON values (str, int, bool, None, lists, dicts) so it
    hashes identically after a round trip through JSONB; avoid floats.
    """
    # Held until the surrounding transaction ends, so no other writer can read the
    # same tail and fork the chain.
    db.execute(select(func.pg_advisory_xact_lock(_CHAIN_LOCK_KEY)))
    prev_hash = db.scalar(select(AuditLog.hash).order_by(AuditLog.id.desc()).limit(1))

    entry = AuditLog(
        occurred_at=datetime.now(UTC),
        actor_user_id=actor.id if actor else None,
        actor_role=actor.role if actor else None,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id),
        institute_id=institute_id,
        payload=payload or {},
        prev_hash=prev_hash or GENESIS_HASH,
    )
    entry.hash = _digest(entry)
    db.add(entry)
    db.flush()
    return entry


@dataclass
class ChainReport:
    ok: bool
    entries_checked: int
    first_broken_id: int | None = None
    reason: str | None = None


def verify_chain(db: Session) -> ChainReport:
    expected_prev = GENESIS_HASH
    checked = 0
    for entry in db.scalars(
        select(AuditLog).order_by(AuditLog.id).execution_options(yield_per=1000)
    ):
        if entry.prev_hash != expected_prev:
            return ChainReport(False, checked, entry.id, "does not link to the previous entry")
        if _digest(entry) != entry.hash:
            return ChainReport(False, checked, entry.id, "contents do not match the stored hash")
        expected_prev = entry.hash
        checked += 1
    return ChainReport(True, checked)

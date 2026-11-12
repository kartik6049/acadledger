"""APAAR registry access.

Everything else in the app depends only on the `ApaarClient` protocol. Today the
only implementation is `MockApaarClient`; a real one (HTTP calls to the APAAR /
ABC service) can be added later and selected with the APAAR_CLIENT setting
without touching the validation pipeline.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from app.config import get_settings


class ApaarStatus(StrEnum):
    FOUND = "found"
    NOT_FOUND = "not_found"


@dataclass(frozen=True)
class ApaarLookup:
    apaar_id: str
    status: ApaarStatus


class ApaarUnavailableError(Exception):
    """The registry could not be reached; the caller should retry later."""


class ApaarClient(Protocol):
    def lookup_many(self, apaar_ids: Sequence[str]) -> dict[str, ApaarLookup]:
        """Look up well-formed (12-digit) APAAR IDs. Returns one result per distinct ID."""
        ...


# --- Verhoeff checksum, used only by the mock below ---------------------------------------

_D = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
    (1, 2, 3, 4, 0, 6, 7, 8, 9, 5),
    (2, 3, 4, 0, 1, 7, 8, 9, 5, 6),
    (3, 4, 0, 1, 2, 8, 9, 5, 6, 7),
    (4, 0, 1, 2, 3, 9, 5, 6, 7, 8),
    (5, 9, 8, 7, 6, 0, 4, 3, 2, 1),
    (6, 5, 9, 8, 7, 1, 0, 4, 3, 2),
    (7, 6, 5, 9, 8, 2, 1, 0, 4, 3),
    (8, 7, 6, 5, 9, 3, 2, 1, 0, 4),
    (9, 8, 7, 6, 5, 4, 3, 2, 1, 0),
)
_P = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
    (1, 5, 7, 6, 2, 8, 3, 0, 9, 4),
    (5, 8, 0, 3, 7, 9, 6, 1, 4, 2),
    (8, 9, 1, 6, 0, 4, 3, 5, 2, 7),
    (9, 4, 5, 3, 1, 2, 6, 8, 7, 0),
    (4, 2, 8, 6, 5, 7, 3, 9, 0, 1),
    (2, 7, 9, 3, 8, 0, 6, 4, 1, 5),
    (7, 0, 4, 6, 9, 1, 3, 2, 5, 8),
)
_INV = (0, 4, 3, 2, 1, 5, 6, 7, 8, 9)


def verhoeff_check_digit(digits: str) -> str:
    c = 0
    for i, ch in enumerate(reversed(digits)):
        c = _D[c][_P[(i + 1) % 8][int(ch)]]
    return str(_INV[c])


def verhoeff_is_valid(digits: str) -> bool:
    c = 0
    for i, ch in enumerate(reversed(digits)):
        c = _D[c][_P[i % 8][int(ch)]]
    return c == 0


class MockApaarClient:
    """Stand-in registry with a deterministic rule instead of real data.

    An ID counts as registered when its 12th digit is the Verhoeff check digit of
    the first 11. This is a convention of the mock so that test data can contain
    both "registered" and "unknown" IDs; it is NOT a property of real APAAR IDs.
    """

    def lookup_many(self, apaar_ids: Sequence[str]) -> dict[str, ApaarLookup]:
        return {
            apaar_id: ApaarLookup(
                apaar_id,
                ApaarStatus.FOUND if verhoeff_is_valid(apaar_id) else ApaarStatus.NOT_FOUND,
            )
            for apaar_id in set(apaar_ids)
        }


def get_apaar_client() -> ApaarClient:
    kind = get_settings().apaar_client
    if kind == "mock":
        return MockApaarClient()
    raise ValueError(f"Unknown APAAR_CLIENT {kind!r}")

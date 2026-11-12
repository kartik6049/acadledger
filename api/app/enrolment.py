"""The `programme_enrolment` materialised view: enrolment against approved intake.

One row per programme and academic year that has an approved intake, with the
number of students in the central repository counted against it. The AICTE
dashboard reads this view instead of counting students on every page load.

The view only changes when it is refreshed, so everything that changes its
inputs (committing an upload, setting an intake) refreshes it in the same
transaction. The dashboard is therefore never behind the data.
"""

from sqlalchemy import text
from sqlalchemy.orm import Session


def refresh_enrolment_view(db: Session) -> None:
    # CONCURRENTLY: people reading the dashboard are not blocked while it rebuilds
    db.execute(text("REFRESH MATERIALIZED VIEW CONCURRENTLY programme_enrolment"))

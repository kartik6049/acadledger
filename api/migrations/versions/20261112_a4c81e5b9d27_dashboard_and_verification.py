"""dashboard view and verification grants

Revision ID: a4c81e5b9d27
Revises: 712d117c381f
Create Date: 2026-11-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a4c81e5b9d27"
down_revision: str | None = "712d117c381f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("organisation", sa.String(length=200), nullable=True))

    op.create_table(
        "verification_grants",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("student_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lookup_count", sa.Integer(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_verification_grants_created_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["student_id"], ["students.id"], name=op.f("fk_verification_grants_student_id_students")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_verification_grants")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_verification_grants_token_hash")),
    )
    op.create_index(
        op.f("ix_verification_grants_student_id"), "verification_grants", ["student_id"]
    )

    # Enrolment against approved intake, per programme and year. See app/enrolment.py.
    op.execute(
        """
        CREATE MATERIALIZED VIEW programme_enrolment AS
        SELECT pi.programme_id,
               pi.academic_year,
               p.institute_id,
               pi.approved_intake,
               count(s.id)::integer AS enrolled
        FROM programme_intakes pi
        JOIN programmes p ON p.id = pi.programme_id
        LEFT JOIN students s
               ON s.programme_id = pi.programme_id AND s.academic_year = pi.academic_year
        GROUP BY pi.programme_id, pi.academic_year, p.institute_id, pi.approved_intake
        """
    )
    # a unique index is what allows REFRESH ... CONCURRENTLY
    op.execute(
        "CREATE UNIQUE INDEX uq_programme_enrolment "
        "ON programme_enrolment (programme_id, academic_year)"
    )
    op.execute("CREATE INDEX ix_programme_enrolment_year ON programme_enrolment (academic_year)")


def downgrade() -> None:
    op.execute("DROP MATERIALIZED VIEW programme_enrolment")
    op.drop_index(op.f("ix_verification_grants_student_id"), table_name="verification_grants")
    op.drop_table("verification_grants")
    op.drop_column("users", "organisation")

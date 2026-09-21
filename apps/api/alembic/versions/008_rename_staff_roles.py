"""Rename two staff roles: the set is now underwriter, medical_professional, dev.

Revision ID: 008
Revises: 007
Create Date: 2026-09-22

`senior_underwriter` becomes `medical_professional` and `admin` becomes `dev`.
What each role may do is unchanged; only the names move.

`ALTER TYPE ... RENAME VALUE` relabels the enum in place, so every existing
`users` row follows without being touched. Each rename is guarded, so running
this against a database that already has the new names does nothing.
`db/schema.sql` declares the new names, so a fresh database starts with them.
"""

from alembic import op

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def _rename(old: str, new: str) -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_enum e
                JOIN pg_type t ON t.oid = e.enumtypid
                WHERE t.typname = 'user_role' AND e.enumlabel = '{old}'
            ) THEN
                ALTER TYPE user_role RENAME VALUE '{old}' TO '{new}';
            END IF;
        END $$;
        """
    )


def upgrade() -> None:
    _rename("senior_underwriter", "medical_professional")
    _rename("admin", "dev")


def downgrade() -> None:
    _rename("medical_professional", "senior_underwriter")
    _rename("dev", "admin")

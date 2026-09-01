"""Add 'image' to evidence_file_type.

Revision ID: 003
Revises: 002
Create Date: 2026-09-01

A chest X-ray uploaded as PNG had to be filed as 'questionnaire', because the
type had no value for a plain image. That is a false statement on a record whose
whole purpose is to be auditable.

`db/schema.sql` now declares the value, so a database built from scratch already
has it — hence IF NOT EXISTS.
"""

from alembic import op

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ALTER TYPE ... ADD VALUE cannot be followed by a use of that value in the
    # same transaction, so it runs outside Alembic's.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE evidence_file_type ADD VALUE IF NOT EXISTS 'image' AFTER 'dicom'")

    # Existing rows were mislabelled by the bug this fixes: every non-DICOM
    # upload became 'questionnaire'. Only files that are actually images are
    # corrected, identified by the mime type recorded at intake.
    op.execute(
        "UPDATE evidence_files SET file_type = 'image' "
        "WHERE file_type = 'questionnaire' AND mime_type LIKE 'image/%'"
    )


def downgrade() -> None:
    # Postgres cannot remove a value from an enum, so the type keeps 'image'.
    # Move the rows back so nothing references it.
    op.execute("UPDATE evidence_files SET file_type = 'questionnaire' WHERE file_type = 'image'")

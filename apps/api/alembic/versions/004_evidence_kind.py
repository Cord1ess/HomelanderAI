"""Record what each piece of evidence is.

Revision ID: 004
Revises: 003
Create Date: 2026-09-21

Which model may read a file is decided by what the file *is*, and until now
nothing recorded that. The pipeline ran every arm over every file, so the retina
model scored chest X-rays at 98.8 out of 100 and, since the highest score
governs, won every application containing one.

`db/schema.sql` declares the column, so a fresh database already has it.
"""

from alembic import op

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE evidence_files ADD COLUMN IF NOT EXISTS evidence_kind VARCHAR(30)")

    # Existing rows: the arm they were linked to implies what they are, and
    # that link was made from the panel the operator chose at intake.
    op.execute(
        "UPDATE evidence_files ef SET evidence_kind = 'chest_xray' "
        "FROM model_arms ma WHERE ef.model_arm_id = ma.id AND ma.name = 'tb_xray'"
    )
    op.execute(
        "UPDATE evidence_files ef SET evidence_kind = 'fundus' "
        "FROM model_arms ma WHERE ef.model_arm_id = ma.id AND ma.name = 'eyepacs_dr'"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE evidence_files DROP COLUMN IF EXISTS evidence_kind")

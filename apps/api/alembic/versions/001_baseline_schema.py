"""001_baseline_schema

Revision ID: 001_baseline
Revises: 
Create Date: 2026-08-31 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '001_baseline'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Enums
    user_role = postgresql.ENUM('underwriter', 'senior_underwriter', 'admin', name='user_role')
    user_role.create(op.get_bind(), checkfirst=True)

    risk_tier = postgresql.ENUM('low', 'moderate', 'elevated', 'insufficient_evidence', name='risk_tier')
    risk_tier.create(op.get_bind(), checkfirst=True)

    underwriter_decision_type = postgresql.ENUM(
        'confirmed_fast_track', 'approved_with_adjustment', 'escalated_senior_review', 'requested_additional_evidence',
        name='underwriter_decision_type'
    )
    underwriter_decision_type.create(op.get_bind(), checkfirst=True)

    # 2. Tenants
    op.create_table(
        'tenants',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('subscription_tier', sa.String(50), nullable=False, server_default='standard'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # 3. Users
    op.create_table(
        'users',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), primary_key=True),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),
        sa.Column('full_name', sa.String(255), nullable=False),
        sa.Column('email', sa.String(255), nullable=False),
        sa.Column('password_hash', sa.String(255), nullable=False),
        sa.Column('role', sa.Enum('underwriter', 'senior_underwriter', 'admin', name='user_role', create_type=False), nullable=False, server_default='underwriter'),
        sa.Column('license_number', sa.String(100), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('tenant_id', 'email', name='uq_users_tenant_email'),
    )
    op.create_index('idx_users_tenant_id', 'users', ['tenant_id'])
    op.create_index('idx_users_email', 'users', ['email'])

    # 4. API Keys
    op.create_table(
        'api_keys',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), primary_key=True),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),
        sa.Column('key_hash', sa.String(255), nullable=False, unique=True),
        sa.Column('label', sa.String(100), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    )

    # 5. Applicants
    op.create_table(
        'applicants',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), primary_key=True),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),
        sa.Column('external_id', sa.String(100), nullable=False),
        sa.Column('age', sa.Integer(), nullable=False),
        sa.Column('sex', sa.String(10), nullable=False),
        sa.Column('smoking_status', sa.String(20), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('tenant_id', 'external_id', name='uq_applicants_tenant_external'),
    )

    # 6. Applications
    op.create_table(
        'applications',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), primary_key=True),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),
        sa.Column('applicant_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('applicants.id', ondelete='CASCADE'), nullable=False),
        sa.Column('product_type', sa.String(50), nullable=False),
        sa.Column('face_amount', sa.Numeric(12, 2), nullable=False),
        sa.Column('status', sa.String(30), nullable=False, server_default='pending'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table('applications')
    op.drop_table('applicants')
    op.drop_table('api_keys')
    op.drop_table('users')
    op.drop_table('tenants')
    op.execute('DROP TYPE IF EXISTS underwriter_decision_type')
    op.execute('DROP TYPE IF EXISTS risk_tier')
    op.execute('DROP TYPE IF EXISTS user_role')

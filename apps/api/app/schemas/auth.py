"""Pydantic v2 validation schemas for authentication and carrier onboarding."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from app.models.user import UserRole


class BaseSchema(BaseModel):
    """Base schema that accepts and outputs camelCase for React/TS frontend compatibility."""

    model_config = ConfigDict(
        from_attributes=True,
        alias_generator=to_camel,
        populate_by_name=True,
    )


class TenantSchema(BaseSchema):
    """Tenant carrier organization representation."""

    id: UUID
    name: str
    subscription_tier: str
    created_at: datetime


class UserSchema(BaseSchema):
    """User representation."""

    id: UUID
    tenant_id: UUID
    full_name: str
    email: str
    role: UserRole
    license_number: str | None = None
    created_at: datetime


class RegisterTenantSchema(BaseSchema):
    """Payload for onboarding a new carrier tenant + tenant admin."""

    tenant_name: str = Field(..., min_length=2, max_length=255)
    subscription_tier: str = Field(default="standard")
    admin_full_name: str = Field(..., min_length=2, max_length=255)
    admin_email: str
    admin_password: str = Field(..., min_length=8)
    license_number: str | None = None
    role: UserRole = Field(default=UserRole.ADMIN)


class UserLoginSchema(BaseSchema):
    """Payload for authenticating existing carrier users."""

    email: str
    password: str
    tenant_slug: str | None = None


class AuthResponseSchema(BaseSchema):
    """Response payload returning user and tenant details."""

    user: UserSchema
    tenant: TenantSchema


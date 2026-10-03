"""A client's portal sign-in, after intake: see it, email it again, or make a new one.

At intake the sign-in is emailed, or shown once to the operator. When the email
never arrived (mail not set up yet, a typo in the address, a server that
refused it) there was no way back to it. This page is that way back.

The password is never stored, so it cannot be shown again. "Again" always means
a new password: the old one stops working the moment a new one is made. It is
emailed when it can be, and shown once to the operator when it cannot.
"""

import asyncio
import re
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import mailer, outbox, persistence
from app.core.security import generate_password, hash_password
from app.db.session import get_db
from app.deps import Principal, current_principal
from app.models import Applicant, Application, EmailLog, UserRole
from app.routers.access import access_to, can_see
from app.schemas.auth import BaseSchema

router = APIRouter(tags=["Client sign-in"])

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class EmailLogSchema(BaseSchema):
    kind: str
    recipient: str
    subject: str
    # sent | not_configured | failed
    status: str
    created_at: datetime


class ClientSignInSchema(BaseSchema):
    application_id: UUID
    reference: str
    client_name: str | None = None
    portal_id: str | None = None
    email: str | None = None
    # False when the client's details are the owner's to hand out and this
    # person has not been given them: the id and address are masked.
    details_visible: bool = True
    mail_configured: bool = False
    emails: list[EmailLogSchema] = Field(default_factory=list)
    # Present once, right after a new password was made and could not be emailed.
    password: str | None = None
    emailed: bool | None = None


class ReissueIn(BaseSchema):
    # A corrected address, when the old one was wrong. Left out keeps it.
    email: str | None = Field(default=None, max_length=255)
    # Email the new sign-in when an address and a mail server allow it.
    send_email: bool = True


def _mask_email(email: str | None) -> str | None:
    if not email or "@" not in email:
        return email
    name, domain = email.split("@", 1)
    return f"{name[:1]}{'•' * max(2, len(name) - 1)}@{domain}"


def _mask_id(portal_id: str | None) -> str | None:
    if not portal_id:
        return portal_id
    return portal_id[:3] + "•" * max(0, len(portal_id) - 5) + portal_id[-2:]


async def _load(
    db: AsyncSession, application_id: UUID, principal: Principal
) -> tuple[Application, Applicant]:
    if principal.role == UserRole.MEDICAL_PROFESSIONAL.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="A client's sign-in is handled by the underwriter, not a doctor.",
        )
    row = (
        await db.execute(
            select(Application, Applicant)
            .join(Applicant, Applicant.id == Application.applicant_id)
            .where(Application.id == application_id, Application.tenant_id == principal.tenant_id)
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such application.")
    return row[0], row[1]


async def _describe(
    db: AsyncSession, principal: Principal, application: Application, applicant: Applicant
) -> ClientSignInSchema:
    state, _ = (await access_to(db, principal, [applicant.id]))[applicant.id]
    visible = can_see(state)
    emails = (
        (
            await db.execute(
                select(EmailLog)
                .where(EmailLog.application_id == application.id)
                .order_by(EmailLog.created_at.desc())
                .limit(20)
            )
        )
        .scalars()
        .all()
    )
    return ClientSignInSchema(
        application_id=application.id,
        reference=applicant.external_ref,
        client_name=applicant.name,
        portal_id=applicant.portal_id if visible else _mask_id(applicant.portal_id),
        email=applicant.email if visible else _mask_email(applicant.email),
        details_visible=visible,
        mail_configured=mailer.configured(),
        emails=[
            EmailLogSchema(
                kind=e.kind,
                recipient=e.recipient if visible else (_mask_email(e.recipient) or ""),
                subject=e.subject,
                status=e.status,
                created_at=e.created_at,
            )
            for e in emails
        ],
    )


@router.get(
    "/applications/{application_id}/client-sign-in",
    response_model=ClientSignInSchema,
    summary="The client's portal sign-in and every email sent to them",
)
async def get_client_sign_in(
    application_id: UUID,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(current_principal),
) -> ClientSignInSchema:
    application, applicant = await _load(db, application_id, principal)
    return await _describe(db, principal, application, applicant)


@router.post(
    "/applications/{application_id}/client-sign-in",
    response_model=ClientSignInSchema,
    summary="Make a new portal password, and email it when possible",
)
async def reissue_client_sign_in(
    application_id: UUID,
    payload: ReissueIn,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(current_principal),
) -> ClientSignInSchema:
    application, applicant = await _load(db, application_id, principal)

    if payload.email is not None:
        address = payload.email.strip().lower()
        if address and not _EMAIL.match(address):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="That does not look like an email address.",
            )
        applicant.email = address or None

    password = generate_password()
    applicant.password_hash = hash_password(password)

    emailed = False
    if payload.send_email and applicant.email:
        emailed = await asyncio.to_thread(
            mailer.send_credentials,
            applicant.email,
            applicant.name or "",
            applicant.external_ref,
            applicant.portal_id,
            password,
        )
        outbox.record(
            db,
            application.tenant_id,
            application.id,
            "portal_sign_in",
            applicant.email,
            f"Your application {applicant.external_ref}",
            emailed,
        )

    await persistence.append_audit(
        db,
        tenant_id=application.tenant_id,
        application_id=application.id,
        actor_user_id=principal.user_id,
        event_type="portal_sign_in_reissued",
        payload={"emailed": emailed, "email_changed": payload.email is not None},
    )
    await db.commit()

    out = await _describe(db, principal, application, applicant)
    out.emailed = emailed
    # Shown once, to the operator, only when it did not go by email.
    out.password = None if emailed else password
    if not out.details_visible:
        # The operator hands this over, so the id they hand over must be whole.
        out.portal_id = applicant.portal_id
    return out

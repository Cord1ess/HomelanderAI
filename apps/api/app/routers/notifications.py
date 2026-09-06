"""In-app notifications for staff.

Phase 1 is in-app only: no email, no SMS. These go to underwriters, never to
applicants — applicants are not users of this system.
"""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.deps import Principal, current_principal
from app.models import Applicant, Application, Notification, NotificationStatus
from app.schemas.application import NotificationSchema

router = APIRouter(tags=["Notifications"])


@router.get("/notifications", response_model=list[NotificationSchema])
async def list_notifications(
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(current_principal),
) -> list[NotificationSchema]:
    """Newest first, for the signed-in user only."""
    rows = (
        await db.execute(
            select(Notification, Applicant.external_ref)
            .outerjoin(Application, Application.id == Notification.application_id)
            .outerjoin(Applicant, Applicant.id == Application.applicant_id)
            .where(
                Notification.tenant_id == principal.tenant_id,
                Notification.user_id == principal.user_id,
            )
            .order_by(Notification.created_at.desc())
            .limit(limit)
        )
    ).all()

    return [
        NotificationSchema(
            id=row.id,
            message=row.message,
            notification_type=row.notification_type.value,
            application_id=row.application_id,
            reference=reference,
            created_at=row.created_at,
            read_at=row.read_at,
        )
        for row, reference in rows
    ]


@router.post("/notifications/{notification_id}/read", response_model=NotificationSchema)
async def mark_read(
    notification_id: UUID,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(current_principal),
) -> NotificationSchema:
    row = (
        await db.execute(
            select(Notification).where(
                Notification.id == notification_id,
                Notification.user_id == principal.user_id,
            )
        )
    ).scalar_one_or_none()

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No such notification."
        )

    # Re-reading something already read is not an error, so this is idempotent.
    if row.read_at is None:
        row.read_at = datetime.now(UTC)
        row.status = NotificationStatus.READ
        await db.commit()
        await db.refresh(row)

    return NotificationSchema(
        id=row.id,
        message=row.message,
        notification_type=row.notification_type.value,
        application_id=row.application_id,
        created_at=row.created_at,
        read_at=row.read_at,
    )

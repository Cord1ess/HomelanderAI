"""A record of every email the platform tried to send.

`mailer` sends and reports whether the server took the message; this module
writes down that it was tried, to whom, and how it went. Never the body: a
sign-in email carries a password.

The log is what lets an operator see that a client's sign-in never arrived
(mail not set up yet, or the server refused it) and send it again.
"""

import asyncio
import logging
from collections.abc import Callable
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app import mailer
from app.db.session import AsyncSessionLocal
from app.models import EmailLog

log = logging.getLogger(__name__)


def status_for(ok: bool) -> str:
    if ok:
        return "sent"
    return "failed" if mailer.configured() else "not_configured"


def record(
    db: AsyncSession,
    tenant_id: UUID,
    application_id: UUID | None,
    kind: str,
    to: str,
    subject: str,
    ok: bool,
) -> None:
    """Add the log row to a session the caller is about to commit."""
    db.add(
        EmailLog(
            tenant_id=tenant_id,
            application_id=application_id,
            kind=kind,
            recipient=to,
            subject=subject[:255],
            status=status_for(ok),
        )
    )


async def send_logged(
    tenant_id: UUID,
    application_id: UUID | None,
    kind: str,
    to: str,
    subject: str,
    send: Callable[..., bool],
    *args,
) -> bool:
    """Send on a worker thread and log it on a session of its own.

    For background tasks, which run after the request's session is closed.
    Never raises: a mail problem must not surface as a server error.
    """
    try:
        ok = await asyncio.to_thread(send, *args)
    except Exception:
        log.exception("Sending %s to %s failed", kind, to)
        ok = False
    try:
        async with AsyncSessionLocal() as db:
            record(db, tenant_id, application_id, kind, to, subject, ok)
            await db.commit()
    except Exception:
        log.exception("Could not log the %s email to %s", kind, to)
    return ok

"""Outgoing mail to applicants.

Two messages: the portal sign-in at intake, and a short notice when a decision
is recorded. Standard-library `smtplib`, so there is no mail dependency to
install and no provider account to hold.

**Sending can fail and the product must not.** Every function here returns
whether the message went, never raises, and the callers have a fallback: at
intake the operator is shown the credentials instead, because the client is
sitting in front of them.

**The decision notice carries no outcome.** Email is not a confidential
channel, so it says only that there is something to see and links to the portal,
where the applicant signs in to read it.
"""

import logging
import smtplib
from email.message import EmailMessage

from app.config import settings

log = logging.getLogger(__name__)

# Long enough for a slow mail server, short enough that an operator with a
# client opposite is not left watching a spinner.
_TIMEOUT_SECONDS = 8


def configured() -> bool:
    return bool(settings.smtp_host)


def send(to: str, subject: str, body: str, *, redact: str | None = None) -> bool:
    """Send one plain-text message. True if the server accepted it.

    `redact` is a secret inside the body, replaced before anything is logged.
    A generated password in a log file is a credential leak whether or not the
    mail was delivered.
    """
    if not configured():
        shown = body.replace(redact, "[not logged]") if redact else body
        log.info("Mail is not configured; this message was not sent.\nTo: %s\n%s", to, shown)
        return False

    message = EmailMessage()
    message["From"] = settings.smtp_from
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=_TIMEOUT_SECONDS) as smtp:
            if settings.smtp_starttls:
                smtp.starttls()
            if settings.smtp_user:
                smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(message)
        return True
    except (smtplib.SMTPException, OSError) as exc:
        # The address and subject, never the body.
        log.error("Could not send mail to %s (%s): %s", to, subject, exc)
        return False


def send_credentials(to: str, name: str, reference: str, portal_id: str, password: str) -> bool:
    body = (
        f"Hello {name or 'there'},\n\n"
        f"Your application {reference} has been received.\n\n"
        "You can follow its progress, see when to expect an answer, and find out "
        "if any documents are still needed, here:\n\n"
        f"  {settings.portal_url}\n\n"
        f"  Portal ID: {portal_id}\n"
        f"  Password:  {password}\n\n"
        "Keep these somewhere safe. We cannot show you the password again.\n"
    )
    return send(to, f"Your application {reference}", body, redact=password)


def send_decision_notice(to: str, name: str, reference: str) -> bool:
    body = (
        f"Hello {name or 'there'},\n\n"
        f"There is an update on your application {reference}.\n\n"
        f"Sign in to see it: {settings.portal_url}\n"
    )
    return send(to, f"An update on your application {reference}", body)


def send_doctor_message(to: str, name: str, reference: str, urgency: str, message: str) -> bool:
    """A doctor's words to the client, about their health rather than the policy.

    The doctor wrote it; nothing is added but a greeting and a way back to the
    portal. An urgent one says so in the subject, because that is the line a
    person reads before deciding whether to open it today.
    """
    subject = (
        f"Urgent: a doctor's advice about your application {reference}"
        if urgency == "urgent"
        else f"A doctor's note about your application {reference}"
    )
    body = (
        f"Dear {name or 'applicant'},\n\n"
        "A doctor reviewing your application has written to you:\n\n"
        f"{message}\n\n"
        f"You can also read this on your client portal: {settings.portal_url}\n"
        "This message is about your health; it is not a decision on your policy.\n"
    )
    return send(to, subject, body)


def send_policy_notice(to: str, name: str, reference: str) -> bool:
    """A change to their policy: issued, cancelled. Like the decision notice it
    says only that there is something to see; the portal says what."""
    body = (
        f"Hello {name or 'there'},\n\n"
        f"There is an update about your policy for application {reference}.\n\n"
        f"Sign in to see it: {settings.portal_url}\n"
    )
    return send(to, f"An update about your policy ({reference})", body)


def send_test(to: str, company: str) -> bool:
    """The administrator checking that mail works, from the settings screen."""
    body = (
        f"This is a test message from {company} on Homelander AI.\n\n"
        "If you are reading it, outgoing mail is set up correctly: clients will "
        "receive their portal sign-in and updates by email.\n"
    )
    return send(to, "Homelander AI: test message", body)

"""Where an email actually goes.

Mirrors app/ai/providers/base.py's LLMProvider Protocol: one interface, one
real implementation, and test doubles that never touch the network.
"""
from __future__ import annotations

import logging
import smtplib
from dataclasses import dataclass, field
from email.message import EmailMessage
from typing import Protocol

log = logging.getLogger(__name__)


class Transport(Protocol):
    def send(
        self,
        *,
        from_addr: str,
        to_addr: str,
        subject: str,
        body: str,
        headers: dict[str, str] | None = None,
    ) -> None: ...


class ConsoleTransport:
    """Logs the message and sends nothing. The email_mode="console" default (pytest/CI)."""

    def send(
        self,
        *,
        from_addr: str,
        to_addr: str,
        subject: str,
        body: str,
        headers: dict[str, str] | None = None,
    ) -> None:
        log.info(
            "EMAIL (console) from=%s to=%s subject=%r headers=%s\n%s",
            from_addr,
            to_addr,
            subject,
            headers or {},
            body,
        )


@dataclass
class MemoryTransport:
    """Records every send in-process instead of sending it. For tests."""

    sent: list[dict[str, object]] = field(default_factory=list)

    def send(
        self,
        *,
        from_addr: str,
        to_addr: str,
        subject: str,
        body: str,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.sent.append(
            {"from": from_addr, "to": to_addr, "subject": subject, "body": body, "headers": dict(headers or {})}
        )


class SmtpTransport:
    """Real SMTP via the stdlib. Serves both a local Mailpit sandbox and a live
    provider (e.g. Gmail) — the only difference between them is host/port/
    credentials, set in app/config.py, never a second code path.
    """

    def __init__(self, *, host: str, port: int, user: str = "", password: str = "", starttls: bool = False) -> None:
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.starttls = starttls

    def send(
        self,
        *,
        from_addr: str,
        to_addr: str,
        subject: str,
        body: str,
        headers: dict[str, str] | None = None,
    ) -> None:
        msg = EmailMessage()
        msg["From"] = from_addr
        msg["To"] = to_addr
        msg["Subject"] = subject
        for key, value in (headers or {}).items():
            msg[key] = value
        msg.set_content(body)

        with smtplib.SMTP(self.host, self.port, timeout=10) as smtp:
            if self.starttls:
                smtp.starttls()
            if self.user:
                smtp.login(self.user, self.password)
            smtp.send_message(msg)


_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "mailpit", "uniassist-mailpit"}


def is_local_host(host: str) -> bool:
    """True for Mailpit and other loopback sandboxes, where nothing leaves the
    machine and the recipient-domain guard in app/notify/mailer.py can relax.
    """
    return host.strip().lower() in _LOCAL_HOSTS


def get_transport() -> Transport:
    """The transport for the configured email_mode. Built fresh per call: sends
    are infrequent, so there is no connection-reuse benefit worth caching, and
    a cached connection would only get in the way of tests that reconfigure
    settings between calls.
    """
    from app.config import settings  # deferred: keeps this module import-cheap for tests

    if settings.email_mode == "smtp":
        return SmtpTransport(
            host=settings.smtp_host,
            port=settings.smtp_port,
            user=settings.smtp_user,
            password=settings.smtp_password,
            starttls=settings.smtp_starttls,
        )
    return ConsoleTransport()

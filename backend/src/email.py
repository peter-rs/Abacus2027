import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, parseaddr
from typing import Literal, Optional

from src.config import env_bool, optional_env, optional_int_env, require_env

AccountType = Literal["admin", "student"]

def get_smtp_port() -> int:
    return optional_int_env("SMTP_PORT", 587)

def normalize_from_address(raw_from: str) -> str:
    name, addr = parseaddr(raw_from)

    if addr and " " not in addr:
        return raw_from

    parts = raw_from.split()
    email_part = next((part for part in reversed(parts) if "@" in part), "")
    display_name = " ".join(part for part in parts if part != email_part).strip()

    if not email_part:
        raise RuntimeError("SMTP_FROM is not a valid email address.")

    return formataddr((display_name, email_part))

def send_email(
    to_email: str,
    subject: str,
    text_body: str,
    *,
    from_email: Optional[str] = None,
    cc_email: Optional[str] = None,
) -> None:
    """
    This module does not try to discover or load .env.backend.
    The process environment must already be configured by Docker, systemd, etc.

    Required:
      SMTP_HOST
      SMTP_USERNAME
      SMTP_PASSWORD

    Optional:
      SMTP_PORT      (defaults to 587 if blank or unset)
      SMTP_FROM      (defaults to SMTP_USERNAME if blank or unset)
      SMTP_USE_TLS   (defaults to true)
      SMTP_USE_SSL   (defaults to false)
    """
    smtp_host = require_env("SMTP_HOST")
    smtp_port = get_smtp_port()
    smtp_user = require_env("SMTP_USERNAME")
    smtp_pass = require_env("SMTP_PASSWORD").replace(" ", "")

    smtp_from_raw = (from_email or optional_env("SMTP_FROM") or smtp_user).strip()
    smtp_from = normalize_from_address(smtp_from_raw)

    use_tls = env_bool("SMTP_USE_TLS", True)
    use_ssl = env_bool("SMTP_USE_SSL", False)

    if use_tls and use_ssl:
        raise RuntimeError("Invalid SMTP config: SMTP_USE_TLS and SMTP_USE_SSL cannot both be true.")

    msg = EmailMessage()
    msg["From"] = smtp_from
    msg["To"] = to_email
    if cc_email:
        msg["Cc"] = cc_email
    msg["Subject"] = subject
    msg.set_content(text_body)

    context = ssl.create_default_context()

    if use_ssl:
        server = smtplib.SMTP_SSL(smtp_host, smtp_port, context=context, timeout=30)
    else:
        server = smtplib.SMTP(smtp_host, smtp_port, timeout=30)
        server.ehlo()
        if use_tls:
            server.starttls(context=context)
            server.ehlo()

    try:
        server.login(smtp_user, smtp_pass)
        server.send_message(msg)
    finally:
        server.quit()

def send_password_link_email(
    to_email: str,
    link: str,
    account_type: AccountType,
    cc_email: Optional[str] = None,
) -> None:
    """
    Sends a password setup/reset link.
    Token signing and expiration are handled in auth.py.
    """
    if account_type == "admin":
        subject = "Abacus: Reset your teacher password"
        intro = "You requested a teacher password reset for Abacus."
    else:
        subject = "Abacus: Set or reset your student password"
        intro = "Use this link to set or reset your Abacus student password."

    body = (
        f"{intro}\n\n"
        f"Open this link to continue:\n"
        f"{link}\n\n"
        f"If you did not request this, you can ignore this email.\n"
        f"This link expires automatically.\n"
    )

    send_email(
        to_email=to_email,
        subject=subject,
        text_body=body,
        cc_email=cc_email,
    )
from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage


def _smtp_from_addr() -> str:
    email = (os.environ.get("BOT_EMAIL") or "").strip()
    return (os.environ.get("SMTP_FROM") or email).strip()


def _smtp_connection_params() -> tuple[str, int, bool, bool]:
    host = (os.environ.get("SMTP_HOST") or "smtp.gmail.com").strip()
    port = int(os.environ.get("SMTP_PORT", "465"))
    use_ssl = os.environ.get("SMTP_USE_SSL", "true").lower() in ("1", "true", "yes")
    use_tls = os.environ.get("SMTP_USE_TLS", "false").lower() in ("1", "true", "yes")
    return host, port, use_ssl, use_tls


def smtp_configured() -> bool:
    """Lê sempre do ambiente em tempo de chamada (evita valores vazios por ordem de import)."""
    email = (os.environ.get("BOT_EMAIL") or "").strip()
    password = os.environ.get("BOT_PASSWORD") or ""
    host, _, _, _ = _smtp_connection_params()
    return bool(email and password and host and _smtp_from_addr())


def send_plain_email(*, to_addr: str, subject: str, body: str) -> None:
    dry = os.environ.get("DIGEST_DRY_RUN", "false").lower() in ("1", "true", "yes")
    if dry:
        print(f"[DIGEST_DRY_RUN] Para: {to_addr}\nAssunto: {subject}\n---\n{body}\n---")
        return

    if not smtp_configured():
        raise RuntimeError(
            "E-mail não configurado: defina BOT_EMAIL e BOT_PASSWORD (ex.: no .env do worker / Docker)"
        )

    bot_email = (os.environ.get("BOT_EMAIL") or "").strip()
    bot_password = os.environ.get("BOT_PASSWORD") or ""
    smtp_from = _smtp_from_addr()
    host, port, use_ssl, use_tls = _smtp_connection_params()

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = smtp_from
    msg["To"] = to_addr
    msg.set_content(body)

    if use_ssl:
        with smtplib.SMTP_SSL(host, port, timeout=60) as smtp:
            smtp.login(bot_email, bot_password)
            smtp.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=60) as smtp:
            if use_tls:
                smtp.starttls()
            smtp.login(bot_email, bot_password)
            smtp.send_message(msg)

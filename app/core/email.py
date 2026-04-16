import smtplib
from email.message import EmailMessage

from app.core.config import get_settings

settings = get_settings()


def send_password_reset_email(to_email: str, reset_link: str) -> None:
    """Send password reset email via SMTP if configured.

    If SMTP is not configured, this function prints the reset link so
    developers can still test the flow locally.
    """
    if not settings.SMTP_HOST or not settings.SMTP_USERNAME or not settings.SMTP_PASSWORD:
        print(f"[DEV] Password reset link for {to_email}: {reset_link}")
        return

    msg = EmailMessage()
    msg["Subject"] = "Recuperacion de contrasena"
    msg["From"] = settings.SMTP_SENDER_EMAIL
    msg["To"] = to_email
    msg.set_content(
        "Recibimos una solicitud para recuperar tu contrasena.\n"
        f"Usa este enlace para restablecerla:\n{reset_link}\n\n"
        "Si no solicitaste este cambio, ignora este correo."
    )

    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=20) as server:
        if settings.SMTP_USE_TLS:
            server.starttls()
        server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
        server.send_message(msg)

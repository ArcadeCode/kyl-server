import smtplib
from email.message import EmailMessage
from os import getenv


def send_reset_password_email(to_email: str, reset_token: str) -> None:
    """
    Send a password-reset email over SMTP. Raises on failure (caller decides
    whether/how to surface it — see routes/sign.py).
    """
    base_url = getenv("RESET_PASSWORD_BASE_URL")
    link = f"{base_url}?token={reset_token}"

    msg = EmailMessage()
    msg["Subject"] = "Réinitialisation de votre mot de passe KYL"
    msg["From"] = getenv("SMTP_FROM_ADDRESS")
    msg["To"] = to_email
    msg.set_content(
        f"Bonjour,\n\nUne demande de réinitialisation de mot de passe a été "
        f"effectuée. Cliquez sur le lien suivant (valable 30 minutes) :\n\n{link}\n\n"
        f"Si vous n'êtes pas à l'origine de cette demande, ignorez cet e-mail."
    )

    host = getenv("SMTP_HOST")
    port = int(getenv("SMTP_PORT", "587"))
    use_tls = getenv("SMTP_USE_TLS", "true").lower() == "true"

    with smtplib.SMTP(host, port) as server:
        if use_tls:
            server.starttls()
        server.login(getenv("SMTP_USERNAME"), getenv("SMTP_PASSWORD"))
        server.send_message(msg)
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


def send(
    smtp_username: str,
    smtp_password: str,
    recipient: str,
    subject: str,
    body: str,
    smtp_host: str = "smtp.gmail.com",
    smtp_port: int = 465,
) -> None:
    """
    Send notification email via Gmail SMTP.

    Args:
        smtp_username: Gmail address for authentication
        smtp_password: Gmail app-specific password
        recipient: Email address to send to
        subject: Email subject line
        body: Email body text (plain text)
    """
    try:
        logging.info("Preparing email - From: %s, To: %s", smtp_username, recipient)
        logging.info("Email subject: %s", subject)

        # Create email message
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = smtp_username
        msg["To"] = recipient

        # Add plain text part
        text_part = MIMEText(body, "plain")
        msg.attach(text_part)

        recipients = [r.strip() for r in recipient.split(",") if r.strip()]
        if not recipients:
            raise ValueError("At least one recipient email must be provided")

        logging.info("Connecting to SMTP server (%s:%s)...", smtp_host, smtp_port)
        with smtplib.SMTP_SSL(smtp_host, smtp_port) as server:
            logging.info("Logging in to Gmail...")
            server.login(smtp_username, smtp_password)
            logging.info("Sending email...")
            server.sendmail(smtp_username, recipients, msg.as_string())

        logging.info("Email notification sent successfully to %s", recipient)
    except Exception as e:
        logging.error("Failed to send email notification: %s", e)
        raise

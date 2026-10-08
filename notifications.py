"""Notification layer (Gmail in the Google build: GmailApp.sendEmail).

Locally every email is written to the NOTIFICATIONS outbox so the demo can show exactly what
each person would have received. If SMTP_HOST (and friends) are set as environment variables,
the message is ALSO sent through SMTP - useful for a real Gmail demo using an app password.
"""
import os
import smtplib
from email.message import EmailMessage

from . import clock


def _smtp_send(to_email, subject, body):
    host = os.environ.get("SMTP_HOST")
    if not host:
        return None
    try:
        msg = EmailMessage()
        msg["From"] = os.environ.get("SMTP_FROM", os.environ.get("SMTP_USER", "automation@novabrands.in"))
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.set_content(body)
        with smtplib.SMTP(host, int(os.environ.get("SMTP_PORT", "587")), timeout=10) as s:
            s.starttls()
            if os.environ.get("SMTP_USER"):
                s.login(os.environ["SMTP_USER"], os.environ.get("SMTP_PASSWORD", ""))
            s.send_message(msg)
        return "Sent via SMTP"
    except Exception as exc:  # noqa: BLE001 - never let email failure break the workflow
        return f"SMTP failed: {exc}"


def send_notification(conn, campaign_id, ntype, to_user, subject, body):
    status = "Sent"
    smtp = _smtp_send(to_user["Email"], subject, body)
    if smtp:
        status = smtp
    conn.execute(
        "INSERT INTO notifications(Timestamp, Campaign_ID, Notification_Type, To_Name, To_Email, Subject, Body, Channel, Status)"
        " VALUES (?,?,?,?,?,?,?,?,?)",
        (clock.ts(), campaign_id, ntype, to_user["Name"], to_user["Email"], subject, body,
         "Gmail (simulated)", status),
    )


def inr(n):
    """Indian digit grouping: 180000 -> ₹1,80,000."""
    try:
        n = int(round(float(n)))
    except (TypeError, ValueError):
        return "₹0"
    sign = "-" if n < 0 else ""
    s = str(abs(n))
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        s = ",".join(parts) + "," + tail
    return f"{sign}₹{s}"

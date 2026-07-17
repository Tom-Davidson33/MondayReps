"""
Delivery via Outlook COM (uses your authenticated profile — no SMTP relay approval
needed). Defaults to saving a Draft so you review before sending.
"""
from __future__ import annotations
import config


def deliver(html: str, subject: str, to: list[str], cc: list[str] | None = None,
            draft_only: bool = True) -> None:
    try:
        import win32com.client as win32
    except ImportError:
        print("[send] pywin32 not installed — skipping Outlook step (preview only).")
        return

    outlook = win32.Dispatch("Outlook.Application")
    mail = outlook.CreateItem(0)  # olMailItem
    mail.Subject = subject
    mail.To = "; ".join(to)
    if cc:
        mail.CC = "; ".join(cc)
    mail.HTMLBody = html
    if draft_only:
        mail.Save()               # -> Outlook Drafts
        print("[send] saved to Drafts for review.")
    else:
        mail.Send()
        print("[send] sent.")


def alert_owner(subject: str, body: str) -> None:
    """Plain-text heads-up to Tom when the report is held for staleness."""
    deliver(f"<pre>{body}</pre>", subject, [config.OWNER_EMAIL], draft_only=False)

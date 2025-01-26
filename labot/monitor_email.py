#! /usr/bin/env python3
"""Monitor for E-Mail."""
from __future__ import annotations

from pathlib import Path
import os
from exchangelib import DELEGATE, Account, Credentials

if __name__ == "__main__":
    email = os.getenv("EMAIL")
    password = os.getenv("PASSWORD")
    if not email or not password:
        raise ValueError("EMAIL and PASSWORD environment variables must be set.")

    # Set up credentials and account
    credentials = Credentials(username=email, password=password)
    account = Account(primary_smtp_address=email, credentials=credentials, autodiscover=True, access_type=DELEGATE)

    print(f"Connected to {account.primary_smtp_address}'s inbox.")

    inbox = account.inbox
    inbox.refresh()
    new_emails = inbox.filter(is_read=False)

    for email in new_emails:
        if email.subject.startswith("Evaluationsauswertung zur Veranstaltung"):

            raise Exception(f"Email with subject '{email.subject}' detected!")

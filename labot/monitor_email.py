#! /usr/bin/env python3
"""Monitor for E-Mail."""
from __future__ import annotations

import os

from exchangelib import Account
from exchangelib import Credentials
from exchangelib import DELEGATE
from github import Github
from jinja2 import Environment
from jinja2 import FileSystemLoader


def create_github_issue(repo, title, body, assignees=None):
    try:
        issue = repo.create_issue(title=title, body=body, assignees=assignees)

        print(f"Issue created successfully! URL: {issue.html_url}")
    except Exception as e:
        print(f"Failed to create issue: {e}")


def issue_exists(repo, title):
    """
    Check if an issue with the given title already exists in the repository.

    :param repo: Repository object
    :param title: Title of the issue to check
    :return: True if the issue exists, False otherwise
    """
    issues = repo.get_issues(state="open")
    for issue in issues:
        if issue.title == title:
            return True
    return False


if __name__ == "__main__":
    email = os.getenv("EMAIL")
    password = os.getenv("PASSWORD")
    handbook_repo = "digital-work-lab/handbook"

    if not email or not password:
        raise ValueError("EMAIL and PASSWORD environment variables must be set.")

    credentials = Credentials(username=email, password=password)
    account = Account(
        primary_smtp_address=email,
        credentials=credentials,
        autodiscover=True,
        access_type=DELEGATE,
    )

    print(f"Connected to {account.primary_smtp_address}'s inbox.")

    inbox = account.inbox
    inbox.refresh()
    new_emails = inbox.filter(is_read=False)

    token = os.getenv("GITHUB_TOKEN")
    if not token:
        raise ValueError("GITHUB_TOKEN environment variable must be set.")

    g = Github(token)
    repo = g.get_repo(handbook_repo)

    template_vars = {}

    env = Environment(loader=FileSystemLoader("templates"))
    template = env.get_template("course_evaluation_issue.md")

    for email in new_emails:
        if email.subject.startswith("Evaluationsauswertung zur Veranstaltung"):

            title = email.subject
            if issue_exists(repo, title):
                print(f"Issue with title '{title}' already exists. Skipping creation.")
                continue

            # body = (
            #     "📧 We received the evaluation results.\n"
            #     "- [ ] Upload the PDF [here](https://github.com/digital-work-lab/handbook/tree/main/assets/evaluations)\n\n"
            #     "Add them to the [courses](https://github.com/digital-work-lab/handbook/tree/main/_courses):\n"
            #     "- [ ] Add participation and overall score to _data/data.json (badges will be updated automatically)\n"
            #     "- [ ] Add student comments to the page of evaluations\n"
            #     "- [ ] Add suggestions for improvement to the issue\n"
            # )
            body = template.render(template_vars)
            assignees = ["geritwagner"]

            create_github_issue(repo, title, body, assignees)

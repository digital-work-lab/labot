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

import labot.thesis_utils


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


def teaching_evaluations(email, repo):
    title = email.subject
    if issue_exists(repo, title):
        print(f"Issue with title '{title}' already exists. Skipping creation.")
        return

    body = template.render(template_vars)
    assignees = ["geritwagner"]

    try:
        issue = repo.create_issue(title=title, body=body, assignees=assignees)

        print(f"Issue created successfully! URL: {issue.html_url}")
    except Exception as e:
        print(f"Failed to create issue: {e}")


def start_thesis_registration(account, email):
    try:
        file_path = ""
        # Check if the email has attachments
        for attachment in email.attachments:
            if hasattr(attachment, "content") and attachment.name.endswith(".docx"):
                file_path = attachment.name

                # Save the attachment
                with open(file_path, "wb") as f:
                    f.write(attachment.content)

        if not file_path:
            # TODO : notify via e-mail
            return

        registration = {"repository": "NA", "word_file": file_path}
        registration = labot.thesis_utils.append_infos_from_word(registration)
        # TODO : validate
        # TODO : rename
        # new_filename = f"{registration['name']}_{registration['student_id']}.docx"

        # upload word file in "digital-work-lab/theses-confidential" repository
        # Check if file already exists in the repo
        # existing_file = repo.get_contents(TARGET_PATH)

        # # Update the file
        # repo.update_file(
        #     TARGET_PATH,
        #     "Updating file via GitHub Actions",
        #     open(FILE_PATH, "r").read(),
        #     existing_file.sha,
        #     branch="main",  # Change to the correct branch
        # )

        # email confirmation: GW auf cc

        # title = email.subject
        # if issue_exists(repo, title):
        #     print(f"Issue with title '{title}' already exists. Skipping creation.")
        #     return

        # body = """
        # **Thesis Registration**

        # **Student Name:**
        # **Student ID:**
        # **Thesis Title:**
        # **Thesis Type:**
        # **Supervisor:**
        # **Second Supervisor:**
        # **Start Date:**
        # **End Date:**
        # **Status:**
        # **Grade:**
        # **Notes:**
        # """
        # assignees = ["geritwagner"]

        # try:
        #     issue = repo.create_issue(title=title, body=body, assignees=assignees)

        #     print(f"Issue created successfully! URL: {issue.html_url}")
        # except Exception as e:
        #     print(f"Failed to create issue: {e}")
    except Exception as e:
        print(f"An error occurred: {e}")

    body = f"""
    **Thesis Registration**

    **Student Name:** {registration['student']}
    **Student ID:** {registration['student_id']} """

    # send a report to gerit.wagner@uni-bamberg.de
    account.send_email(
        subject=f"AW: {email.subject}",
        body=body,
        to_recipients=["gerit.wagner@uni-bamberg.de"],
    )


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
    handbook_repo = g.get_repo(handbook_repo)

    template_vars = {}

    env = Environment(loader=FileSystemLoader("labot/templates"))
    template = env.get_template("course_evaluation_issue.md.j2")

    for email in new_emails:
        if email.subject.startswith("teaching_evaluations zur Veranstaltung"):
            teaching_evaluations(email, handbook_repo)
        if (
            email.subject == "[digital-work-labot]: Start registration"
            or email.subject == "AW: AW: Masterarbeit Anmeldung"
        ):
            start_thesis_registration(account, email)

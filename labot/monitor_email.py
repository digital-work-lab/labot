#! /usr/bin/env python3
"""Monitor for E-Mail."""
from __future__ import annotations

import os
import re

from docx import Document
from exchangelib import Account
from exchangelib import Credentials
from exchangelib import DELEGATE
from github import Github
from jinja2 import Environment
from jinja2 import FileSystemLoader


def _extract_text_from_word(file_path: str) -> str:
    try:
        document = Document(file_path)
        text = []

        for paragraph in document.paragraphs:
            text.append(paragraph.text)

        return "\n".join(text)

    except Exception as e:
        return f"An error occurred: {e}"


def _clean_name(raw_name: str) -> str:
    parts = raw_name.split(",")
    if len(parts) == 2:
        last_name = parts[0].replace(" ", "").strip()
        first_name = parts[1].strip()
        return f"{last_name}, {first_name}"
    return raw_name.strip()


def _extract_information(text: str) -> dict:

    name_pattern = r"Name:\s*([^\n]+)"
    student_id_pattern = r"Matrikelnummer:\s*(\d+)"
    topic_pattern = r"Englisch \(zur Aufnahme ins Zeugnis\):\n([^\n]+)"
    date_pattern_1 = r"Bamberg, den\s*(\d{2}\.\d{2}\.\d{4})"
    date_pattern_2 = r"Bamberg, den\s*([\d-]+)"
    work_time_pattern = r"(\d+)\s*Monate"
    zulassung_date_pattern = r"Die Zulassung erfolgte am:\s*(\d{2}\.\d{2}\.\d{4})"

    name_match = re.search(name_pattern, text)
    student_id_match = re.search(student_id_pattern, text)
    date_match = re.search(date_pattern_1, text)
    if date_match:
        # convert to YYYY-MM-DD
        date = date_match.group(1)
        date = re.sub(r"(\d{2})\.(\d{2})\.(\d{4})", r"\3-\2-\1", date)
    else:
        date_match = re.search(date_pattern_2, text)
    topic_match = re.search(topic_pattern, text)
    work_time_match = re.search(work_time_pattern, text)
    zulassung_date_match = re.search(zulassung_date_pattern, text)

    raw_name = name_match.group(1).strip() if name_match else None
    name = _clean_name(raw_name) if raw_name else None
    student_id = student_id_match.group(1) if student_id_match else None
    topic = topic_match.group(1).strip() if topic_match else None
    date = date_match.group(1) if date_match else None
    date = re.sub(r"(\d{2})\.(\d{2})\.(\d{4})", r"\3-\2-\1", date) if date else None
    work_time = work_time_match.group(1) if work_time_match else "NA"
    zulassung_date = zulassung_date_match.group(1) if zulassung_date_match else "NA"

    level = "bachelor" if "bachelorarbeit" in text.lower() else "master"

    return {
        "student": name,
        "student_id": student_id,
        "Topic": topic,
        "Date": date,
        "Work Time": work_time + " months",
        "Zulassung Date": zulassung_date,
        "Level": level,
    }


def append_infos_from_word(registration: dict) -> dict:

    extracted_text = _extract_text_from_word(registration["word_file"])
    info = _extract_information(extracted_text)
    registration.update(info)
    return registration


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
        # TODO : validate e-mail (sender: @stud-uni-bamberg.de)
        registration = {"repository": "NA", "word_file": file_path}
        registration = append_infos_from_word(registration)
        # TODO : validate
        # TODO : rename
        # new_filename = f"{registration['name']}_{registration['student_id']}.docx"

        target_path = f"registrations/{file_path}"
        # upload word file in "digital-work-lab/theses-confidential" repository
        repo = g.get_repo("digital-work-lab/theses-confidential")
        repo.create_file(
            target_path,
            "Upload registration file",
            open(file_path).read(),
            target_path,
            branch=registration["student"],
        )
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

        title = email.subject
        if issue_exists(repo, title):
            print(f"Issue with title '{title}' already exists. Skipping creation.")
            return

        body = f"""
        **Thesis Registration**

        **Student Name:** {registration['student']}
        **Student ID:** {registration['student_id']}
        **Thesis Title:** {registration['Topic']}
        **Date:** {registration['Date']}
        **Work Time:** {registration['Work Time']}

Branch: https://github.com/digital-work-lab/theses-confidential/tree/{registration['student']}

"""
        assignees = ["geritwagner"]

        try:
            issue = repo.create_issue(title=title, body=body, assignees=assignees)

            print(f"Issue created successfully! URL: {issue.html_url}")
        except Exception as e:
            print(f"Failed to create issue: {e}")
    except Exception as e:
        print(f"An error occurred: {e}")

    # body = f"""
    # **Thesis Registration**

    # **Student Name:** {registration['student']}
    # **Student ID:** {registration['student_id']} """

    # # send a report
    # email_message = Message(
    #     account=account,
    #     folder=account.sent,
    #     subject=f"AW: {email.subject}",
    #     body=body,
    #     to_recipients=["gerit.wagner@uni-bamberg.de"],
    # )
    # email_message.send()


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

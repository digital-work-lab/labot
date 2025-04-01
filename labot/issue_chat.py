#! /usr/bin/env python3
"""Labot issue chat."""
import os
import re
from datetime import datetime
from datetime import timedelta
from pathlib import Path

import requests
from exchangelib import Account
from exchangelib import Credentials
from exchangelib import FileAttachment
from exchangelib import Message
from git import Repo
from github import Github
from github.Issue import Issue

import labot.monitor_email
import labot.utils

# def onboard(local_repo: Repo, github_repo: Github, issue: Issue) -> None:
# Check: issue authored by geritwagner, otherwise: exit
# get the text of the issue
# determine username (@digital-work-labot onboard USERNAME)
# create agenda repository based on template https://github.com/digital-work-lab/agenda_template
# add geritwagner and Stella1234-design as contributors
# create an issue in the agenda repository with the checklist (sholud be in templates dir)


def onboard(
    local_repo: Repo, github_repo: Github, issue: Issue, comment_text: str
) -> None:
    """
    Onboard a new user by creating an agenda repository from a template,
    adding contributors, and creating an onboarding issue.
    """

    # Determine the username from the issue text
    match = re.search(r"@digital-work-labot onboard (\S+)", comment_text)
    if not match:
        print("No username found in issue text. Exiting.")
        return
    new_user = match.group(1)

    # Define necessary repository information
    template_repo = "digital-work-lab/agenda_template"
    org_name = "digital-work-lab"
    new_repo_name = f"agenda_gerit_{new_user}"

    # Create a new repository from the template
    github_client = Github(os.getenv("GITHUB_TOKEN"))
    org = github_client.get_organization(org_name)

    template = github_client.get_repo(template_repo)
    new_repo = org.create_repo_from_template(
        name=new_repo_name,
        repo=template,
        private=True,
        description=f"✅ Agenda repository for {new_user}",
    )
    # new_repo = org.create_repo(
    #     name=new_repo_name,
    #     private=True,
    #     description=f"Agenda repository for {new_user}",
    #     template_repo=github_client.get_repo(template_repo),
    #     has_issues=True,
    #     has_wiki=False,
    # )

    # Update the repository with new topics
    new_repo.replace_topics(["agenda"])

    # Add contributors
    contributors = ["geritwagner", new_user, "Stella1234-design"]
    for contributor in contributors:
        new_repo.add_to_collaborators(contributor, permission="push")
    repo_html_url = new_repo.html_url
    # Retrieve checklist template using Jinja
    template = labot.utils.get_template("onboarding_checklist.md.j2")
    checklist_issue_body = template.render(username=new_user, repo_url=repo_html_url)

    # Create an issue in the new agenda repository
    checklist_issue = new_repo.create_issue(
        title="Onboarding Checklist",
        body=checklist_issue_body,
        # Do not set assignee to avoid 422 error (repo invitation not yet accepted)
        # assignee=new_user,
    )

    # Comment in the original issue with the agenda repo link and checklist issue link
    issue.create_comment(
        f"Onboarding user: {new_user}\n\nAgenda Repository: {new_repo.html_url}\n\nChecklist Issue: {checklist_issue.html_url}\n\n "
        f"@{new_user}, you should have received invitations to the repository via e-mail. \n\n"
    )

    # Close the original onboarding issue
    issue.edit(state="closed")


def new_semester(
    local_repo: Repo, github_repo: Github, issue: Issue, comment_text: str
) -> None:
    issue.create_comment("I will create a branch and set up a new semester for you 🛠️")
    # create branch "new_semester" in local_repo
    local_repo.git.checkout("main")
    local_repo.git.pull()
    local_repo.git.checkout("-b", "new_semester")
    # in the docs dir, iterate over md-files containing "teaching_note" in the title and replace "- [x] " with "- [ ] "
    repo_path = Path(local_repo.working_tree_dir)  # Get the repo directory
    for file in repo_path.glob("docs/*teaching_note*.md"):
        with open(file) as f:
            content = f.read()
        content = content.replace("- [x] ", "- [ ] ")
        with open(file, "w") as f:
            f.write(content)

    # commit and push changes
    local_repo.git.add(".")
    local_repo.index.commit("Reset teaching notes for new semester")
    local_repo.git.push("origin", "new_semester")
    # create a pull request
    pr = github_repo.create_pull(
        title="Create new semester",
        body="Reset the teaching notes for the new semester.",
        base="main",
        head="new_semester",
    )
    # link to the pull request in the issue
    issue_number = issue.number
    pr.add_to_labels(f"linked-to-issue-{issue_number}")

    issue.create_comment(f"I have created a pull request here: {pr.html_url} 🚀")

    # TODO : regularly create the "New semester" issue with notes and the @labot command at the end
    # TODO: create a new issue:
    "Evaluation WS 2024/25 (improvements for SS 2025)"


def thesis_registration_accept(
    local_repo: Repo, github_repo: Github, issue: Issue, comment_text: str
) -> None:
    def extract_branch_name(issue_body: str) -> str:
        """
        Extracts the branch name from the issue body by matching the GitHub branch URL.
        """
        match = re.search(
            r"https://github\.com/digital-work-lab/theses-confidential/tree/([\w\-_]+)",
            issue_body,
        )
        if match:
            return match.group(1)  # Extracted branch name
        return None  # No match found

    def extract_file_name(issue_body: str) -> str:
        match = re.search(r"\s*([\w\-\/_]+\.docx)", issue_body)
        if match:
            return match.group(1)
        else:
            return None

    branch_name = extract_branch_name(issue.body)
    if not branch_name:
        issue.create_comment(
            "I'm sorry, I couldn't find the branch name in the issue body."
        )
        return

    file_name = extract_file_name(issue.body)
    if not file_name:
        print(issue.body)
        issue.create_comment(
            "I'm sorry, I couldn't find the file name in the issue body."
        )
        return
    GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
    # CLONE_DIR = "/tmp/theses-confidential"
    # GITHUB_REPO_URL = f"https://x-access-token:{GITHUB_TOKEN}@github.com/digital-work-lab/theses-confidential.git"

    # if not os.path.exists(CLONE_DIR):
    #     Repo.clone_from(
    #         GITHUB_REPO_URL,
    #         CLONE_DIR,
    #         branch=branch_name,
    #         depth=1,
    #     )
    # else:
    #     print(f"✅ Repository already cloned: {CLONE_DIR}")

    # # ✅ Step 2: Access the file directly
    # local_path = os.path.join(CLONE_DIR, file_name)

    # file_content = github_repo.get_contents(file_name, ref=branch_name)
    # decoded_content = base64.b64decode(file_content.content)

    # local_path = os.path.join("/tmp", os.path.basename(file_name))  # Save to /tmp
    # with open(local_path, "wb") as f:
    #     f.write(decoded_content)

    # GitHub API URL
    URL = f"https://api.github.com/repos/digital-work-lab/theses-confidential/contents/{file_name}?ref={branch_name}"

    # Headers for authentication
    HEADERS = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3.raw",
    }

    # Download file
    response = requests.get(URL, headers=HEADERS)

    if response.status_code == 200:
        # Save file locally
        local_path = os.path.basename(file_name)
        with open(local_path, "wb") as file:
            file.write(response.content)
        print(f"✅ File downloaded: {local_path}")
    else:
        print(
            f"❌ Failed to download file. HTTP {response.status_code}: {response.text}"
        )

    # ✅ Debugging: Check if the file was saved correctly
    print(f"🔍 File exists: {os.path.exists(local_path)}")
    if os.path.exists(local_path):
        print(f"🔍 File size: {os.path.getsize(local_path)} bytes")

        # Check file type (Linux/macOS only, useful for debugging)
        try:
            import subprocess

            result = subprocess.run(
                ["file", local_path], capture_output=True, text=True
            )
            print(f"🔍 File type: {result.stdout.strip()}")
        except Exception as e:
            print(f"⚠️ Unable to check file type: {e}")

    # Ensure the file is valid before opening
    if not os.path.exists(local_path) or os.path.getsize(local_path) == 0:
        raise FileNotFoundError(f"❌ File not found or is empty: {local_path}")

    print(f"✅ File successfully saved at: {local_path}")

    registration = {"repository": "NA", "word_file": local_path}
    print(os.path.exists(local_path))

    registration = labot.monitor_email.append_infos_from_word(registration)
    print(registration)
    if registration["student"] is None:
        issue.create_comment("I'm sorry, I couldn't find the student name in the file.")
        return
    deadline_submission = datetime.strptime(
        registration["date_of_registration"], "%Y-%m-%d"
    ) + timedelta(int(registration["work_time_months"]) * 30)
    registration["deadline_submission"] = deadline_submission.strftime("%Y-%m-%d")
    registration["work_time_days"] = int(registration["work_time_months"]) * 30
    registration["expected_review_completion"] = (
        deadline_submission + timedelta(days=90)
    ).strftime("%Y-%m-%d")

    # get the branch name from the issue body, match "https://github.com/digital-work-lab/theses-confidential/tree/..."
    # get the filenames in github_repo (theses folder)
    files = github_repo.get_contents("theses", ref=branch_name)
    # files are 001_name.md, 002_name.md, ... - I need the next number
    next_number = str(len(files) + 1).zfill(3)
    # create a new file in the github_repo

    template = labot.utils.get_template("theses_details.md.j2")
    content = template.render(registration=registration)
    thesis_filename = f"theses/{next_number}_{registration['student'].replace(',', '').replace(' ', '_')}.md"
    github_repo.create_file(
        thesis_filename,
        "Thesis registration",
        content=content,
        branch=branch_name,
    )

    issue_number = issue.number
    # create pull request
    pr = github_repo.create_pull(
        title=f"Thesis registration for {registration['student']}",
        body=f"TODO : send e-mail to examination office: ADD .\nPlease check the registration details for {registration['student']} and merge this pull request.\n\n🔗 **Issue:** [#{issue_number}](https://github.com/digital-work-lab/theses-confidential/issues/{issue_number})",
        base="main",
        head=branch_name,
    )

    pull_request_link = pr.html_url
    issue.create_comment(
        f"I created the [thesis file](https://github.com/digital-work-lab/theses-confidential/blob/{branch_name}/{thesis_filename}?plain=1) 📚\n\nPlease check and merge the [pull request]({pull_request_link})"
    )

    # Call this function at the end of thesis_registration_accept()
    send_thesis_registration_email_exchange(local_path, registration["student"])

    issue.create_comment("Sent the e-mail to the examination office")
    issue.create_comment(
        "- [ ] TODO (in issue_chat.py): merge pull request and close issue"
    )


def send_thesis_registration_email_exchange(file_path: str, student_name: str):
    """
    Sends an email via Microsoft Exchange with the attached thesis registration document.

    :param file_path: Path to the thesis registration Word document.
    :param student_name: Name of the student for whom the thesis registration is being sent.
    """

    # Load credentials (securely stored in environment variables)
    EMAIL_ADDRESS = os.getenv("EMAIL")
    EMAIL_PASSWORD = os.getenv("PASSWORD")
    RECIPIENT_EMAIL = "gerit.wagner@posteo.de"
    CC_EMAILS = ["gerit.wagner@uni-bamberg.de"]

    # Exchange authentication
    credentials = Credentials(username=EMAIL_ADDRESS, password=EMAIL_PASSWORD)
    account = Account(EMAIL_ADDRESS, credentials=credentials, autodiscover=True)

    # Create email
    subject = "Anmeldung Abschlussarbeit"
    body = f"""Liebe Frau Schick,

anbei übersende ich Ihnen die ausgefüllte Themenbestätigung für {student_name}.

Mit besten Grüßen

Gerit Wagner
"""

    msg = Message(
        account=account,
        folder=account.sent,  # Save to "Sent Items"
        subject=subject,
        body=body,
        to_recipients=[RECIPIENT_EMAIL],
        cc_recipients=CC_EMAILS,
    )

    # Attach the thesis document
    with open(file_path, "rb") as f:
        attachment = FileAttachment(name=os.path.basename(file_path), content=f.read())
        msg.attach(attachment)

    # Send the email
    msg.send()
    print("✅ Email sent successfully via Exchange")


def comment(local_repo: Repo, github_repo: Github, event_data: dict) -> None:
    issue_nr = event_data["issue"].get("number")
    issue = github_repo.get_issue(issue_nr)
    comment_author = event_data.get("comment", {}).get("user", {}).get("login")
    comment_text = event_data.get("comment", {}).get("body")
    if "@digital-work-labot" not in comment_text:
        return
    if comment_author != "geritwagner":
        # later: others
        return

    COMMANDS = {
        "@digital-work-labot onboard": onboard,
        "@digital-work-labot create new semester": new_semester,
        "@digital-work-labot accept thesis registration": thesis_registration_accept,
    }

    for command in COMMANDS:
        if comment_text.startswith(command):
            COMMANDS[command](local_repo, github_repo, issue, comment_text)
            break
    else:
        issue.create_comment(
            f"I'm sorry, I don't understand this command. \n Options:\n {COMMANDS.keys()}"
        )
        return


def new_issue(local_repo: Repo, github_repo: Github, event_data: dict) -> None:
    issue = event_data["issue"]
    issue_title = issue.get("title")
    issue.get("body")
    issue_author = issue.get("user").get("login")
    if issue_author != "geritwagner":
        # later: others
        return

    COMMANDS = {}

    for match_string, function in COMMANDS.items():
        if issue_title.startswith(match_string):
            function(local_repo, github_repo, issue)

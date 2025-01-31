#! /usr/bin/env python3
"""Labot issue chat."""
import re
from datetime import datetime
from datetime import timedelta
from pathlib import Path

from git import Repo
from github import Github
from github import Issue

import labot.monitor_email
import labot.utils


def new_semester(local_repo: Repo, github_repo: Github, issue: Issue) -> None:
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
    local_repo: Repo, github_repo: Github, issue: Issue
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
        match = re.search(r"\*\*File:\*\*: ([\.\w\s\/-]+)$", issue_body)
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
        issue.create_comment(
            "I'm sorry, I couldn't find the file name in the issue body."
        )
        return

    registration = {"repository": "NA", "word_file": file_name}
    registration = labot.monitor_email.append_infos_from_word(registration)
    print(registration)
    if registration["student"] is None:
        issue.create_comment("I'm sorry, I couldn't find the student name in the file.")
        return
    deadline_submission = datetime.strptime(
        registration["date_of_registration"], "%Y-%m-%d"
    ) + timedelta(int(registration["work_time_months"]) * 30)
    registration["deadline_submission"] = deadline_submission.strftime("%Y-%m-%d")
    registration["work_time_days"] = registration["work_time_months"] * 30
    registration["expected_review_completion"] = (
        deadline_submission + timedelta(days=90)
    ).strftime("%Y-%m-%d")

    issue.create_comment("I will register your thesis 📚")
    # get the branch name from the issue body, match "https://github.com/digital-work-lab/theses-confidential/tree/..."
    # get the filenames in github_repo (theses folder)
    files = github_repo.get_contents("theses", ref=branch_name)
    # files are 001_name.md, 002_name.md, ... - I need the next number
    next_number = len(files) + 1
    # create a new file in the github_repo

    template = labot.utils.get_template("theses_details.md.j2")
    content = template.render(registration)
    github_repo.create_file(
        f"theses/{next_number}_{registration['name']}.md",
        "Thesis registration",
        content=content,
        branch=branch_name,
    )

    # create student file in /theses


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
        "@digital-work-labot create new semester": new_semester,
        "@digital-work-labot accept thesis registration": thesis_registration_accept,
    }

    if comment_text in COMMANDS:
        COMMANDS[comment_text](local_repo, github_repo, issue)
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

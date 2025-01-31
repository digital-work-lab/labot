#! /usr/bin/env python3
"""Labot issue chat."""
from github import Github
from github import Issue


def new_semester(issue: Issue) -> None:
    issue.create_comment(
        "Creating a new semester is not yet implemented. Please be patient."
    )


def main(github_repo: Github, event_data: dict) -> None:
    issue_nr = event_data["issue"]
    issue = github_repo.get_issue(issue_nr)
    comment_author = event_data.get("comment", {}).get("user", {}).get("login")
    comment_text = event_data.get("comment", {}).get("body")
    if "@digital-work-labot" not in comment_text:
        return
    if comment_author != "geritwagner":
        # later: others
        return

    COMMANDS = {"@digital-work-labot create new semester": new_semester}

    if comment_text in COMMANDS:
        COMMANDS[comment_text](issue)
    else:
        issue.create_comment(
            f"I'm sorry, I don't understand this command. \n Options:\n {COMMANDS.keys()}"
        )
        return

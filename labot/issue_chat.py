#! /usr/bin/env python3
"""Labot issue chat."""
from git import Repo
from github import Github
from github import Issue


def new_semester(local_repo: Repo, github_repo: Github, issue: Issue) -> None:
    issue.create_comment("I will create a branch and set up a new semester for you 🛠️")
    # create branch "new_semester" in local_repo
    local_repo.git.checkout("main")
    local_repo.git.pull()
    local_repo.git.checkout("-b", "new_semester")
    # in the docs dir, iterate over md-files containing "teaching_note" in the title and replace "- [x] " with "- [ ] "
    for file in local_repo.glob("docs/*teaching_note*.md"):
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


def main(local_repo: Repo, github_repo: Github, event_data: dict) -> None:
    issue_nr = event_data["issue"].get("number")
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
        COMMANDS[comment_text](local_repo, github_repo, issue)
    else:
        issue.create_comment(
            f"I'm sorry, I don't understand this command. \n Options:\n {COMMANDS.keys()}"
        )
        return

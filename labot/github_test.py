#! /usr/bin/env python3
"""GitHub interface for Labot."""
import requests


def respond_to_comment(issue_number, comment_body, repo, token):
    """Responds to a comment on an issue using the GitHub API."""
    url = f"https://api.github.com/repos/{repo}/issues/{issue_number}/comments"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
    }
    payload = {"body": comment_body}

    response = requests.post(url, headers=headers, json=payload)
    if response.status_code == 201:
        print("Successfully responded to the comment!")
    else:
        print(f"Failed to respond: {response.status_code}, {response.text}")


def github_issue(params) -> str:

    print("Called github_issue")

    response_message = "Thank you for your comment! :tada:"

    if params["event_name"] == "issue_comment" and params["action"] == "created":
        print("Responding to a new comment...")
        respond_to_comment(
            params["issue_number"], response_message, params["repo"], params["token"]
        )
    else:
        print("No action required for this event.")

    return "Called"

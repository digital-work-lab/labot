#! /usr/bin/env python3
"""Repository checks."""
import sys
import os
import requests

# Set up GitHub API URL and token
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")  # GitHub token should be set in the environment variable
REPO_OWNER, REPO_NAME = os.getenv("GITHUB_REPOSITORY").split("/")  # Get owner/repo from the GitHub environment

BASE_URL = "https://api.github.com"
HEADERS = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json"
}

def get_repo_tags(owner, repo_name):
    """Fetch the tags of the repository."""
    url = f"{BASE_URL}/repos/{owner}/{repo_name}/tags"
    response = requests.get(url, headers=HEADERS)

    if response.status_code != 200:
        print(f"Error fetching tags: {response.json()}")
        sys.exit(1)

    tags = response.json()
    return [tag['name'] for tag in tags]

def get_repo_topics(owner, repo_name):
    """Fetch the topics of the repository."""
    url = f"{BASE_URL}/repos/{owner}/{repo_name}/topics"
    response = requests.get(url, headers=HEADERS)

    if response.status_code != 200:
        print(f"Error fetching topics: {response.json()}")
        sys.exit(1)

    topics = response.json().get('names', [])
    return topics

def main():
    """Main function."""
    tags = get_repo_tags(REPO_OWNER, REPO_NAME)
    topics = get_repo_topics(REPO_OWNER, REPO_NAME)
    
    print(f"Repository '{REPO_NAME}' tags: {tags}")
    print(f"Repository '{REPO_NAME}' topics: {topics}")
    
    sys.exit(0)

if __name__ == "__main__":
    main()

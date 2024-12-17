#! /usr/bin/env python3
"""Repository checks."""
import sys
import os
import requests
import subprocess
from github import Github

# Set up GitHub API URL and token
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")  # GitHub token should be set in the environment variable
REPO_OWNER, REPO_NAME = os.getenv("GITHUB_REPOSITORY").split("/")  # Get owner/repo from the GitHub environment

VALID = True
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

def _colrev_sync_references():

    # Authenticate using a GitHub token
    g = Github(GITHUB_TOKEN)

    # Get the repository
    repo = g.get_repo(f"{REPO_OWNER}/{REPO_NAME}")

    BRANCH_NAME = "colrev_update"
    # Create a new branch (if needed)
    base = repo.get_branch("main")
    repo.create_git_ref(ref=f"refs/heads/{BRANCH_NAME}", sha=base.commit.sha)

    # Run the colrev-sync command
    try:
        # Run the colrev-sync command and capture the output
        result = subprocess.run(
            ['colrev-sync'],
            check=True,  # Raise an exception if the command fails
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True  # Ensure the output is captured as text (not bytes)
        )
        
        # Print the standard output and error (if any)
        print("Output:\n", result.stdout)
        if result.stderr:
            print("Error:\n", result.stderr)
            
    except subprocess.CalledProcessError as e:
        print(f"Error running colrev-sync: {e}")
        print("Output:\n", e.stdout)
        print("Error:\n", e.stderr)


    # Create a pull request
    pr = repo.create_pull(
        title="New Pull Request",
        body="This is an automated PR created by Python script",
        head=BRANCH_NAME,
        base="main"
    )
    print(f"Pull Request created: {pr.html_url}")

def run_research_repo_checks():
    """Run checks specific to research repositories."""
    global VALID
    print("Running research repository checks...")

    makefile_path = "Makefile"  # Adjust if the Makefile is in a subdirectory

    # Check if Makefile exists
    if not os.path.isfile(makefile_path):
        print("No Makefile found in the repository.")
        VALID = False
    else:
        # Check if 'make pdf' rule exists in the Makefile
        with open(makefile_path, 'r') as makefile:
            makefile_contents = makefile.read()
            if "pdf" not in makefile_contents:
                print("'make pdf' rule not found in Makefile.")
                VALID = False

    if not os.path.isfile("paper.md"):
        print("No 'paper.md' file found in the repository.")
        VALID = False

    _colrev_sync_references()

def run_teaching_repo_checks():
    """Run checks specific to teaching repositories."""

    # Require a reset_course.yml workflow

    workflows_url = f"{BASE_URL}/repos/{REPO_OWNER}/{REPO_NAME}/actions/workflows"
    response = requests.get(workflows_url, headers=HEADERS)

    if response.status_code != 200:
        print(f"Error fetching workflows: {response.json()}")
        VALID = False
    
    workflows = response.json().get('workflows', [])
    workflow_names = [workflow['name'] for workflow in workflows]

    if ".github/workflows/reset_course.yml" not in workflow_names:
        print("No 'reset_course.yml' workflow found.")
        VALID = False


def main():
    """Main function."""
    tags = get_repo_tags(REPO_OWNER, REPO_NAME)
    topics = get_repo_topics(REPO_OWNER, REPO_NAME)
    
    print(f"Repository '{REPO_NAME}' topics: {topics}")

    if "research" in topics:
        run_research_repo_checks()
    if "teaching-material" in topics:
        run_teaching_repo_checks()


    if VALID:
        sys.exit(0)
    else:
        sys.exit(1)

if __name__ == "__main__":
    main()

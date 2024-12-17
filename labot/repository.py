#! /usr/bin/env python3
"""Repository checks."""
import sys
import os
import requests
import subprocess
from github import Github
from git import Repo
from datetime import datetime
import pkgutil
import hashlib
from pathlib import Path

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

def _update_labot_file():
    # Define the file paths
    # labot_local_file = os.path.join(os.path.dirname(__file__), "labot.yml")
    # labot_package_file = pkg_resources.resource_filename('labot', 'labot/labot.yml')

    labot_local_file = Path(".github/workflows/labot.yml")
    labot_package_data = pkgutil.get_data("labot", "data/labot.yml")

    # Function to compute file hash
    def compute_file_hash(file_path):
        with open(file_path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()

    # Compare the local file content with package data
    labot_package_hash = hashlib.sha256(labot_package_data).hexdigest()
    labot_local_hash = compute_file_hash(labot_local_file)

    if labot_local_hash != labot_package_hash:
        print("Files differ. Replacing and committing changes.")
        
        # write labot_package_data to labot_local_file
        with open(labot_local_file, "wb") as f:
            f.write(labot_package_data)

        # Initialize the repository using gitpython
        repo = Repo(os.getcwd())

        # Check for untracked files or changes
        repo.git.add(labot_local_file)  # Stage the file for commit

        # print current branch and git status
        print(f"Current branch: {repo.active_branch}")
        print(repo.git.status())

        # Commit the change
        repo.index.commit("Update labot.yml file")

        # Push the changes to the main branch
        origin = repo.remotes.origin
        origin.push("main")

        print("Changes pushed to main.")
    else:
        print("Files are identical. No action taken.")

def _colrev_sync_references():


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

    repo = Repo(os.getcwd())
    # Check if there are any changes before creating the PR
    if repo.is_dirty(untracked_files=True):
        # Get the repository

        # should be colrev-update-2024-12-17-12-00-00
        new_branch = f"colrev-update-{datetime.now().strftime('%Y-%m-%d-%H-%M-%S')}"

        if new_branch not in repo.heads:
            new_branch_ref = repo.create_head(new_branch, repo.head.commit)  # Create the new branch from the current commit
            new_branch_ref.checkout()  # Checkout the new branch
            print(f"New branch '{new_branch}' created and checked out.")
        else:
            new_branch_ref = repo.heads[new_branch]
            new_branch_ref.checkout()
            print(f"Branch '{new_branch}' already exists. Checked out.")

        # Push the new branch to GitHub
        origin = repo.remotes.origin
        origin.push(new_branch)
        print(f"Branch '{new_branch}' pushed to GitHub.")
        # add all changes
        repo.git.add("--all")

        # Create a commit for the changes
        repo.index.commit("Sync changes using colrev-sync")

        # Push the changes to the new branch again
        origin.push(new_branch)
        print(f"Changes pushed to {new_branch}.")
        # Authenticate using a GitHub token
        g = Github(GITHUB_TOKEN)
        repo_name = f"{REPO_OWNER}/{REPO_NAME}"
        repo_github = g.get_repo(repo_name)

        # Create a pull request
        pr = repo_github.create_pull(
            title="ColRev Sync",
            body="This PR was created using the colrev-sync command.",
            head=new_branch,
            base="main"
        )
        print(f"Pull Request created: {pr.html_url}")

        # switch to main
        repo.heads.main.checkout()
    else:
        print("No changes found in the branch. Skipping PR creation.")
        return


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

    _update_labot_file()

    if VALID:
        sys.exit(0)
    else:
        sys.exit(1)

if __name__ == "__main__":
    main()

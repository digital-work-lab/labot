#! /usr/bin/env python3
"""Repository checks."""
import hashlib
import os
import pkgutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import colrev.loader.load_utils
import requests
from git import Repo
from github import Github

# Set up GitHub API URL and token
GITHUB_TOKEN = os.getenv(
    "GITHUB_TOKEN"
)  # GitHub token should be set in the environment variable
REPO_OWNER, REPO_NAME = os.getenv("GITHUB_REPOSITORY").split(
    "/"
)  # Get owner/repo from the GitHub environment

VALID = True
BASE_URL = "https://api.github.com"
HEADERS = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json",
}


def check_github_token_permissions():
    """Check if the GITHUB_TOKEN has permissions to create pull requests and issues."""
    url = f"{BASE_URL}/repos/{REPO_OWNER}/{REPO_NAME}"
    response = requests.get(url, headers=HEADERS)

    if response.status_code != 200:
        print(f"Error checking repository access: {response.json()}")
        sys.exit(1)

    repo_data = response.json()
    print(repo_data.get("permissions", {}))

    if not repo_data.get("permissions", {}).get("pull"):
        print(
            "GITHUB_TOKEN does not have permission to create pull requests. Add key from labot-repository-workflows.md as MY_PAT_TOKEN repository secret."
        )
        sys.exit(1)

    if not repo_data.get("permissions", {}).get("push"):
        print(
            "GITHUB_TOKEN does not have permission to create issues (push)). Add key from labot-repository-workflows.md as MY_PAT_TOKEN repository secret."
        )
        sys.exit(1)

    print("GITHUB_TOKEN has the required permissions.")


def get_repo_tags(owner, repo_name):
    """Fetch the tags of the repository."""
    url = f"{BASE_URL}/repos/{owner}/{repo_name}/tags"
    response = requests.get(url, headers=HEADERS)

    if response.status_code != 200:
        print(f"Error fetching tags: {response.json()}")
        sys.exit(1)

    tags = response.json()
    return [tag["name"] for tag in tags]


def get_repo_topics(owner, repo_name):
    """Fetch the topics of the repository."""
    url = f"{BASE_URL}/repos/{owner}/{repo_name}/topics"
    response = requests.get(url, headers=HEADERS)

    if response.status_code != 200:
        print(f"Error fetching topics: {response.json()}")
        sys.exit(1)

    topics = response.json().get("names", [])
    return topics


def _update_labot_file():
    # Define the file paths
    labot_local_file = os.path.join(os.path.dirname(__file__), "labot.yml")

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

        issue_title = "Suggestion: Update the YAML file"
        issue_body = f"""It seems that the YAML file in the repository needs to be updated.
Please copy the [latest version](https://github.com/digital-work-lab/labot/blob/main/labot/data/labot.yml) and update it [here](https://github.com/{REPO_OWNER}/{REPO_NAME}/edit/main/.github/workflows/labot.yml)."""

        # Initialize the GitHub API client
        g = Github(GITHUB_TOKEN)

        try:
            # Get the repository
            repo_name = f"{REPO_OWNER}/{REPO_NAME}"
            repo = g.get_repo(repo_name)

            # Check if an issue with the same title already exists
            issues = repo.get_issues(state="open")
            for issue in issues:
                if issue.title == issue_title:
                    print(f"Issue already exists: {issue.html_url}")
                    return issue

            # Create a new issue if it does not exist
            new_issue = repo.create_issue(title=issue_title, body=issue_body)
            print(f"New issue created: {new_issue.html_url}")
            return new_issue

        except Exception as e:
            print(f"Error: {e}")
            return None

    else:
        print("Labot workflow files are identical. No action taken.")


def _colrev_sync_references():

    # Run the colrev-sync command
    try:
        # Run the colrev-sync command and capture the output
        result = subprocess.run(
            ["colrev-sync"],
            check=True,  # Raise an exception if the command fails
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,  # Ensure the output is captured as text (not bytes)
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
            new_branch_ref = repo.create_head(
                new_branch, repo.head.commit
            )  # Create the new branch from the current commit
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
            base="main",
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
        with open(makefile_path) as makefile:
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
    global VALID

    # Require a reset_course.yml workflow

    workflows_url = f"{BASE_URL}/repos/{REPO_OWNER}/{REPO_NAME}/actions/workflows"
    response = requests.get(workflows_url, headers=HEADERS)

    if response.status_code != 200:
        print(f"Error fetching workflows: {response.json()}")
        VALID = False

    workflows = response.json().get("workflows", [])
    workflow_names = [workflow["name"] for workflow in workflows]

    if ".github/workflows/reset_course.yml" not in workflow_names:
        print("No 'reset_course.yml' workflow found.")
        VALID = False


def check_paper_files(paper_files, references):
    """Check the paper files."""
    global VALID

    def validate_structure(content, paper_id, expected_title):
        """Validate the structure of a single paper file."""
        # Define the expected structure template with placeholders
        structure_template = (
            f"# {paper_id}\n"
            "\n"
            "## <Full title of the paper>\n"
            f"{expected_title}\n"
            "\n"
            "## Abstract\n"
            "<Summary of the research>\n"
            "\n"
            "<Core takeaways from the research>\n"
            "\n"
            "## Connections\n"
            "<Links to overarching concepts from the concepts/ directory>"
        )
        return content.strip() == structure_template.strip()

    errors = []

    for paper_file in paper_files:
        try:
            with open("paper/" + paper_file, 'r') as file:
                content = file.read()
        except FileNotFoundError:
            errors.append(f"File {paper_file} not found.")
            continue

        paper_id = paper_file.replace(".md", "").split('/')[-1]  # Extract paper ID from the file name

        if paper_id not in references:
            errors.append(f"Paper ID {paper_id} in {paper_file} is not in the references.")
            continue

        expected_title = references[paper_id].get("title", "<Full title of the paper>")

        if not validate_structure(content, paper_id, expected_title):
            errors.append(f"File {paper_file} does not match the expected structure.")

    if errors:
        for error in errors:
            print(f"Error: {error}")
        VALID = False
    else:
        print("All paper files are correctly structured.")


def run_knowledge_repo_checks():
    """Run checks specific to the knowledge repository."""
    global VALID

    references = colrev.loader.load_utils.load(
        filename=Path("references.bib"),
        unique_id_field="ID",
    )

    # check whether all files in the pdfs dir have *.pdf extension
    pdfs_dir = "pdfs"
    pdfs = os.listdir(pdfs_dir)
    for pdf in pdfs:
        if not pdf.endswith(".pdf"):
            print(f"File '{pdf}' in 'pdfs' directory does not have a '.pdf' extension.")
            VALID = False

    # check if all files in the papers and concepts dirs have n *.md extension
    papers_dir = "papers"
    concepts_dir = "concepts"
    paper_files = os.listdir(papers_dir)
    concept_files = os.listdir(concepts_dir)
    for paper in paper_files:
        if not paper.endswith(".md"):
            print(
                f"File '{paper}' in 'papers' directory does not have a '.md' extension."
            )
            VALID = False

    check_paper_files(paper_files, references)

    for concept in concept_files:
        if not concept.endswith(".md"):
            print(
                f"File '{concept}' in 'concepts' directory does not have a '.md' extension."
            )
            VALID = False

    # check whether all papers are in the references.bib
    for paper in paper_files:
        if paper.replace(".md", "") not in references:
            print(f"Paper '{paper}' is not listed in 'references.bib'.")
            VALID = False

    # check whether all papers have a PDF in the pdfs dir
    for paper in paper_files:
        pdf_file = paper.replace(".md", ".pdf")
        if pdf_file not in pdfs:
            print(
                f"PDF file '{pdf_file}' for paper '{paper}' not found in 'pdfs' directory."
            )
            VALID = False

    _colrev_sync_references()


def main():
    """Main function."""
    check_github_token_permissions()

    tags = get_repo_tags(REPO_OWNER, REPO_NAME)
    print(f"tags: {tags}")
    topics = get_repo_topics(REPO_OWNER, REPO_NAME)

    print(f"Repository '{REPO_NAME}' topics: {topics}")

    if "research" in topics and REPO_NAME not in ["work_hub"]:
        run_research_repo_checks()
    if "teaching-material" in topics:
        run_teaching_repo_checks()

    if REPO_NAME in ["work_hub"]:
        run_knowledge_repo_checks()

    _update_labot_file()

    if VALID:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()

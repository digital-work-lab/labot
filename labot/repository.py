#! /usr/bin/env python3
"""Repository checks."""
import hashlib
import json
import os
import pkgutil
import subprocess
import sys
from datetime import datetime
from datetime import timedelta
from pathlib import Path

import colrev.loader.load_utils
import requests
from git import Repo
from github import Github
from openai import OpenAI

import labot.thesis

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


def detect_event_type():
    event_name = os.getenv("GITHUB_EVENT_NAME")

    if event_name == "pull_request":
        head_ref = os.getenv("GITHUB_HEAD_REF", "unknown")
        base_ref = os.getenv("GITHUB_BASE_REF", "unknown")
        print(f"Triggered by a pull request from {head_ref} to {base_ref}.")
        return "pull_request"
    elif event_name == "push":
        branch = os.getenv("GITHUB_REF", "unknown").replace("refs/heads/", "")
        print(f"Triggered by a push to branch {branch}.")
        return "push"
    else:
        print(f"Triggered by an unrecognized event: {event_name}")
        return "other"


def check_github_token_permissions():
    """Check if the GITHUB_TOKEN has permissions to create pull requests and issues."""
    url = f"{BASE_URL}/repos/{REPO_OWNER}/{REPO_NAME}"
    response = requests.get(url, headers=HEADERS)

    if response.status_code != 200:
        print(f"Error checking repository access: {response.json()}")
        print("Add MY_PAT_TOKEN as repository secret")
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

    current_branch = repo.active_branch.name

    # Check if there are any changes before creating the PR
    if repo.is_dirty(untracked_files=True):
        # should be colrev-update-2024-12-17-12-00-00
        new_branch = f"colrev-update-{datetime.now().strftime('%Y-%m-%d-%H-%M-%S')}"
        # Get the current branch
        if current_branch == "main":
            if new_branch not in repo.heads:
                # Create the new branch from the current commit
                new_branch_ref = repo.create_head(new_branch, repo.head.commit)
                new_branch_ref.checkout()
                print(f"New branch '{new_branch}' created and checked out.")
            else:
                new_branch_ref = repo.heads[new_branch]
                new_branch_ref.checkout()
                print(f"Branch '{new_branch}' already exists. Checked out.")

        # add all changes
        repo.git.add("--all")

        # Create a commit for the changes and check whether a commit was created
        if not repo.index.commit("Sync changes using colrev-sync"):
            print("No changes to commit.")
            return

        origin = repo.remotes.origin
        if current_branch == "main":
            # Push the new branch to GitHub
            origin.push(new_branch)
            print(f"Branch '{new_branch}' pushed to GitHub.")

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
            origin.push(current_branch)

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
        structure_template = f"# {paper_id}\n" "\n" f"## {expected_title}\n" "\n"
        return content.strip().startswith(structure_template.strip())

    errors = []

    for paper_file in paper_files:
        try:
            with open("papers/" + paper_file) as file:
                content = file.read()
        except FileNotFoundError:
            errors.append(f"File {paper_file} not found.")
            continue

        paper_id = paper_file.replace(".md", "").split("/")[
            -1
        ]  # Extract paper ID from the file name

        if paper_id not in references:
            errors.append(
                f"Paper ID {paper_id} in {paper_file} is not in the references."
            )
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
    papers_dir = "papers"
    concepts_dir = "concepts"
    paper_files = os.listdir(papers_dir)

    for pdf in pdfs:
        if not pdf.endswith(".pdf"):
            print(f"File '{pdf}' in 'pdfs' directory does not have a '.pdf' extension.")
            VALID = False
        # all pdfs must have a paper_file
        if pdf.replace(".pdf", ".md") not in paper_files:
            print(f"PDF file '{pdf}' does not have a corresponding paper file.")
            VALID = False

    # check if all files in the papers and concepts dirs have n *.md extension
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
        # TODO : validate asset locations and links (broken links)

    _colrev_sync_references()


def get_pull_request_number():
    """
    Retrieve the pull request number from the GitHub Actions environment.

    Returns:
        int: The pull request number, or None if not a pull request event.
    """
    # Path to the event payload file
    event_path = os.getenv("GITHUB_EVENT_PATH")

    if not event_path:
        raise OSError("GITHUB_EVENT_PATH environment variable is not set.")

    try:
        # Load the event payload from the JSON file
        with open(event_path) as event_file:
            event_data = json.load(event_file)

        # Extract the pull request number if available
        if "pull_request" in event_data:
            pr_number = event_data["pull_request"]["number"]
            return pr_number
        else:
            print("This event is not a pull request.")
            return None
    except Exception as e:
        raise RuntimeError(f"Failed to parse the event payload: {e}")


def get_pull_request_changes(pr_number):
    """
    Fetch the changes introduced by the commits associated with a pull request.

    Args:
        pr_number (int): The number of the pull request.

    Returns:
        dict: A dictionary with filenames as keys and the type of change (added, modified, removed) as values,
              or an error message if the request fails.
    """
    # Retrieve the GitHub token and repository information
    github_token = os.getenv("GITHUB_TOKEN")
    github_repo = os.getenv("GITHUB_REPOSITORY")  # e.g., "owner/repo"

    if not github_token or not github_repo:
        raise OSError(
            "GITHUB_TOKEN or GITHUB_REPOSITORY environment variable is not set."
        )

    # Construct the API URL for the pull request files
    api_url = f"https://api.github.com/repos/{github_repo}/pulls/{pr_number}/files"

    # Set up headers for the API request
    headers = {
        "Authorization": f"Bearer {github_token}",
        "Accept": "application/vnd.github.v3+json",
    }

    # Make the API request to fetch the changes
    response = requests.get(api_url, headers=headers)

    if response.status_code == 200:
        # Parse the JSON response and extract file patches
        files = response.json()
        changes = {
            file["filename"]: file.get(
                "patch", "No patch available (binary or large file)"
            )
            for file in files
        }
        return changes
    else:
        return f"Failed to fetch changes. Status code: {response.status_code}, Response: {response.text}"


def evaluate_changes_with_openai(changes):
    """
    Use OpenAI's GPT to evaluate if the changes align with defined values.

    Args:
        changes (str): A string describing the changes to evaluate.

    Returns:
        str: The evaluation provided by OpenAI.
    """
    # Retrieve the OpenAI API key from the environment
    api_key = os.getenv("OPENAI_KEY")
    if not api_key:
        raise OSError("OPENAI_KEY environment variable is not set.")

    # Define the values for alignment
    values = """
    🚀 Impact in research, teaching, and practice
    We challenge ourselves every day to make significant contributions to research on digital work,
    inspiring students in different teaching formats, and facilitating the application of our work in practice.

    🛠️ Rigor, reliability, and reproducibility
    We value rigorous methods that are based on evidence and yield reproducible results.
    To this end, we select reliable tools and standard operating principles.

    ♻️ Continuous improvement, openness, sustainability
    We aim to make our work processes, continuous improvement efforts, and outcomes openly accessible.
    In particular, we prefer open-source over proprietary technology.

    🙏 Participation, support, and diversity
    We build a culture of support, encouraging the participation of different stakeholders,
    including current and former team members, students, and colleagues. We make diversity our strength.

    🧑‍🎓️ Learning
    We believe in continuous growth, setting aside time to learn on a regular basis, and curating helpful resources.
    """

    # Construct the prompt for OpenAI
    prompt = f"""
    You are an expert reviewer tasked with evaluating changes against the following values:

    {values}

    Please review the following changes and determine if they align with these values. Provide specific reasoning for your assessment:

    Changes:
    {changes}
    """

    # Call the OpenAI API
    try:
        client = OpenAI(api_key=api_key)
        chat_completion = client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert reviewer of technical changes.",
                },
                {"role": "user", "content": prompt},
            ],
            model="gpt-4",
        )
        return chat_completion.choices[0].message.content.strip()
    except Exception as e:
        return f"An error occurred while communicating with OpenAI: {e}"


def add_comment_to_pull_request(pr_number, comment_body):
    """
    Add a comment to a pull request on GitHub.

    Args:
        pr_number (int): The number of the pull request.
        comment_body (str): The body of the comment to add.

    Returns:
        str: A message indicating success or failure.
    """
    # Retrieve the GitHub token and repository information
    github_token = os.getenv("GITHUB_TOKEN")
    github_repo = os.getenv("GITHUB_REPOSITORY")  # e.g., "owner/repo"

    if not github_token or not github_repo:
        raise OSError(
            "GITHUB_TOKEN or GITHUB_REPOSITORY environment variable is not set."
        )

    # Construct the API URL for pull request comments
    api_url = f"https://api.github.com/repos/{github_repo}/issues/{pr_number}/comments"

    # Set up headers for the API request
    headers = {
        "Authorization": f"Bearer {github_token}",
        "Accept": "application/vnd.github.v3+json",
    }

    # Construct the payload for the comment
    data = {"body": comment_body}

    # Make the API request to post the comment
    response = requests.post(api_url, headers=headers, json=data)

    if response.status_code == 201:
        return "Comment successfully added to the pull request."
    else:
        return f"Failed to add comment. Status code: {response.status_code}, Response: {response.text}"


def run_pull_request_checks():
    pr_number = get_pull_request_number()
    changes = get_pull_request_changes(pr_number)
    print(f"Changes in pull request {pr_number}: {changes}")
    response = evaluate_changes_with_openai(changes)
    add_comment_to_pull_request(pr_number, response)


def generate_mermaid_chart(theses):

    # Dynamic date range
    today = datetime.today()
    end_date = today.strftime("%Y-%m")
    start_date = (today - timedelta(days=365)).strftime("%Y-%m")

    current_date = datetime.strptime(start_date, "%Y-%m")
    end_date = datetime.strptime(end_date, "%Y-%m")
    thesis_counts = {}

    while current_date <= end_date:
        month_key = current_date.strftime("%Y-%m")
        thesis_counts[month_key] = {"current": 0, "capacity": 8}  # Default capacity
        current_date = datetime(
            current_date.year + (current_date.month // 12),
            current_date.month % 12 + 1,
            1,
        )

    for thesis in theses:
        registration_date = datetime.strptime(
            thesis.date_of_registration, "%Y-%m-%d"
        )
        print(registration_date)
        month_key = registration_date.strftime("%Y-%m")
        if month_key in thesis_counts:
            thesis_counts[month_key]["current"] += 1

    print(thesis_counts)
    x_axis = list(thesis_counts.keys())
    bar_data = [value["current"] for value in thesis_counts.values()]
    line_data = [value["capacity"] for value in thesis_counts.values()]

    chart = f"""{'{: .text-center}'}
```mermaid
---
config:
    xyChart:
        width: 900
        height: 300
---
xychart-beta
    x-axis [{', '.join(x_axis)}]
    y-axis "Theses (current vs capacity)" 0 --> {max(max(bar_data), max(line_data))}
    bar [{', '.join(map(str, bar_data))}]
    line [{', '.join(map(str, line_data))}]
```"""
    return chart


def run_theses_checks():

    current_dir = os.getcwd()
    os.chdir("..")
    repo_path = "theses-confidential"
    if not os.path.exists(repo_path):
        os.system(
            f"git clone https://{GITHUB_TOKEN}@github.com/digital-work-lab/theses-confidential.git"
        )
    os.chdir(repo_path)
    theses_path = os.getcwd() + "/theses"
    theses = labot.thesis.load_theses(theses_path=theses_path)

    mermaid_chart = generate_mermaid_chart(theses)
    print(mermaid_chart)
    os.chdir(current_dir)


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
    if REPO_NAME == "theses":
        run_theses_checks()

    _update_labot_file()

    if detect_event_type() == "pull_request":
        run_pull_request_checks()

    if VALID:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()

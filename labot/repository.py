#! /usr/bin/env python3
"""Repository checks."""
import hashlib
import json
import os
import pkgutil
import re
import subprocess
import sys
from collections import OrderedDict
from datetime import datetime
from pathlib import Path

import colrev.loader.load_utils
import requests
import yaml
from git import Repo
from github import Github
from openai import OpenAI

import labot.issue_chat
import labot.notes
import labot.paper
import labot.thesis

yaml.add_representer(
    OrderedDict,
    lambda dumper, data: dumper.represent_mapping(
        "tag:yaml.org,2002:map", data.items()
    ),
)
yaml.add_representer(
    tuple, lambda dumper, data: dumper.represent_sequence("tag:yaml.org,2002:seq", data)
)

# Regex pattern to find asset links in markdown files
asset_link_pattern = re.compile(r"!\[.*?\]\((.*?)\)")
img_src_pattern = re.compile(r'<img\s[^>]*src="([^"]+)"', re.IGNORECASE)
a_href_pattern = re.compile(r'<a\s[^>]*href="([^"]+)"', re.IGNORECASE)


class Repository:

    def __init__(self) -> None:

        # GitHub token should be set in the environment variable
        self.GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
        self.GITHUB_REPOSITORY = os.getenv("GITHUB_REPOSITORY")
        if not self.GITHUB_TOKEN or not self.GITHUB_REPOSITORY:
            print("GITHUB_TOKEN or GITHUB_REPOSITORY environment variable is not set.")
            sys.exit(1)
        # self.REPO_OWNER: str = self.GITHUB_REPOSITORY("/")[0]
        self.REPO_NAME: str = self.GITHUB_REPOSITORY.split("/")[1]

        # Retrieve the OpenAI API key from the environment
        self.OPENAI_KEY = os.getenv("OPENAI_KEY") or ""

        self.github_repo = Github(self.GITHUB_TOKEN).get_repo(self.GITHUB_REPOSITORY)
        self.local_repo = Repo(Path.cwd())

        self.VALID = True
        self.GH_API_BASE_URL = "https://api.github.com"
        self.HEADERS = {
            "Authorization": f"Bearer {self.GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json",
        }

        self.PROJECT_ROOT = Path.cwd()
        self.ASSETS_DIR = Path("assets")
        self.ASSET_IGNORE_FILE = (
            self.PROJECT_ROOT / ".github/workflows/.asset_ignore.txt"
        )

    def _load_ignored_assets(self) -> set:
        if not self.ASSET_IGNORE_FILE.exists():
            return set()

        with open(self.ASSET_IGNORE_FILE, encoding="utf-8") as f:
            ignored_paths = {line.strip() for line in f if line.strip()}

        # Convert relative paths in the ignore file to absolute paths
        ignored_assets = {
            self.PROJECT_ROOT / Path(ignored).resolve() for ignored in ignored_paths
        }
        return ignored_assets

    def _find_linked_assets(self, markdown_dir: Path) -> set:
        linked_assets = set()

        # Walk through all markdown files
        for root, _, files in os.walk(markdown_dir):
            for file in files:
                if file.endswith(".md"):
                    filepath = Path(root) / file
                    with open(filepath, encoding="utf-8") as f:
                        content = f.read()
                        # Find all asset links in the markdown file
                        links = asset_link_pattern.findall(content)
                        links.extend(img_src_pattern.findall(content))
                        links.extend(a_href_pattern.findall(content))
                        for link in links:
                            # Convert to absolute path if necessary and normalize
                            asset_path = (Path(root) / link).resolve()
                            linked_assets.add(asset_path)

        return linked_assets

    def _find_all_assets(self) -> set:
        all_assets = set()

        # Walk through all files in the assets directory
        for root, _, files in os.walk(self.ASSETS_DIR):
            for file in files:
                asset_path = Path(root) / file
                all_assets.add(asset_path.resolve())

        return all_assets

    def _find_dangling_assets(self) -> set:
        linked_assets = self._find_linked_assets(Path("slides"))
        linked_assets.update(self._find_linked_assets(Path("docs")))
        all_assets = self._find_all_assets()
        ignored_assets = self._load_ignored_assets()
        dangling_assets = all_assets - linked_assets - ignored_assets
        return dangling_assets

    def _check_dangling_assets(self) -> None:

        dangling_assets = self._find_dangling_assets()
        if not dangling_assets:
            print("No dangling assets found.")

        print(f"Dangling assets: {dangling_assets}")

        # Initialize a string to store the output
        dangling_assets_content = "## Dangling Assets:\n"
        for asset in dangling_assets:
            dangling_assets_content += f"- `{asset}`\n"

        issue_title = "Assets report"

        try:

            # Check if an issue with the same title already exists
            issues = self.github_repo.get_issues(state="open")
            existing_issue = None

            for issue in issues:
                if issue.title == issue_title:
                    print(f"Issue already exists: {issue.html_url}")
                    existing_issue = issue
                    break

            if not existing_issue and dangling_assets:
                # Create a new issue if it does not exist
                new_issue = self.github_repo.create_issue(
                    title=issue_title, body=dangling_assets_content
                )
                print(f"New issue created: {new_issue.html_url}")

            if existing_issue and dangling_assets:
                existing_issue.edit(body=dangling_assets_content)
                print(f"Issue updated: {existing_issue.html_url}")
            if existing_issue and not dangling_assets:
                existing_issue.edit(state="closed")
                print(f"Issue closed: {existing_issue.html_url}")

            # for issue in issues:
            #     if issue.title == issue_title:
            #         print(f"Issue already exists: {issue.html_url}")
            #         return issue

            # # Create a new issue if it does not exist
            # new_issue = repo.create_issue(title=issue_title, body=dangling_assets_content)
            # print(f"New issue created: {new_issue.html_url}")
            # return issue

        except Exception as e:
            print(f"Error: {e}")

    def _detect_event_type(self) -> str:
        event_name = os.getenv("GITHUB_EVENT_NAME")
        if not event_name:
            event_name = "local"

        if event_name == "pull_request":
            head_ref = os.getenv("GITHUB_HEAD_REF", "unknown")
            base_ref = os.getenv("GITHUB_BASE_REF", "unknown")
            print(f"Triggered by a pull request from {head_ref} to {base_ref}.")
        elif event_name == "push":
            branch = os.getenv("GITHUB_REF", "unknown").replace("refs/heads/", "")
            print(f"Triggered by a push to branch {branch}.")
        elif event_name == "issue_comment":
            pass
        else:
            print(f"Triggered by an unrecognized event: {event_name}")
        return event_name

    def _check_github_token_permissions(self) -> None:
        """Check if the GITHUB_TOKEN has permissions to create pull requests and issues."""
        url = f"{self.GH_API_BASE_URL}/repos/{self.GITHUB_REPOSITORY}"
        print(url)
        response = requests.get(url, headers=self.HEADERS)

        if response.status_code != 200:
            print(f"Error checking repository access: {response.json()}")
            print("Add MY_PAT_TOKEN as repository secret")
            sys.exit(1)

        repo_data = response.json()
        print(repo_data.get("permissions", {}))

        if not repo_data.get("permissions", {}).get("pull"):
            print(
                "GITHUB_TOKEN does not have permission to create pull requests. "
                "Add key from labot-repository-workflows.md as MY_PAT_TOKEN repository secret."
            )
            sys.exit(1)

        if not repo_data.get("permissions", {}).get("push"):
            print(
                "GITHUB_TOKEN does not have permission to create issues (push)). "
                "Add key from labot-repository-workflows.md as MY_PAT_TOKEN repository secret."
            )
            sys.exit(1)

        print("GITHUB_TOKEN has the required permissions.")

    def _get_repo_tags(self) -> list:
        """Fetch the tags of the repository."""
        url = f"{self.GH_API_BASE_URL}/repos/{self.GITHUB_REPOSITORY}/tags"
        response = requests.get(url, headers=self.HEADERS)

        if response.status_code != 200:
            print(f"Error fetching tags: {response.json()}")
            sys.exit(1)

        tags = response.json()
        return [tag["name"] for tag in tags]

    def _get_repo_topics(self) -> list:
        """Fetch the topics of the repository."""
        url = f"{self.GH_API_BASE_URL}/repos/{self.GITHUB_REPOSITORY}/topics"
        response = requests.get(url, headers=self.HEADERS)

        if response.status_code != 200:
            print(f"Error fetching topics: {response.json()}")
            sys.exit(1)

        topics = response.json().get("names", [])
        return topics

    def _update_labot_file(self) -> None:
        # Define the file paths
        # labot_local_file = os.path.join(os.path.dirname(__file__), "labot.yml")

        labot_local_file = Path(".github/workflows/labot.yml")
        labot_package_data = pkgutil.get_data("labot", "data/labot.yml")
        if not labot_package_data:
            return

        # Function to compute file hash
        def compute_file_hash(file_path: Path) -> str:
            with open(file_path, "rb") as f:
                return hashlib.sha256(f.read()).hexdigest()

        # Compare the local file content with package data
        labot_package_hash = hashlib.sha256(labot_package_data).hexdigest()
        labot_local_hash = compute_file_hash(labot_local_file)

        if labot_local_hash != labot_package_hash:
            print("Files differ. Replacing and committing changes.")

            issue_title = "Suggestion: Update the YAML file"
            issue_body = (
                """It seems that the YAML file in the repository needs to be updated.
Please copy the [latest version](https://github.com/digital-work-lab/labot/blob/main/labot/data/labot.yml)"""
                + """ and update it [here]"""
                + f"""(https://github.com/{self.GITHUB_REPOSITORY}/edit/main/.github/workflows/labot.yml)."""
            )

            try:

                # Check if an issue with the same title already exists
                issues = self.github_repo.get_issues(state="open")
                for issue in issues:
                    if issue.title == issue_title:
                        print(f"Issue already exists: {issue.html_url}")
                        return issue

                # Create a new issue if it does not exist
                new_issue = self.github_repo.create_issue(
                    title=issue_title, body=issue_body
                )
                print(f"New issue created: {new_issue.html_url}")
                return new_issue

            except Exception as e:
                print(f"Error: {e}")
                return None

        else:
            print("Labot workflow files are identical. No action taken.")

    def _has_changes_to_commit(self) -> bool:
        """
        Check if there are any changes in the repository, ignoring newline differences.
        """
        try:
            # Run git diff with --ignore-space-at-eol to ignore newline changes
            result = subprocess.run(
                ["git", "diff", "--ignore-space-at-eol", "--exit-code"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            return result.returncode != 0  # Non-zero exit code means changes exist
        except Exception as e:
            print(f"Error checking repository changes: {e}")
            return False

    def _colrev_sync_references(self) -> None:

        pr_title = "ColRev Sync"
        # return if a pull request with the pr_title exists
        for pr in self.github_repo.get_pulls(state="open"):
            if pr.title == pr_title:
                print(f"Pull Request '{pr_title}' already exists.")
                return

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

        current_branch = self.local_repo.active_branch.name

        # Check if there are any changes before creating the PR
        if self._has_changes_to_commit():
            # should be colrev-update-2024-12-17-12-00-00
            new_branch = f"colrev-update-{datetime.now().strftime('%Y-%m-%d-%H-%M-%S')}"
            # Get the current branch
            if current_branch == "main":
                if new_branch not in self.local_repo.heads:
                    # Create the new branch from the current commit
                    new_branch_ref = self.local_repo.create_head(
                        new_branch, self.local_repo.head.commit
                    )
                    new_branch_ref.checkout()
                    print(f"New branch '{new_branch}' created and checked out.")
                else:
                    new_branch_ref = self.local_repo.heads[new_branch]
                    new_branch_ref.checkout()
                    print(f"Branch '{new_branch}' already exists. Checked out.")

            # add all changes
            self.local_repo.git.add("--all")

            # Create a commit for the changes and check whether a commit was created
            if not self.local_repo.index.commit("Sync changes using colrev-sync"):
                print("No changes to commit.")
                return

            origin = self.local_repo.remotes.origin
            if current_branch == "main":
                # Push the new branch to GitHub
                origin.push(new_branch)
                print(f"Branch '{new_branch}' pushed to GitHub.")

                # Push the changes to the new branch again
                origin.push(new_branch)
                print(f"Changes pushed to {new_branch}.")

                # Create a pull request
                pr = self.github_repo.create_pull(
                    title=pr_title,
                    body="This PR was created using the colrev-sync command.",
                    head=new_branch,
                    base="main",
                )
                print(f"Pull Request created: {pr.html_url}")

                # switch to main
                self.local_repo.heads.main.checkout()
            else:
                origin.push(current_branch)

        else:
            print("No changes found in the branch. Skipping PR creation.")
            return

    def _parse_markdown_to_dict(self, file_path: Path) -> dict:
        """
        Parses a markdown file with a YAML header into a Python dictionary (OrderedDict).

        Args:
            file_path (str): The path to the markdown file.

        Returns:
            dict: The parsed YAML content as an OrderedDict.
        """
        with open(file_path, encoding="utf-8") as file:
            content = file.read()

        # Extract the YAML block (content between the "---")
        yaml_content = content.strip().split("---")[1]

        # Parse the YAML content into an OrderedDict to preserve the order
        parsed_dict = yaml.safe_load(yaml_content)

        # Ensure the result is an OrderedDict (if not already)
        if isinstance(parsed_dict, dict):
            parsed_dict = OrderedDict(parsed_dict)

        return parsed_dict

    def _run_research_repo_checks(self) -> None:
        """Run checks specific to research repositories."""
        print("Running research repository checks...")

        makefile_path = "Makefile"

        # Check if Makefile exists
        if not os.path.isfile(makefile_path):
            print("No Makefile found in the repository.")
            self.VALID = False
        else:
            # Check if 'make pdf' rule exists in the Makefile
            with open(makefile_path) as makefile:
                makefile_contents = makefile.read()
                if "pdf" not in makefile_contents:
                    print("'make pdf' rule not found in Makefile.")
                    self.VALID = False

        if not os.path.isfile("paper.md"):
            print("No 'paper.md' file found in the repository.")
            self.VALID = False
            return

        try:
            paper = labot.paper.Paper("paper.md", self.local_repo, self.github_repo)

            # Note: trigger on status changes because this is what users are aware of
            if paper.just_published():
                template = labot.utils.get_template("paper_published_issue.md.j2")
                issue = self.github_repo.create_issue(
                    title="Paper published",
                    body=template.render(),
                    assignee="geritwagner",
                )
                print(f"Issue created: {issue.html_url}")

            if paper.status not in ["published"]:
                self._colrev_sync_references()
        except Exception as exc:
            print(exc)
            self.VALID = False

    def _run_teaching_repo_checks(self) -> None:
        """Run checks specific to teaching repositories."""

        # Require a reset_course.yml workflow

        # workflows_url = f"{GH_API_BASE_URL}/repos/{self.GITHUB_REPOSITORY}/actions/workflows"
        # response = requests.get(workflows_url, headers=HEADERS)

        # if response.status_code != 200:
        #     print(f"Error fetching workflows: {response.json()}")
        #     self.VALID = False

        # workflows = response.json().get("workflows", [])
        # workflow_names = [workflow["name"] for workflow in workflows]

        # # TBD: should this be an option of the manually-dispatched labot workflow?
        # if ".github/workflows/reset_course.yml" not in workflow_names:
        #     print("No 'reset_course.yml' workflow found.")
        #     self.VALID = False

        if self.REPO_NAME == "theses-confidential":
            theses = labot.thesis.load_theses()

            for thesis in theses:
                thesis.generate_gantt_chart_for_student()
                thesis.notify_for_inactive_students(self.github_repo)
                thesis.notify_close_to_submission(self.github_repo)

            labot.thesis.generate_gantt(theses)

            labot.thesis.create_issue_accept_thesis_supervision(self.github_repo)

    def _check_paper_files(self, paper_files: list, references: dict) -> None:
        """Check the paper files."""

        def validate_structure(content: str, expected_title: str) -> bool:
            """self.validate the structure of a single paper file."""
            # Define the expected structure template with placeholders
            structure_template = f"# {expected_title}\n" "\n"
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

            expected_title = references[paper_id].get(
                "title", "<Full title of the paper>"
            )

            if not validate_structure(content, expected_title):
                errors.append(
                    f"File {paper_file} does not match the expected structure:\n\n"
                    "https://github.com/digital-work-lab/labot/blob/main/labot/"
                    "templates/literature_note.md.j2.md?plain=1"
                )

        if errors:
            for error in errors:
                print(f"Error: {error}")
            self.VALID = False
        else:
            print("All paper files are correctly structured.")

    def _run_knowledge_repo_checks(self) -> None:
        """Run checks specific to the knowledge repository."""

        labot.notes.check_notes(self.local_repo)

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
                print(
                    f"File '{pdf}' in 'pdfs' directory does not have a '.pdf' extension."
                )
                self.VALID = False
            # all pdfs must have a paper_file
            if pdf.replace(".pdf", ".md") not in paper_files:
                print(f"PDF file '{pdf}' does not have a corresponding paper file.")
                self.VALID = False

        # check if all files in the papers and concepts dirs have n *.md extension
        concept_files = os.listdir(concepts_dir)
        for paper in paper_files:
            if not paper.endswith(".md"):
                print(
                    f"File '{paper}' in 'papers' directory does not have a '.md' extension."
                )
                self.VALID = False

        self._check_paper_files(paper_files, references)

        for concept in concept_files:
            if not concept.endswith(".md"):
                print(
                    f"File '{concept}' in 'concepts' directory does not have a '.md' extension."
                )
                self.VALID = False

        # check whether all papers are in the references.bib
        for paper in paper_files:
            if paper.replace(".md", "") not in references:
                print(f"Paper '{paper}' is not listed in 'references.bib'.")
                self.VALID = False

        # check whether all papers have a PDF in the pdfs dir
        for paper in paper_files:
            pdf_file = paper.replace(".md", ".pdf")
            if pdf_file not in pdfs:
                print(
                    f"PDF file '{pdf_file}' for paper '{paper}' not found in 'pdfs' directory."
                )
                self.VALID = False
            # TODO : self.VALIDate asset locations and links (broken links)

        self._colrev_sync_references()

    def _get_pull_request_number(self) -> int:
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
                return -1
        except Exception as e:
            raise RuntimeError(f"Failed to parse the event payload: {e}")

    def _get_pull_request_changes(self, pr_number: int) -> dict:
        """
        Fetch the changes introduced by the commits associated with a pull request.

        Args:
            pr_number (int): The number of the pull request.

        Returns:
            dict: A dictionary with filenames as keys and the type of change
                (added, modified, removed) as values,
                or an error message if the request fails.
        """

        if not self.GITHUB_TOKEN or not self.GITHUB_REPOSITORY:
            raise OSError(
                "GITHUB_TOKEN or GITHUB_REPOSITORY environment variable is not set."
            )

        # Construct the API URL for the pull request files
        api_url = f"https://api.github.com/repos/{self.GITHUB_REPOSITORY}/pulls/{pr_number}/files"

        # Set up headers for the API request
        headers = {
            "Authorization": f"Bearer {self.GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json",
        }

        # Make the API request to fetch the changes
        response = requests.get(api_url, headers=headers)

        if response.status_code != 200:
            print(
                f"Failed to fetch changes. Status code: {response.status_code}, Response: {response.text}"
            )
            raise RuntimeError("Failed to fetch changes.")

        # Parse the JSON response and extract file patches
        files = response.json()
        changes = {
            file["filename"]: file.get(
                "patch", "No patch available (binary or large file)"
            )
            for file in files
        }
        return changes

    def _evaluate_changes_with_openai(self, changes: dict) -> str:
        """
        Use OpenAI's GPT to evaluate if the changes align with defined values.

        Args:
            changes (str): A string describing the changes to evaluate.

        Returns:
            str: The evaluation provided by OpenAI.
        """

        if not self.OPENAI_KEY:
            print("OPENAI_KEY environment variable is not set.")
            return ""

        # Define the values for alignment
        values = """
        🚀 Impact in research, teaching, and practice
        We challenge ourselves every day to make significant contributions to research on digital work,
        inspiring students in different teaching formats,
        and facilitating the practical application of our work.

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
        We believe in continuous growth, learning, and curating helpful resources.
        """

        # Construct the prompt for OpenAI
        prompt = f"""
        You are an expert reviewer tasked with evaluating changes against the following values:

        {values}

        Please review the following changes and determine if they align with these values.
        Provide specific reasoning for your assessment:

        Changes:
        {changes}
        """

        # Call the OpenAI API
        try:
            client = OpenAI(api_key=self.OPENAI_KEY)
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

    def _add_comment_to_pull_request(self, pr_number: int, comment_body: str) -> str:
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
        api_url = (
            f"https://api.github.com/repos/{github_repo}/issues/{pr_number}/comments"
        )

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

    def _run_pull_request_checks(self) -> None:
        pr_number = self._get_pull_request_number()
        if pr_number < 0:
            return
        changes = self._get_pull_request_changes(pr_number)
        print(f"Changes in pull request {pr_number}: {changes}")
        response = self._evaluate_changes_with_openai(changes)
        if response:
            self._add_comment_to_pull_request(pr_number, response)

    def _read_availability_md(self, file_path: str) -> str:
        """Reads the Mermaid chart from the markdown file."""
        with open(file_path) as file:
            content = file.read()
        return content

    def _parse_mermaid_chart(self, content: str) -> tuple:
        """Parses x-axis, bar, and line data from the Mermaid chart."""
        x_axis_match = re.search(r"x-axis \[([^\]]+)\]", content)
        bar_match = re.search(r"bar \[([^\]]+)\]", content)
        line_match = re.search(r"line \[([^\]]+)\]", content)

        if not x_axis_match:
            raise ValueError(f"No match found for x-axis in content: {content}")
        if not bar_match:
            raise ValueError(f"No match found for bar in content: {content}")
        if not line_match:
            raise ValueError(f"No match found for line in content: {content}")

        x_axis = x_axis_match.group(1).split(", ")
        bar_data = list(map(int, bar_match.group(1).split(",")))
        line_data = list(map(int, line_match.group(1).split(",")))

        return x_axis, bar_data, line_data

    def _update_mermaid_chart(
        self, x_axis: list, bar_data: list, line_data: list, currently: int
    ) -> str:
        """Updates the Mermaid chart data."""
        # Remove the first data point
        x_axis.pop(0)
        bar_data.pop(0)
        line_data.pop(0)

        # Add the current month and data
        current_month = datetime.now().strftime("%Y-%m")
        x_axis.append(current_month)
        bar_data.append(currently)
        line_data.append(8)  # Fixed capacity

        # Regenerate the chart
        updated_chart = f"""{'{: .text-center}'}
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
        return updated_chart

    def _write_availability_md(self, file_path: str, content: str) -> None:
        """Writes the updated Mermaid chart back to the markdown file."""
        with open(file_path, "w") as file:
            file.write(content)
        # create and push a commit using git.Repo()

        self.local_repo.git.add(file_path)
        self.local_repo.index.commit("Update availability chart")
        origin = self.local_repo.remotes.origin
        origin.push("main")

    def _generate_mermaid_chart(self, theses: list) -> None:

        file_path = "_includes/availability.md"
        currently = sum(1 for thesis in theses if thesis.status != "archived")
        content = self._read_availability_md(file_path)
        current_month = datetime.now().strftime("%Y-%m")
        if current_month in content:
            return

        x_axis, bar_data, line_data = self._parse_mermaid_chart(content)

        updated_chart = self._update_mermaid_chart(
            x_axis, bar_data, line_data, currently
        )
        self._write_availability_md(file_path, updated_chart)

    def _run_theses_checks(self) -> None:

        current_dir = os.getcwd()
        os.chdir("..")
        repo_path = "theses-confidential"
        if not os.path.exists(repo_path):
            os.system(
                f"git clone https://{self.GITHUB_TOKEN}@github.com/digital-work-lab/theses-confidential.git"
            )
        os.chdir(repo_path)
        theses_path = Path.cwd() / "theses"
        theses = labot.thesis.load_theses(theses_path=theses_path)
        os.chdir(current_dir)
        self._generate_mermaid_chart(theses)

    def main(self) -> None:
        """Main function."""
        self._check_github_token_permissions()

        if self._detect_event_type() == "issue":
            event_path = os.getenv("GITHUB_EVENT_PATH")
            if not event_path:
                print("GITHUB_EVENT_PATH environment variable is not set.")
                sys.exit(1)
            with open(event_path) as f:
                event_data = json.load(f)
            labot.issue_chat.new_issue(self.local_repo, self.github_repo, event_data)
            return

        if self._detect_event_type() == "issue_comment":
            event_path = os.getenv("GITHUB_EVENT_PATH")
            if not event_path:
                print("GITHUB_EVENT_PATH environment variable is not set.")
                sys.exit(1)
            with open(event_path) as f:
                event_data = json.load(f)
            labot.issue_chat.comment(self.local_repo, self.github_repo, event_data)
            return

        # TODO : different functions for event-types? e.g.,
        """
        def issue_comment():

        if thesis_repo():
            thesis_repo_issue_comment()
        if paper_repo():
            ...

    def thesis_repo_issue_comment():

        if "[registration]" in title:
            registration_issue_comment()
            """

        # TODO : run "tasks" checks (for all md-files) and execute (+combine with a daily run of the workflow)

        # TODO : generally lint for "SS\d{2,4}"

        tags = self._get_repo_tags()
        print(f"tags: {tags}")
        topics = self._get_repo_topics()

        print(f"Repository '{self.REPO_NAME}' topics: {topics}")

        if "research" in topics and self.REPO_NAME not in ["work_hub"]:
            self._run_research_repo_checks()
        if "teaching-materials" in topics:
            self._run_teaching_repo_checks()

            # TODO : also for other repos?
            self._check_dangling_assets()

        if self.REPO_NAME in ["work_hub"]:
            self._run_knowledge_repo_checks()
        if self.REPO_NAME == "theses":
            self._run_theses_checks()

        self._update_labot_file()

        if self._detect_event_type() == "pull_request":
            self._run_pull_request_checks()

        if self.VALID:
            sys.exit(0)
        else:
            sys.exit(1)


if __name__ == "__main__":
    repo_instance = Repository()
    repo_instance.main()

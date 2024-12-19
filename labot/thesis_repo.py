import os
import re

from docx import Document
from github import Github


def clean_name(raw_name):
    parts = raw_name.split(",")
    if len(parts) == 2:
        last_name = parts[0].replace(" ", "").strip()
        first_name = parts[1].strip()
        return f"{last_name}, {first_name}"
    return raw_name.strip()


def extract_information(text):
    # Define regex patterns
    name_pattern = r"Name:\s*([^\n]+)"
    student_id_pattern = r"Matrikelnummer:\s*(\d+)"
    topic_pattern = r"Englisch \(zur Aufnahme ins Zeugnis\):\n([^\n]+)"
    date_pattern = r"Bamberg, den\s*([\d-]+)"
    work_time_pattern = r"(\d+)\s*Monate"

    # Extract information
    name_match = re.search(name_pattern, text)
    student_id_match = re.search(student_id_pattern, text)
    date_match = re.search(date_pattern, text)
    topic_match = re.search(topic_pattern, text)
    work_time_match = re.search(work_time_pattern, text)

    # Get the matched groups or default to None
    raw_name = name_match.group(1).strip() if name_match else None
    name = clean_name(raw_name) if raw_name else None
    student_id = student_id_match.group(1) if student_id_match else None
    topic = topic_match.group(1).strip() if topic_match else None
    date = date_match.group(1) if date_match else None
    work_time = work_time_match.group(1) if work_time_match else None

    # Return extracted information as a dictionary
    return {
        "Name": name,
        "Student ID": student_id,
        "Topic": topic,
        "Date": date,
        "Work Time": work_time + " months",
    }


def extract_text_from_word(file_path):
    try:
        document = Document(file_path)
        text = []

        for paragraph in document.paragraphs:
            text.append(paragraph.text)

        # Join all paragraphs into a single string with line breaks
        return "\n".join(text)

    except Exception as e:
        return f"An error occurred: {e}"


def extract_word_info(file_path):

    extracted_text = extract_text_from_word(file_path)
    # print("\nExtracted Text:\n")
    # print(extracted_text)
    info = extract_information(extracted_text)
    print(info)
    return info


# Create a pull-request with student details and word file, add issue-link in
# When merged: notify student in comment
# When document signed: post in issue and close?


def parse_issue_body(issue_body):
    parsed_data = {}

    lines = issue_body.splitlines()

    for line in lines:
        if line.startswith("### "):
            current_key = line[4:].strip()
            parsed_data[current_key] = None
        elif line.strip():  # Skip empty lines
            if current_key:
                parsed_data[current_key] = line.strip()

    return parsed_data


def start_registration(issue_url):
    g = Github(GITHUB_TOKEN)

    try:
        parts = issue_url.split("/")
        repo_name = f"{parts[3]}/{parts[4]}"  # owner/repo
        issue_number = int(parts[-1])
    except (IndexError, ValueError):
        print("Invalid issue URL format.")
        return

    # Retrieve the issue
    try:
        repo = g.get_repo(repo_name)
        issue = repo.get_issue(number=issue_number)
        print(f"Issue Title: {issue.title}")
        print(parse_issue_body(issue.body))

        # Check comments for the specific message
        comments = issue.get_comments()
        for comment in comments:
            if "started the registration" in comment.body:
                print("Registration already started.")
                return  # Exit the function if the comment is found

        # download all docx files from the repository
        # get all files in the repository
        files = repo.get_contents("")
        for file in files:
            if file.name.endswith(".docx"):
                print(f"Downloading file: {file.name}")
                file_content = file.decoded_content
                with open(file.name, "wb") as f:
                    f.write(file_content)

                info = extract_word_info(file.name)

        # Convert to Markdown Table
        markdown_table = "| Key                | Value |\n"
        markdown_table += "|--------------------|-------|\n"
        for key, value in info.items():
            markdown_table += f"| {key} | {value} |\n"
        issue.create_comment(
            f"Thank you. We have started the registration with the following information:\n {markdown_table}\n\nPlease check whehter the information is correct and add a comment below if there are errors. Otherwise, close the isse.\n\nBest of luck with your thesis 🎓📚🍀🤞"
        )
        # TODO : maybe post/add gantt?
        print("Comment added to the issue.")

    except Exception as e:
        print(f"An error occurred: {e}")


def list_registration_issues(GITHUB_TOKEN):
    g = Github(GITHUB_TOKEN)

    user = g.get_user()
    repos = user.get_repos()

    registration_issues = []

    print("Scanning repositories for '[registration]' issues...\n")

    for repo in repos:
        print(repo)
        if "thesis" not in repo.full_name.lower():
            continue
        print(f"Checking repository: {repo.full_name}")
        try:
            issues = repo.get_issues(state="open")
            for issue in issues:
                if "[registration]" in issue.title.lower():
                    registration_issues.append(
                        {
                            "repository": repo.full_name,
                            "issue_title": issue.title,
                            "issue_url": issue.html_url,
                        }
                    )
        except Exception as e:
            print(f"Error accessing repository {repo.full_name}: {e}")

    print()
    if registration_issues:
        print(
            f"Found {len(registration_issues)} issues with '[registration]' in the title:\n"
        )
        for issue in registration_issues:
            print(f"- Repository: {issue['repository']}")
            print(f"  Title: {issue['issue_title']}")
            print(f"  URL: {issue['issue_url']}\n")
            print("TODO : REINCLUDE:")
            start_registration(issue["issue_url"])
    else:
        print("No issues found with '[registration]' in the title.")


if __name__ == "__main__":
    # Note: this is executed regularly in
    # https://github.com/digital-work-lab/theses-confidential

    GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
    if not GITHUB_TOKEN:
        raise OSError("The GITHUB_TOKEN environment variable is not set or empty.")

    list_registration_issues(GITHUB_TOKEN)

import os
import pprint
import re

from docx import Document
from github import Github

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
if not GITHUB_TOKEN:
    raise OSError("The GITHUB_TOKEN environment variable is not set or empty.")


def clean_name(raw_name: str) -> str:
    parts = raw_name.split(",")
    if len(parts) == 2:
        last_name = parts[0].replace(" ", "").strip()
        first_name = parts[1].strip()
        return f"{last_name}, {first_name}"
    return raw_name.strip()


def extract_information(text: str) -> dict:
    # Define regex patterns
    name_pattern = r"Name:\s*([^\n]+)"
    student_id_pattern = r"Matrikelnummer:\s*(\d+)"
    topic_pattern = r"Englisch \(zur Aufnahme ins Zeugnis\):\n([^\n]+)"
    date_pattern_1 = r"Bamberg, den\s*(\d{2}\.\d{2}\.\d{4})"
    date_pattern_2 = r"Bamberg, den\s*([\d-]+)"
    work_time_pattern = r"(\d+)\s*Monate"
    zulassung_date_pattern = r"Die Zulassung erfolgte am:\s*(\d{2}\.\d{2}\.\d{4})"

    # Extract information
    name_match = re.search(name_pattern, text)
    student_id_match = re.search(student_id_pattern, text)
    date_match = re.search(date_pattern_1, text)
    if date_match:
        # convert to YYYY-MM-DD
        date = date_match.group(1)
        date = re.sub(r"(\d{2})\.(\d{2})\.(\d{4})", r"\3-\2-\1", date)
    else:
        date_match = re.search(date_pattern_2, text)
    topic_match = re.search(topic_pattern, text)
    work_time_match = re.search(work_time_pattern, text)
    zulassung_date_match = re.search(zulassung_date_pattern, text)

    # Get the matched groups or default to None
    raw_name = name_match.group(1).strip() if name_match else None
    name = clean_name(raw_name) if raw_name else None
    student_id = student_id_match.group(1) if student_id_match else None
    topic = topic_match.group(1).strip() if topic_match else None
    date = date_match.group(1) if date_match else None
    work_time = work_time_match.group(1) if work_time_match else "NA"
    zulassung_date = zulassung_date_match.group(1) if zulassung_date_match else "NA"

    level = "bachelor" if "bachelorarbeit" in text.lower() else "master"

    # Return extracted information as a dictionary
    return {
        "Name": name,
        "Student ID": student_id,
        "Topic": topic,
        "Date": date,
        "Work Time": work_time + " months",
        "Zulassung Date": zulassung_date,
        "Level": level,
    }


def extract_text_from_word(file_path: str) -> str:
    try:
        document = Document(file_path)
        text = []

        for paragraph in document.paragraphs:
            text.append(paragraph.text)

        # Join all paragraphs into a single string with line breaks
        return "\n".join(text)

    except Exception as e:
        return f"An error occurred: {e}"


def append_infos_from_word(registration) -> dict:

    extracted_text = extract_text_from_word(registration["word_file"])
    info = extract_information(extracted_text)
    registration.update(info)
    return registration


# Create a pull-request with student details and word file, add issue-link in
# When merged: notify student in comment
# When document signed: post in issue and close?


def parse_issue_body(issue_body: str) -> dict:
    parsed_data: dict = {}

    lines = issue_body.splitlines()

    for line in lines:
        if line.startswith("### "):
            current_key = line[4:].strip()
            parsed_data[current_key] = None
        elif line.strip():  # Skip empty lines
            if current_key:
                parsed_data[current_key] = line.strip()

    return parsed_data


# def start_registration(issue_url: str) -> None:
#     g = Github(GITHUB_TOKEN)

#     try:
#         parts = issue_url.split("/")
#         repo_name = f"{parts[3]}/{parts[4]}"  # owner/repo
#         issue_number = int(parts[-1])
#     except (IndexError, ValueError):
#         print("Invalid issue URL format.")
#         return

#     # Retrieve the issue
#     try:
#         repo = g.get_repo(repo_name)
#         issue = repo.get_issue(number=issue_number)
#         print(f"Issue Title: {issue.title}")
#         print(parse_issue_body(issue.body))

#         # Check comments for the specific message
#         comments = issue.get_comments()
#         for comment in comments:
#             if "started the registration" in comment.body:
#                 print("Registration already started.")
#                 return  # Exit the function if the comment is found

#         # download all docx files from the repository
#         # get all files in the repository
#         files = repo.get_contents("")
#         for file in files:
#             if file.name.endswith(".docx"):
#                 print(f"Downloading file: {file.name}")
#                 file_content = file.decoded_content
#                 with open(file.name, "wb") as f:
#                     f.write(file_content)

#                 info = append_infos_from_word(file.name)

#         # Convert to Markdown Table
#         markdown_table = "| Key                | Value |\n"
#         markdown_table += "|--------------------|-------|\n"
#         for key, value in info.items():
#             markdown_table += f"| {key} | {value} |\n"
#         issue.create_comment(
#             f"Thank you. We have started the registration with the following information:\n {markdown_table}\n\nPlease check whehter the information is correct and add a comment below if there are errors. Otherwise, close the isse.\n\nBest of luck with your thesis 🎓📚🍀🤞"
#         )
#         # TODO : maybe post/add gantt?
#         print("Comment added to the issue.")

#     except Exception as e:
#         print(f"An error occurred: {e}")


def list_registration_issues(GITHUB_TOKEN: str) -> None:
    g = Github(GITHUB_TOKEN)

    user = g.get_user()
    repos = user.get_repos()

    registration_issues = []

    print("Scanning repositories for '[registration]' issues...\n")

    for repo in repos:
        # print(repo)
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

            start_registration(issue["issue_url"])
    else:
        print("No issues found with '[registration]' in the title.")


def get_registrations():
    g = Github(GITHUB_TOKEN)

    user = g.get_user()
    repos = user.get_repos()

    registration_issues = []

    print("Scanning thesis repositories for word file...\n")

    for repo in repos:
        # print(repo)
        if "thesis" not in repo.full_name.lower():
            continue
        print(f"Checking repository: {repo.full_name}")
        try:
            files = repo.get_contents("")
            for file in files:
                if file.name.endswith(".docx"):
                    print(f"Downloading file: {file.name}")
                    file_content = file.decoded_content
                    with open(file.name, "wb") as f:
                        f.write(file_content)

                    registration_issues.append(
                        {
                            "repository": repo.full_name,
                            "word_file": file.name,
                        }
                    )

            # issues = repo.get_issues(state="open")
            # for issue in issues:
            #     if "[registration]" in issue.title.lower():
            #         registration_issues.append(
            #             {
            #                 "repository": repo.full_name,
            #                 "issue_title": issue.title,
            #                 "issue_url": issue.html_url,
            #             }
            #         )
        except Exception as e:
            print(f"Error accessing repository {repo.full_name}: {e}")
    return registration_issues


def consistency_checks(registration):

    # Check whether Date is after Zulassung Date
    if registration["Date"] < registration["Zulassung Date"]:
        raise ValueError("The date is before the Zulassung date.")

    # TODO : also check whether we already have a thesis (bachelor/master) for that student!


def create_thesis_file(data):

    # determine next_id from theses repo (or from the last file in the directory)
    next_id = 1
    # pathlib.Path
    for file in os.listdir("theses"):
        if file.endswith(".md"):
            file_id = int(file.split("_")[0])
            if file_id >= next_id:
                next_id = file_id + 1

    # Extract information from the provided dictionary
    name_split = data["Name"].split(", ")
    last_name = name_split[0]
    first_name = name_split[1] if len(name_split) > 1 else ""
    work_time_months = data["Work Time"].split()[0]  # Extract number of months
    date_of_registration = data["Date"]  # Use the Zulassung Date

    # Generate the file name and path
    file_name = f"{str(next_id).zfill(3)}_{last_name}_{first_name}.md"
    file_path = os.path.join("theses", file_name)

    # Create the content for the file
    file_content = f"""---
student: {last_name}, {first_name}
title: "{data['Topic']}"
level: "{data['Level']}"
student_id: {data['Student ID']}
status: registered
supervisor: geritwagner
degree_program: WI
industry_partner: False
date_of_registration: '{date_of_registration}'
work_time_months: {work_time_months}
date_of_actual_submission: ""
plagiarism_check_result: ""
deadline_for_the_review: ""
date_review_created: ""
---

# {data['Topic']}

```mermaid
gantt
    title Progress, {data['Name']}
    dateFormat  YYYY-MM-DD
    section Registration
```"""

    # Write the content to the file
    with open(file_path, "w", encoding="utf-8") as file:
        file.write(file_content)

    print(f"File created at: {file_path}")


def process_registrations(registrations):
    for registration in registrations:

        append_infos_from_word(registration)
        pprint.pprint(registration)
        consistency_checks(registration)

        if "y" != input("Do you want to register the thesis? [y/n]"):
            continue

        create_thesis_file(registration)

        # TODO : open comment in student repo (link to labot code for transparency)


def main():
    # Note: this is executed regularly in
    # https://github.com/digital-work-lab/theses-confidential

    # Assert the script is running in the right directory
    if not os.path.isdir("theses"):
        raise OSError(
            "The 'theses' directory does not exist in the current working directory."
        )

    # TODO : load existing theses

    # TODO : get the Word documents and urls (if any) (skip if url/thesis is already registered/...)

    registrations = get_registrations()

    # TODO : if unregistered theses: start registration (locally/remotely through issues in thesis-confidential?)
    # We should validate the title/content (other conditions) and not send it out automatically.
    # Run the action regularly and create the issue + upload the word document, include a link to the repository, extract information for validation, and add check(boxes) + results of automated checks

    # TODO : drop registrations where url is already in registered theses

    process_registrations(registrations)

    # list_registration_issues(GITHUB_TOKEN)


if __name__ == "__main__":
    main()

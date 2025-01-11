#! /usr/bin/env python3
"""Thesis repository commands."""
import os
import pprint
import re
from datetime import date
from pathlib import Path
from urllib.parse import quote

import git
from docx import Document
from github import Github
from github.Issue import Issue
from PyPDF2 import PdfReader

import labot.thesis


class ThesisRepo:

    REPO_NAME = "digital-work-lab/theses-confidential"

    def __init__(self) -> None:

        # Tokens
        self.GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
        if not self.GITHUB_TOKEN:
            raise OSError("The GITHUB_TOKEN environment variable is not set or empty.")

        self.LABOT_TOKEN = os.getenv("LABOT_TOKEN")

        # Paths
        if not os.path.isdir("theses"):
            raise OSError(
                "The 'theses' directory does not exist in the current working directory."
            )
        theses_path = Path.cwd() / "theses"
        assert theses_path.is_dir(), f"The directory {theses_path} does not exist."

        # Theses
        self.theses = labot.thesis.load_theses(theses_path=theses_path)

    def _clean_name(self, raw_name: str) -> str:
        parts = raw_name.split(",")
        if len(parts) == 2:
            last_name = parts[0].replace(" ", "").strip()
            first_name = parts[1].strip()
            return f"{last_name}, {first_name}"
        return raw_name.strip()

    def _extract_information(self, text: str) -> dict:

        name_pattern = r"Name:\s*([^\n]+)"
        student_id_pattern = r"Matrikelnummer:\s*(\d+)"
        topic_pattern = r"Englisch \(zur Aufnahme ins Zeugnis\):\n([^\n]+)"
        date_pattern_1 = r"Bamberg, den\s*(\d{2}\.\d{2}\.\d{4})"
        date_pattern_2 = r"Bamberg, den\s*([\d-]+)"
        work_time_pattern = r"(\d+)\s*Monate"
        zulassung_date_pattern = r"Die Zulassung erfolgte am:\s*(\d{2}\.\d{2}\.\d{4})"

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

        raw_name = name_match.group(1).strip() if name_match else None
        name = self._clean_name(raw_name) if raw_name else None
        student_id = student_id_match.group(1) if student_id_match else None
        topic = topic_match.group(1).strip() if topic_match else None
        date = date_match.group(1) if date_match else None
        date = re.sub(r"(\d{2})\.(\d{2})\.(\d{4})", r"\3-\2-\1", date) if date else None
        work_time = work_time_match.group(1) if work_time_match else "NA"
        zulassung_date = zulassung_date_match.group(1) if zulassung_date_match else "NA"

        level = "bachelor" if "bachelorarbeit" in text.lower() else "master"

        return {
            "student": name,
            "student_id": student_id,
            "Topic": topic,
            "Date": date,
            "Work Time": work_time + " months",
            "Zulassung Date": zulassung_date,
            "Level": level,
        }

    def _extract_text_from_word(self, file_path: str) -> str:
        try:
            document = Document(file_path)
            text = []

            for paragraph in document.paragraphs:
                text.append(paragraph.text)

            return "\n".join(text)

        except Exception as e:
            return f"An error occurred: {e}"

    def _append_infos_from_word(self, registration: dict) -> dict:

        extracted_text = self._extract_text_from_word(registration["word_file"])
        info = self._extract_information(extracted_text)
        registration.update(info)
        return registration

    # Create a pull-request with student details and word file, add issue-link in
    # When merged: notify student in comment
    # When document signed: post in issue and close?

    def _parse_issue_body(self, issue_body: str) -> dict:
        parsed_data: dict = {}

        lines = issue_body.splitlines()

        for line in lines:
            if line.startswith("### "):
                current_key = line[4:].strip()
                parsed_data[current_key] = None
            elif line.strip():
                if current_key:
                    parsed_data[current_key] = line.strip()

        return parsed_data

    def start_registration(self, issue_url: str) -> None:
        g = Github(self.GITHUB_TOKEN)

        try:
            parts = issue_url.split("/")
            repo_name = f"{parts[3]}/{parts[4]}"
            issue_number = int(parts[-1])
        except (IndexError, ValueError):
            print("Invalid issue URL format.")
            return

        try:
            repo = g.get_repo(repo_name)
            issue = repo.get_issue(number=issue_number)
            print(f"Issue Title: {issue.title}")
            print(self._parse_issue_body(issue.body))

            comments = issue.get_comments()
            for comment in comments:
                if "started the registration" in comment.body:
                    print("Registration already started.")
                    return

            # download all docx files from the repository
            # get all files in the repository
            files = repo.get_contents("")
            for file in files:
                if file.name.endswith(".docx"):
                    print(f"Downloading file: {file.name}")
                    file_content = file.decoded_content
                    with open(file.name, "wb") as f:
                        f.write(file_content)

                    info = self._append_infos_from_word(file.name)

            markdown_table = "| Key                | Value |\n"
            markdown_table += "|--------------------|-------|\n"
            for key, value in info.items():
                markdown_table += f"| {key} | {value} |\n"
            issue.create_comment(
                "Thank you. We have started the registration with the following information:\n"
                f" {markdown_table}\n\n"
                "Please check whehter the information is correct and "
                "add a comment below if there are errors. Otherwise, close the isse.\n\n"
                "Best of luck with your thesis 🎓📚🍀🤞"
            )

            # TODO : maybe post/add gantt?
            print("Comment added to the issue.")

        except Exception as e:
            print(f"An error occurred: {e}")

    def list_registration_issues(self) -> None:
        g = Github(self.GITHUB_TOKEN)

        user = g.get_user()
        repos = user.get_repos()

        registration_issues = []

        print("Scanning repositories for '[registration]' issues...\n")

        for repo in repos:
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

                self.start_registration(issue["issue_url"])
        else:
            print("No issues found with '[registration]' in the title.")

    def get_open_registrations(
        self,
    ) -> list:
        g = Github(self.GITHUB_TOKEN)

        user = g.get_user()
        repos = user.get_repos()

        registration_issues = []

        print("Scanning thesis repositories for word file...\n")

        for repo in repos:
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

    def consistency_checks(self, registration: Issue) -> None:

        # Check whether Date is after Zulassung Date
        if registration["Date"] < registration["Zulassung Date"]:
            raise ValueError("The date is before the Zulassung date.")

        # TODO : also check whether we already have a thesis (bachelor/master) for that student!

    def create_thesis_file(self, data: dict) -> Path:

        # determine next_id from theses repo (or from the last file in the directory)
        next_id = 1
        for file in os.listdir("theses"):
            if file.endswith(".md"):
                file_id = int(file.split("_")[0])
                if file_id >= next_id:
                    next_id = file_id + 1

        name_split = data["student"].split(", ")
        last_name = name_split[0]
        first_name = name_split[1] if len(name_split) > 1 else ""
        work_time_months = data["Work Time"].split()[0]
        date_of_registration = data["Date"]

        file_name = f"{str(next_id).zfill(3)}_{last_name}_{first_name}.md"
        file_path = Path("theses") / file_name.replace(" ", "_")

        file_content = f"""---
    student: {last_name}, {first_name}
    title: "{data['Topic']}"
    level: "{data['Level']}"
    student_id: {data['student_id']}
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
        title Progress, {data['student']}
        dateFormat  YYYY-MM-DD
        section Registration
    ```"""

        with open(file_path, "w", encoding="utf-8") as file_ob:
            file_ob.write(file_content)

        print(f"File created at: {file_path}")
        return file_path

    def process_registrations(self, registrations: list) -> None:
        for registration in registrations:

            self._append_infos_from_word(registration)
            pprint.pprint(registration)
            self.consistency_checks(registration)

            # TODO : add the word file to a new issue
            # (if the topic and date are filled and the thesis is not already registered)
            # if "y" != input("Do you want to register the thesis? [y/n]"):
            #     continue

            branch_name = (
                registration["student"].split(",")[0].replace(" ", "_").lower()
            )

            repo = git.Repo(Path.cwd())

            assert (
                self.LABOT_TOKEN is not None
            ), "The LABOT_TOKEN environment variable is not set or empty."
            g = Github(self.LABOT_TOKEN)
            gh_repo = g.get_repo(self.REPO_NAME)

            # check if branch_name exists on remote
            repo.remote().fetch(prune=True)
            if f"origin/{branch_name}" in [b.name for b in repo.remote().refs]:
                print(f"Branch {branch_name} already exists on remote.")
                continue

            repo.git.checkout("-b", branch_name)

            file_path = self.create_thesis_file(registration)
            repo.git.add(file_path)

            original_path = Path.cwd() / registration["word_file"]
            (Path.cwd() / "registrations").mkdir(exist_ok=True)
            registration_filename = file_path.name.replace(".md", ".docx")
            registration_path = Path.cwd() / "registrations" / registration_filename
            original_path.rename(registration_path)
            repo.git.add(registration_path)
            repo.git.commit(
                "-m",
                f"Add thesis for {registration['student']}",
                "--author=Labot <noreply@github.com>",
            )

            repo.git.push("origin", branch_name)

            # Extract the email address and email body
            email_address = "wiai.pruefungen@uni-bamberg.de"
            email_subject = "Anmeldung Abschlussarbeit"
            first, last = registration["student"].split(", ")
            formatted_name = f"{last} {first}"
            email_body = f"""Liebe Frau Schick,

    Anbei übersende ich Ihnen die ausgefüllte Themenbestätigung für {formatted_name}.

    Mit besten Grüßen

    Gerit Wagner"""

            # URL-encode the email subject and body
            email_subject_encoded = quote(email_subject)
            email_body_encoded = quote(email_body)
            mailto_link = f"mailto:{email_address}?subject={email_subject_encoded}&body={email_body_encoded}"

            # TODO : instead of simply merging, we may use a @labot command (triggering other actions?)

            attachment_link = (
                f"https://github.com/{self.REPO_NAME}/raw/refs/heads/"
                + f"{branch_name}/registrations/{registration_filename}"
            )
            pr = gh_repo.create_pull(
                title=f"[registration]: {registration['student']}",
                body=(
                    f"Registration for {registration['student']}:\n\n"
                    f"**Topic**: {registration['Topic']}\n\n"
                    # Later: this may also be the place to set the supervisor
                    # f" - [ ] Set the supervisor\n"
                    f" - [ ] Set the industry_partner field (if applicable)\n"
                    f" - [ ] Send the <a href='{mailto_link}'>Send Email</a> with "
                    f"[this attachment]({attachment_link}) \n\n"
                    f" 🚀 To accept, simply merge this pull request."
                ),
                head=branch_name,
                base="main",
            )

            pr.add_to_assignees("geritwagner")
            # Note: simultaneously creating registrations may lead to duplicate IDs
            # But this should be resolved quickly with the validation checks (when merging the second PR)

            repo.git.checkout("main")
            repo.git.branch("-D", branch_name)

            print(f"Pull request created: {pr.html_url}")
            input("TEMP:")
            break
            # TODO : open comment in student repo (link to labot code for transparency)

    def _extract_text_from_pdf(self, pdf_file: Path) -> str:
        try:
            reader = PdfReader(pdf_file)
            all_text = []
            for page in reader.pages:
                all_text.append(page.extract_text())

            return "\n".join(all_text)
        except FileNotFoundError:
            return "The PDF file was not found."
        except Exception as e:
            return f"An error occurred: {e}"

    def _get_new_submissions(self, repo: Github) -> list:
        issues = repo.get_issues(state="open")
        submissions = []
        for issue in issues:
            if not issue.title.startswith("[Thesis Submission]"):
                continue
            if len(list(issue.get_comments())) == 0:
                submissions.append(issue)
        return submissions

    def _handle_submissions(self, new_submission: Issue, theses: list) -> None:

        print(new_submission)
        comments = list(new_submission.get_comments())

        if len(comments) == 0:
            attachment_url = None
            markdown_link_pattern = r"\[.*?\]\((.*?)\)"

            match = re.search(markdown_link_pattern, new_submission.body)
            if match and match.group(1).endswith(".pdf"):
                attachment_url = match.group(1)

            if not attachment_url:
                for comment in comments:
                    match = re.search(markdown_link_pattern, comment.body)
                    if match and match.group(1).endswith(".pdf"):
                        attachment_url = match.group(1)
                        break

            if attachment_url:
                print(f"Download PDF from: {attachment_url}")

                # Download of attachments problematic:
                # https://github.com/cli/cli/issues/9046

            else:
                print("No PDF attachment found for this issue.")
                return

            input("save as submission.pdf")
            submission_pdf = Path.cwd() / "submission.pdf"

            text = self._extract_text_from_pdf(submission_pdf)

            # match date "DD.MM.YYYY" from text
            date_match = re.search(r"\d{2}\.\d{2}\.\d{4}", text)

            if date_match:
                submission_date = re.sub(
                    r"(\d{2})\.(\d{2})\.(\d{4})", r"\3-\2-\1", date_match.group(0)
                )
            else:
                print("Did not find submission date - using today as a fallback.")
                submission_date = str(date.today())

            if len(text) < 1000:
                print("No text extracted from the PDF.")
                return

            thesis = None
            for current_thesis in theses:
                if current_thesis.status != "registered":
                    continue

                if current_thesis.student.split(",")[
                    0
                ].lower() in text.lower() and current_thesis.title.lower().replace(
                    " ", ""
                ) in text.lower().replace(
                    " ", ""
                ).replace(
                    "\n", ""
                ):
                    print(f"Found thesis: {current_thesis.to_dict()}")
                    thesis = current_thesis
                    break

            if thesis is None:
                print("No matching thesis found.")
                return

            if "y" != input("Confirm the thesis? [y/n]"):
                return

            print("- Add file to repository")
            # rename submission.pdf to submissions/XXX_student.pdf
            new_filename = thesis.filename.replace(".md", ".pdf")
            new_path = Path.cwd() / "submissions" / new_filename
            submission_pdf.rename(new_path)
            # update status in the thesis file
            thesis.status = "submitted"
            thesis.date_of_actual_submission = str(submission_date)
            labot.thesis.update_thesis_metadata(thesis)

            # add new_file and thesis.filename to git using gitpython
            print("- Add commit and push")
            repo = git.Repo(Path.cwd())
            repo.git.add(new_path)
            repo.git.add(Path("theses") / thesis.filename)
            repo.git.commit("-m", f"Add submission for {thesis.student}")
            repo.git.push()

            pdf_file_path = (
                f"https://github.com/{self.REPO_NAME}/blob/main/submissions/"
                + f"{thesis.filename.replace('.md', '.pdf')}"
            )
            notes_file_path = f"https://github.com/{self.REPO_NAME}/blob/main/theses/{thesis.filename}"

            print("- Respond to issue")
            reply_body = (
                f"Thesis matched successfully!\n\n"
                f"**Student:** {thesis.student}\n"
                f"**Title:** {thesis.title}\n"
                f"**Notes:** [file]({notes_file_path})\n\n"
                f"**PDF:** [file]({pdf_file_path})\n\n"
                f"Supervisor: @{thesis.supervisor} \n"
                f"Please do your best to complete the review by XY (2 weeks) (official deadline: XY)"
                f"TODO: Plagiarism check (automatically mark XY_thesis.md?)"
                f"To create the review, use `labot thesis --grade`"
            )
            new_submission.create_comment(reply_body)

    def registrations(self) -> None:
        # Note: this is executed regularly in
        # https://github.com/digital-work-lab/theses-confidential

        # TODO : get the Word documents and urls (if any) (skip if url/thesis is already registered/...)
        # TODO : also skip if topic is missing or date is a problem
        # TODO : drop registrations where url is already in registered theses
        registrations = self.get_open_registrations()

        # TODO: for manually initiated issues, attach the file/have it uploaded separately (PULL-REQUEST)

        # TODO : if unregistered theses: start registration (remotely through issues in thesis-confidential)
        # We should validate the title/content (other conditions) and not send it out automatically.
        # Run the action regularly and create the issue + upload the word document.
        # extract information for validation, and add check(boxes) + results of automated checks
        # TODO : include a link to the repository,

        self.process_registrations(registrations)

        # list_registration_issues(self.GITHUB_TOKEN)

    def submissions(self) -> None:
        print(
            f"Check thesis submissions (issues in https://github.com/{self.REPO_NAME}/issues)"
        )

        theses_path = Path.cwd() / "theses"
        assert theses_path.is_dir(), f"The directory {theses_path} does not exist."
        theses = labot.thesis.load_theses(theses_path=theses_path)

        g = Github(self.GITHUB_TOKEN)
        repo = g.get_repo(self.REPO_NAME)

        new_submissions = self._get_new_submissions(repo)
        print(f"Found {len(new_submissions)} new submissions.\n\n")
        if new_submissions:
            for new_submission in new_submissions:

                self._handle_submissions(new_submission, theses)

                # TODO : add files to git
                print("Temporary:")
                break

            # TODO : if len(comments) == 1...


if __name__ == "__main__":
    print("Nothing")

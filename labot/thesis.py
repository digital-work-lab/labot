#! /usr/bin/env python3
"""Command-line interface for CoLRev."""
from __future__ import annotations

import webbrowser
from datetime import date
from datetime import datetime
from datetime import timedelta
from pathlib import Path

import inquirer
import yamale
import yaml
from github import Github
from mailmerge import MailMerge

import labot.utils

# flake8: noqa: E501

THESIS_DOCS_URL = "https://digital-work-lab.github.io/handbook/docs/30-teaching/30_processes/30.40.theses.html#grading"


class Thesis:
    def __init__(
        self,
        filename: str,
        student: str,
        student_id: str,
        level: str,
        status: str,
        degree_program: str,
        work_time_months: str,
        industry_partner: str,
        date_of_registration: str,
        deadline_submission: str,
        date_of_actual_submission: str,
        deadline_for_the_review: str,
        date_review_created: str,
        plagiarism_check_result: str,
        supervisor: str,
        title: str,
    ):
        self.student = student
        self.filename = filename
        self.id = filename[:3]
        self.student_id = student_id
        self.level = level
        self.status = status
        self.degree_program = degree_program
        self.work_time_months = work_time_months
        self.industry_partner = industry_partner
        self.date_of_registration = date_of_registration
        self.deadline_submission = deadline_submission
        self.date_of_actual_submission = date_of_actual_submission
        self.deadline_for_the_review = deadline_for_the_review
        self.date_review_created = date_review_created
        self.plagiarism_check_result = plagiarism_check_result
        self.supervisor = supervisor
        self.title = title

    def __str__(self) -> str:
        return f"{self.student} - {self.title} - {self.status}"

    def __repr__(self) -> str:
        return self.__str__()

    def formatted_student(self) -> str:
        last, first = self.student.split(", ")
        return f"{first} {last}"

    def to_dict(self) -> dict:
        return {
            "student": self.student,
            "student_id": self.student_id,
            "degree_program": self.degree_program,
            "work_time_months": self.work_time_months,
            "industry_partner": self.industry_partner,
            "date_of_registration": self.date_of_registration,
            "deadline_submission": self.deadline_submission,
            "date_of_actual_submission": self.date_of_actual_submission,
            "deadline_for_the_review": self.deadline_for_the_review,
            "date_review_created": self.date_review_created,
            "plagiarism_check_result": self.plagiarism_check_result,
            "status": self.status,
            "supervisor": self.supervisor,
            "title": self.title,
        }

    def generate_gantt_chart_for_student(self) -> None:
        print(f"Generating Gantt chart for {self.student}")
        gantt_chart = [
            "gantt",
            f"    title Progress, {self.student}",
            "    dateFormat  YYYY-MM-DD",
        ]

        registration_date = datetime.strptime(self.date_of_registration, "%Y-%m-%d")
        work_end_date = datetime.strptime(self.deadline_submission, "%Y-%m-%d")
        work_time_days = (work_end_date - registration_date).days

        # Registration milestone
        gantt_chart.append("    section Registration")
        gantt_chart.append(f"    Registration: milestone, {self.date_of_registration},")

        # Work progress section
        gantt_chart.append("    section Work Progress")

        if datetime.now() > work_end_date:
            gantt_chart.append(
                f"    Work Time ({self.work_time_months} months): done, {self.date_of_registration}, {work_time_days}d"
            )
        else:
            gantt_chart.append(
                f"    Work Time ({self.work_time_months} months): active, {self.date_of_registration}, {work_time_days}d"
            )

        # Actual submission milestone
        if self.date_of_actual_submission:
            submission_date = datetime.strptime(
                self.date_of_actual_submission, "%Y-%m-%d"
            )
            gantt_chart.append(
                f"    Actual Submission: milestone, {submission_date.strftime('%Y-%m-%d')}, 1d"
            )
        else:
            submission_date = work_end_date
            gantt_chart.append(
                f"    Expected Submission: milestone, {submission_date.strftime('%Y-%m-%d')}, 1d"
            )

        # Review process section
        gantt_chart.append("    section Review Process")

        review_start_date = submission_date + timedelta(days=1)
        review_period_days = 90
        review_end_date = review_start_date + timedelta(days=review_period_days)

        if datetime.now() > review_end_date:
            gantt_chart.append(
                f"    Review period: done, {review_start_date.strftime('%Y-%m-%d')}, {review_period_days}d"
            )
        else:
            gantt_chart.append(
                f"    Review period: active, {review_start_date.strftime('%Y-%m-%d')}, {review_period_days}d"
            )

        if self.date_review_created:
            review_created_date = datetime.strptime(
                self.date_review_created, "%Y-%m-%d"
            )
            gantt_chart.append(
                f"    Review Created: milestone, {review_created_date.strftime('%Y-%m-%d')}, 1d"
            )
        else:
            gantt_chart.append(
                f"    Expected Review Completion: milestone, {review_end_date.strftime('%Y-%m-%d')}, 1d"
            )

        print("\n".join(gantt_chart))
        # update gatt chart in self.filename (replace existing mermai)

        # Update Gantt chart in file
        filename = Path("theses") / self.filename
        with open(filename) as file:
            lines = file.readlines()

        # Replace existing Mermaid section
        with open(filename, "w") as file:
            in_mermaid_block = False
            for line in lines:
                if line.strip() == "```mermaid":
                    in_mermaid_block = True
                    file.write(line)
                    file.write("\n".join(gantt_chart) + "\n")
                elif line.strip() == "```" and in_mermaid_block:
                    in_mermaid_block = False
                    file.write(line)  # Add closing code block
                elif not in_mermaid_block:
                    file.write(line)

    def notify_for_inactive_students(self, github_repo: Github) -> None:
        if self.status != "registered":
            return
        print("Notification for inactive students")
        # get last modified date of the file
        filename = Path("theses") / self.filename
        file = github_repo.get_contents(str(filename))
        last_modified = datetime.strptime(file.last_modified, "%a, %d %b %Y %H:%M:%S %Z")
        days_since_last_modified = (datetime.now() - last_modified).days
        print(days_since_last_modified)
        if days_since_last_modified < 30:
            return
        print(f"Notify {self.student} for inactivity")
        issue_title = f"Thesis Inactivity: {self.student}"
        template = labot.utils.get_template("thesis_inactivity_issue.md.j2.md")

        github_repo.create_issue(
            title=issue_title, body=template, assignee="geritwagner"
        )


def get_thesis() -> Thesis:
    # Load theses from YAML files

    theses_data = load_theses(
        theses_path=Path(
            "/home/gerit/ownCloud/data/teaching/theses-confidential/theses"
        )
    )

    student_choices = {
        f"{thesis.student} ({thesis.student_id})": thesis.student_id
        for thesis in theses_data
        if thesis.date_of_actual_submission != "" and thesis.status != "archived"
    }

    questions = [
        inquirer.List(
            "student",
            message="Select a student:",
            choices=student_choices.keys(),
        )
    ]
    answers = inquirer.prompt(questions)
    selected_student_id = student_choices[answers["student"]]
    selected_thesis = [
        thesis for thesis in theses_data if thesis.student_id == selected_student_id
    ][0]
    return selected_thesis


def create_review_file(thesis: Thesis) -> None:
    print("Creating review file...")
    # Add logic to create the review file here
    review_content = f"""---
subject: "Review: {thesis.level.capitalize()}'s Thesis"
candidate: "{thesis.student}"
student_id: {int(thesis.student_id)}
thesis_id: 35.{thesis.id}
title: "{thesis.title}"
---

<!--
https://digital-work-lab.github.io/handbook/docs/30-teaching/30_processes/30.40.theses.html#grading
-->

<!-- Summary paragraph -->

<!-- Formal requirements summary -->

<!-- Main criteria summary: process -->

<!-- Main criteria summary: contribution -->

<!-- Summary of main strengths and shortcomings -->

The main strengths are ...
The main shortcomings are ...

Overall, I therefore recommend a grade of XXXXX for {thesis.formatted_student()}'s {thesis.level.capitalize()}'s thesis.
"""

    with open("review.md", "w") as review_file:
        review_file.write(review_content)

    webbrowser.open_new_tab(THESIS_DOCS_URL)


def generate_review() -> None:
    # Read the Markdown file
    with open("review.md") as file:
        content = file.read()

    # Separate frontmatter and body
    if content.startswith("---"):
        parts = content.split("---", 2)
        metadata = yaml.safe_load(parts[1])
        body = parts[2].strip()
    else:
        raise ValueError("No frontmatter found in the Markdown file.")

    # Process the body to remove comments
    lines = body.split("\n")
    lines_wo_comments = []
    skipping_comment = False
    for line in lines:
        if line.startswith("<!--"):
            skipping_comment = True
        if "-->" in line:
            skipping_comment = False
            continue
        if skipping_comment:
            continue
        lines_wo_comments.append(line)

    metadata["body"] = "\n".join(lines_wo_comments)
    metadata["review"] = metadata["body"]
    metadata["Date"] = str(date.today())

    # Populate the template
    template_1 = "/home/gerit/ownCloud/data/labot/labot/review_template.docx"
    document_1 = MailMerge(template_1)

    # Add required fields for the merge
    metadata["thesis_id"] = str(metadata["thesis_id"])
    metadata["candidate"] = str(metadata["candidate"])
    metadata["title"] = str(metadata["title"])
    metadata["student_id"] = str(metadata["student_id"])

    document_1.merge(**metadata)
    document_1.write(
        f'{str(date.today())}-{metadata["thesis_id"]}-{metadata["candidate"].replace(" ", "_")}_Gutachten.docx'
    )


def grade() -> None:
    review_file = Path("review.md")

    if not review_file.exists():
        thesis = get_thesis()
        print(thesis)
        create_review_file(thesis)
        print(f"Created review file: {review_file}")
        return

    print(f"Selected review file: {review_file}")
    generate_review()


def load_theses(theses_path: Path = Path("theses")) -> list:
    # iterate over all md files in the theses directory
    theses = []
    for thesis_file in Path(theses_path).rglob("*.md"):
        # Extract YAML header and validate
        yaml_header = thesis_file.read_text().split("---")[1]
        data = yamale.make_data(content=yaml_header)
        data[0][0]["filename"] = thesis_file.name
        # theses.append(data[0][0])
        theses.append(Thesis(**data[0][0]))

    return theses


def update_thesis_metadata(thesis: Thesis) -> None:

    # Update the yaml metadata of the thesis

    # Load the file
    thesis_file = Path("theses") / Path(thesis.filename)
    thesis_content = thesis_file.read_text()

    # Generate yaml header
    yaml_header = f"""---
student: {thesis.student}
title: "{thesis.title}"
level: {thesis.level}
student_id: {thesis.student_id}
status: {thesis.status}
supervisor: {thesis.supervisor}
degree_program: {thesis.degree_program}
industry_partner: {thesis.industry_partner}
date_of_registration: '{thesis.date_of_registration}'
work_time_months: {thesis.work_time_months}
date_of_actual_submission: '{thesis.date_of_actual_submission}'
plagiarism_check_result: '{thesis.plagiarism_check_result}'
deadline_for_the_review: '{thesis.deadline_for_the_review}'
date_review_created: '{thesis.date_review_created}'
---"""
    # replace existing yaml header
    thesis_content = thesis_content.split("---", 2)[2]

    # Update the file
    thesis_file.write_text(yaml_header + thesis_content)


def generate_gantt(theses: list) -> None:
    """Generate a Gantt chart for all active theses."""

    active_theses = [thesis for thesis in theses if thesis.status != "archived"]
    sorted_theses = sorted(
        active_theses,
        key=lambda x: datetime.strptime(x.date_of_registration, "%Y-%m-%d"),
    )
    gantt_chart = ["gantt", "    title Active Theses", "    dateFormat  YYYY-MM-DD"]

    for thesis in sorted_theses:
        gantt_chart.append(f"    section {thesis.student} ({thesis.student_id})")

        registration_date = datetime.strptime(thesis.date_of_registration, "%Y-%m-%d")
        work_end_date = datetime.strptime(thesis.deadline_submission, "%Y-%m-%d")
        work_time_days = (work_end_date - registration_date).days

        if datetime.now() > work_end_date:
            gantt_chart.append(
                f"    {thesis.work_time_months} months: done, {thesis.date_of_registration}, {work_time_days}d"
            )
        else:
            gantt_chart.append(
                f"    {thesis.work_time_months} months: active, {thesis.date_of_registration}, {work_time_days}d"
            )

        if thesis.date_of_actual_submission:
            submission_date = datetime.strptime(
                thesis.date_of_actual_submission, "%Y-%m-%d"
            )
            # grading_end_date = submission_date + timedelta(days=90)
            gantt_chart.append(
                f"    Grading: crit, {submission_date.strftime('%Y-%m-%d')}, 90d"
            )

    print("\n".join(gantt_chart))

    with open("gantt_chart.md", "w") as file:
        file.write("# Gantt Chart\n")
        file.write("```mermaid\n")
        file.write("\n".join(gantt_chart))
        file.write("\n```\n")

    print("Gantt chart generated and saved as gantt_chart.md")

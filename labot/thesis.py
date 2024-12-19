#! /usr/bin/env python3
"""Command-line interface for CoLRev."""
from __future__ import annotations

import webbrowser
from datetime import date
from pathlib import Path

import inquirer
import yamale
import yaml
from frontmatter import Frontmatter
from mailmerge import MailMerge

HANDBOOK_PATH = Path("/home/gerit/ownCloud/data/handbook")
# TODO : similarly: should know about nextcloud paths

PRIVATE_DATA = Path("/home/gerit/ownCloud/digital-work-lab/")

THESES_YAML_PATH = Path(
    "/home/gerit/ownCloud/data/teaching/theses-confidential/theses.yaml"
)


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
        # deadline: str,
        date_of_actual_submission: str,
        deadline_for_the_review: str,
        date_review_created: str,
        plagiarism_check_result: str,
        supervisor: str,
        title: str,
    ):
        self.student = student
        self.filename = filename
        self.student_id = student_id
        self.level = level
        self.status = status
        self.degree_program = degree_program
        self.work_time_months = work_time_months
        self.industry_partner = industry_partner
        self.date_of_registration = date_of_registration
        # TODO : calcualte
        # self.deadline = deadline
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

    def to_dict(self) -> dict:
        return {
            "student": self.student,
            "student_id": self.student_id,
            "status": self.status,
            "program": self.program,
            "work_time_months": self.work_time_months,
            "industry_partner": self.industry_partner,
            "date_of_registration": self.date_of_registration,
            "deadline": self.deadline,
            "date_of_actual_submission": self.date_of_actual_submission,
            "deadline_for_the_review": self.deadline_for_the_review,
            "date_review_created": self.date_review_created,
            "plagiarism_check_result": self.plagiarism_check_result,
            "remarks": self.remarks,
            "archived": self.archived,
            "supervisor": self.supervisor,
            "title": self.title,
        }


def get_thesis() -> Thesis:
    # Load theses from YAML file
    with open(THESES_YAML_PATH) as yaml_file:
        theses_data = yaml.safe_load(yaml_file)

    # Create a mapping of student names to their corresponding IDs
    student_choices = {
        f"{data['student']} ({student_id})": student_id
        for student_id, data in theses_data.items()
        if data.get("date_of_actual_submission", "") != ""
        and data["status"] != "graded"
    }

    # Create a list of student names with IDs for the selection menu
    questions = [
        inquirer.List(
            "student",
            message="Select a student:",
            choices=student_choices.keys(),
        )
    ]
    answers = inquirer.prompt(questions)

    # Get the selected student ID
    selected_student_id = student_choices[answers["student"]]
    selected_student_data = theses_data[selected_student_id]
    input(selected_student_data)
    # Create and return a Thesis object
    return Thesis(
        student=selected_student_data["student"],
        student_id=selected_student_data["student_id"],
        status=selected_student_data["status"],
        degree_program=selected_student_data["degree_program"],
        work_time_months=selected_student_data["work_time_months"],
        industry_partner=selected_student_data["industry_partner"],
        date_of_registration=selected_student_data["date_of_registration"],
        date_of_actual_submission=selected_student_data["date_of_actual_submission"],
        deadline_for_the_review=selected_student_data["deadline_for_the_review"],
        date_review_created=selected_student_data["date_review_created"],
        plagiarism_check_result=selected_student_data["plagiarism_check_result"],
        remarks=selected_student_data["comment"],
        archived=selected_student_data["archived"],
        supervisor=selected_student_data["supervisor"],
        title=selected_student_data["title"],
    )


def create_review_file(thesis):
    print("Creating review file...")
    # Add logic to create the review file here
    review_content = f"""---
subject: "Review: {thesis.program}'s Thesis"
candidate: "{thesis.student}"
student_id: {int(thesis.student_id)}
thesis_id: 35.XXXXXXXX
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

Overall, I therefore recommend a grade of XXXXX for {thesis.student}'s {thesis.program}'s thesis.
"""

    with open("review.md", "w") as review_file:
        review_file.write(review_content)

    url = "https://digital-work-lab.github.io/handbook/docs/30-teaching/30_processes/30.40.theses.html#grading"
    webbrowser.open_new_tab(url)


def generate_review():
    data = Frontmatter.read_file("review.md")

    lines = data["body"].split("\n")

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

    data["body"] = "\n".join(lines_wo_comments)

    data["review"] = data["body"]
    data["Date"] = today = str(date.today())

    template_1 = "/home/gerit/ownCloud/data/labot/labot/review_template.docx"

    document_1 = MailMerge(template_1)

    data["thesis_id"] = str(data["attributes"]["thesis_id"])
    data["candidate"] = str(data["attributes"]["candidate"])
    data["title"] = str(data["attributes"]["title"])
    data["student_id"] = str(data["attributes"]["student_id"])

    document_1.merge(**data)
    document_1.write(
        f'{str(date.today())}-{data["thesis_id"]}-{data["candidate"].replace(" ", "_")}_Gutachten.docx'
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


def load_theses():
    # iterate over all md files in the theses directory
    theses = []
    for thesis_file in Path("theses").rglob("*.md"):
        # Extract YAML header and validate
        yaml_header = thesis_file.read_text().split("---")[1]
        data = yamale.make_data(content=yaml_header)
        data[0][0]["filename"] = thesis_file.name
        # theses.append(data[0][0])
        theses.append(Thesis(**data[0][0]))

    return theses

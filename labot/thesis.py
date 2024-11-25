#! /usr/bin/env python3
"""Command-line interface for CoLRev."""
from __future__ import annotations

from pathlib import Path

import inquirer
import pandas as pd
from datetime import date

from frontmatter import Frontmatter
import pandas as pd
from mailmerge import MailMerge

HANDBOOK_PATH = Path("/home/gerit/ownCloud/data/handbook")
# TODO : similarly: should know about nextcloud paths

PRIVATE_DATA = Path("/home/gerit/ownCloud/digital-work-lab/")

THESES_OVERVIEW = PRIVATE_DATA / Path(
    "30-teaching/35_theses/000_overview/35.000 Theses.xlsx"
)


class Thesis:

    def __init__(
        self,
        Student: str,
        Status: str,
        Studiengang: str,
        Bearbeitungszeit: float,
        Matrikelnummer: float,
        Unternehmenskooperation: str,
        Deadline: str,
        Abgabe: str,
        Anmeldung: str,
        Deadline_Review: str,
        Gutachten_erstellt: str,
        Plagiatscheck: str,
        Bemerkungen: str,
        Archiviert: str,
        Hauptbetreuer: str,
        Titel: str,
        degree: str,
    ):
        self.student = Student
        self.status = Status
        self.studiengang = Studiengang
        self.bearbeitungszeit = Bearbeitungszeit
        self.matrikelnummer = Matrikelnummer
        self.unternehmenskooperation = Unternehmenskooperation
        self.anmeldung = Anmeldung
        self.deadline = Deadline
        self.abgabe = Abgabe
        self.deadline_review = Deadline_Review
        self.gutachten_erstellt = Gutachten_erstellt
        self.plagiatscheck = Plagiatscheck
        self.bemerkungen = Bemerkungen
        self.archiviert = Archiviert
        self.hauptbetreuer = Hauptbetreuer
        self.title = Titel
        self.degree = degree

    def __str__(self) -> str:
        return f"{self.student} - {self.title} - {self.status}"

    def __repr__(self) -> str:
        return self.__str__()

    def to_dict(self) -> dict:
        return {"student": self.student, "degree": self.degree, "status": self.status}


def get_thesis() -> Thesis:
    questions = [
        inquirer.List("degree", message="Select:", choices=["Bachelor", "Master"])
    ]

    answers = inquirer.prompt(questions)
    selected_degree = answers["degree"]

    if selected_degree == "Bachelor":
        df = pd.read_excel(THESES_OVERVIEW, sheet_name="Bachelor-Arbeiten")
    else:
        df = pd.read_excel(THESES_OVERVIEW, sheet_name="Master-Arbeiten")

    filtered_df = df[
        (df["Status"] != "Bewertet")
        & (df["Status"] != "Angemeldet")
        & (~df["Status"].isna())
    ]
    # print(filtered_df)

    questions = [
        inquirer.List(
            "row",
            message="Select a row:",
            choices=filtered_df[filtered_df["Student"].notna()]["Student"].tolist(),
        )
    ]

    answers = inquirer.prompt(questions)
    student = answers["row"]

    selected_row = filtered_df[filtered_df["Student"] == student]
    selected_student_row = selected_row.iloc[0]

    return Thesis(**selected_student_row, degree=selected_degree)


def create_review_file(thesis):
    print("Creating review file...")
    # Add logic to create the review file here
    review_content = f"""---
subject: "Review: {thesis.degree}'s Thesis"
candidate: "{thesis.student}"
student_id: {int(thesis.matrikelnummer)}
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

Overall, I therefore recommend a grade of XXXXX for {thesis.student}'s {thesis.degree}'s thesis.
"""

    with open("review.md", "w") as review_file:
        review_file.write(review_content)

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

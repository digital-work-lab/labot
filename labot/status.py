#! /usr/bin/env python3
"""Command-line interface for CoLRev."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from labot.constants import Colors

HANDBOOK_PATH = Path("/home/gerit/ownCloud/data/handbook")
# TODO : similarly: should know about nextcloud paths

PRIVATE_DATA = Path("/home/gerit/ownCloud/digital-work-lab/")

THESES_OVERVIEW = PRIVATE_DATA / Path(
    "30-teaching/35_theses/000_overview/35.000 Theses.xlsx"
)


def get_url(page: str) -> str:

    return (
        str(page)
        .replace(str(HANDBOOK_PATH), "https://digital-work-lab.github.io/handbook/")
        .replace(".md", ".html")
    )


def print_status():

    print("Tasks")  # Role...

    task_dict = {}
    for file_path in HANDBOOK_PATH.glob("**/*.md"):
        with open(file_path) as file:
            lines = file.readlines()
            open_tasks = [line.strip() for line in lines if "- [ ]" in line]
            task_dict[file_path] = open_tasks

    for page, tasks in task_dict.items():
        if len(tasks) == 0:
            continue
        with open(page) as file:
            lines = file.readlines()
            yaml_header = "".join(
                lines[:10]
            )  # Assuming the YAML header is in the first 3 lines
            if "template: true" in yaml_header:
                continue

        print(f"\n{Colors.ORANGE}{page.name}{Colors.END} ({get_url(page)})")
        for task in tasks:
            print(f"  {task}")

    print()
    print("Theses")

    df = pd.read_excel(THESES_OVERVIEW, sheet_name="Bachelor-Arbeiten")
    filtered_df = df[df["Status"] != "Bewertet"]
    open_theses = [t for t in filtered_df["Student"].to_list() if not pd.isna(t)]
    print("- [ ] " + "\n- [ ] ".join(open_theses))

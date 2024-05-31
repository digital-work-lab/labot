#! /usr/bin/env python3
"""Command-line interface for CoLRev."""
from __future__ import annotations
from pathlib import Path
import pprint
from labot.constants import Colors

HANDBOOK_PATH = Path("/home/gerit/ownCloud/data/handbook")
# TODO : similarly: should know about nextcloud paths

def print_status():
    print("hello")

    task_dict = {}
    for file_path in HANDBOOK_PATH.glob("**/*.md"):
        with open(file_path, "r") as file:
            lines = file.readlines()
            open_tasks = [line.strip() for line in lines if "- [ ]" in line]
            task_dict[file_path] = open_tasks

    for page, tasks in task_dict.items():
        if len(tasks) == 0:
            continue
        with open(page, "r") as file:
            lines = file.readlines()
            yaml_header = "".join(lines[:10])  # Assuming the YAML header is in the first 3 lines
            if "template: true" in yaml_header:
                continue
        print(page)
        print(f"{Colors.ORANGE}{page.name}{Colors.END}")
        for task in tasks:
            print(f"  {task}")
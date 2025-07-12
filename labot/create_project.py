#! /usr/bin/env python
import datetime
import math
import os
import re
from pathlib import Path

# from time import time, gmtime, strftime


def get_project_path_dir(project_name, year_quartal_prefix):
    # project_path_dir = input("Path of directory:")
    project_path_dir = Path.cwd()

    project_path = project_path_dir / project_name

    # if all/many projects in the directory are prefixed YYYY_Qn_,
    # ask if that should be added
    existing_directories = [
        x
        for x in os.listdir(project_path_dir)
        if os.path.isdir(os.path.join(project_path_dir, x))
    ]
    directories_matching_yyyy_qn = [
        re.match(re.compile(r"\d{4}_Q\d_"), x) is not None for x in existing_directories
    ]
    if len(directories_matching_yyyy_qn) > 0:
        freq_matching_yyyy_qn = len(
            [x for x in directories_matching_yyyy_qn if x]
        ) / len(directories_matching_yyyy_qn)
        if freq_matching_yyyy_qn > 0.8:
            project_path = project_path_dir / Path(year_quartal_prefix + project_name)
        if freq_matching_yyyy_qn > 0.3 and freq_matching_yyyy_qn <= 0.8:
            if "y" == input(
                "Several directories with YYYY_Qn_ prefix."
                " Prefix this project as well? (y/n)"
            ):
                project_path = (
                    project_path_dir + "/" + year_quartal_prefix + project_name
                )

    return project_path


def main():

    print("Templates available: ")
    print("\n".join(os.listdir(os.path.expanduser("~") + "/ownCloud/checklists/")))

    project_name = input("Project name (should be easy to pronounce!): ")
    project_name = project_name.replace(" ", "_")

    now = datetime.datetime.now()
    year_quartal_prefix = (
        str(now.year) + "_Q" + str(math.ceil((max(now.month, 2) - 1) / 3)) + "_"
    )

    project_path = get_project_path_dir(project_name, year_quartal_prefix)

    if os.path.exists(project_path):
        print(f"project_path already exists! ({project_path})")
    else:
        os.mkdir(project_path)
        os.mkdir(project_path / "archive")
        os.mkdir(project_path / "wip")

        outfile = open(project_path / "readme.md", "w", encoding="utf-8")
        outfile.write("# Outline\n- Goal: ")
        outfile.write(input("Project goal:"))
        outfile.write("\n- Deliverables:")
        outfile.write("\n - [ ] " + input("Deliverables (comma-seperated):"))
        outfile.write(
            "\n- Partners and Stakeholders: " + input("Partners and Stakeholders:")
        )
        outfile.write(
            "\n- Starting Date:" + datetime.datetime.today().strftime("%Y-%m-%d") + "\n"
        )
        outfile.close()

        if "data/service/reviewer" in str(project_path):
            print(project_path)
            print(os.path.expanduser("~") + "/ownCloud/checklists/peer_review/")
            input(project_path / "/peer-review-checklist/")
            os.symlink(
                os.path.expanduser("~") + "/ownCloud/checklists/review/",
                project_path / "peer-review-checklist",
            )
            input(
                "TODO: add template from https://digital-work-lab.github.io/handbook/docs/50-service/50_processes/50.10.reviewer.html"
            )
            # shutil.copy(
            #     os.path.expanduser("~") + "/ownCloud/checklists/review/template.md",
            #     project_path / "/wip/review.md",
            # )

        input("Check knowledge database and link relevant literature directories.")

        # if os.path.exists(
        #     os.path.expanduser("~")
        #     + "/ownCloud/projects/"
        #     + project_name.replace(year_quartal_prefix, "")
        # ):
        #     input("other project path already linked in ownCloud/projects!")
        # else:
        #     os.symlink(
        #         project_path,
        #         os.path.expanduser("~")
        #         + "/ownCloud/projects/"
        #         + project_name.replace(year_quartal_prefix, ""),
        #     )

        # projects_archive_link = (
        #     os.path.expanduser("~")
        #     + "/ownCloud/projects/Archive/"
        #     + str(now.year)
        #     + "/"
        #     + year_quartal_prefix
        #     + project_name
        # )
        # Path(projects_archive_link).parent.mkdir(exist_ok=True, parents=True)

        # if os.path.exists(projects_archive_link):
        #     input("other project path already linked in ownCloud/projects!")
        # else:
        #     os.symlink(project_path, projects_archive_link)

        # subprocess.call(
        #     "nautilus --browser "
        #     + os.path.expanduser("~")
        #     + "/ownCloud/projects/"
        #     + project_name.replace(year_quartal_prefix, ""),
        #     shell=True,
        # )

        print("successful")

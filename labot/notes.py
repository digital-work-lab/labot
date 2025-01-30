#! /usr/bin/env python3
"""Labot notes management."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import colrev.constants
import colrev.env.environment_manager
import colrev.env.local_index
import colrev.env.tei_parser
import colrev.exceptions as colrev_exceptions
import colrev.loader.load_utils
import colrev.record.record_id_setter
import inquirer
from colrev.constants import RecordState
from colrev.packages.crossref.src import crossref_api
from colrev.writer.write_utils import write_file
from git import Actor
from git import Repo

import labot.utils

references_file = Path("references.bib")
event_name = os.getenv("GITHUB_EVENT_NAME")
# tbd. whether the check is adequate
local_mode = event_name is None

labot_actor = Actor("digital-work-labot", "digital-work-labot@users.noreply.github.com")


def get_missing_references(pdfs: list, references: dict) -> list:
    missing_references = []
    for pdf in pdfs:
        if pdf.stem not in references:
            missing_references.append(pdf.stem)
    return missing_references


def get_missing_paper_summaries(papers_paths: list, references: dict) -> list:
    papers = [str(paper_path.stem) for paper_path in papers_paths]
    missing_paper_summaries = []
    for reference in references:
        if reference not in papers:
            missing_paper_summaries.append(reference)
    return missing_paper_summaries


def create_paper_summary(missing_paper_summary: dict, references: dict) -> None:

    paper_metadata = references[missing_paper_summary]
    paper_summary = Path(f"papers/{missing_paper_summary}.md")

    matching_connections = []
    for concept in Path("concepts").iterdir():
        concept_str = concept.stem.replace("_", " ")
        if (
            concept_str in paper_metadata.get("abstract", "NA").lower()
            or concept_str in paper_metadata["title"].lower()
        ):
            matching_connections.append(concept.stem)

    template = labot.utils.get_template("literature_note.md.j2")

    with open(paper_summary, "w") as file:

        rendered_content = template.render(
            paper_metadata=paper_metadata,
            matching_connections=matching_connections,
        )
        file.write(rendered_content)

        # f.write(f"# {paper_metadata['title']}\n\n")
        # f.write(f"## Abstract\n\n{paper_metadata.get('abstract', 'no-abstract')}\n\n")
        # f.write("<Core takeaways from the research>\n\n")
        # if matching_connections:
        #     f.write("## Connections\n\n")
        #     for connection in matching_connections:
        #         f.write(f"- [[{connection}]]\n")
        #     f.write("- [ ] Add other connections manually\n")
        # else:
        #     f.write(
        #         "## Connections\n\n<Links to overarching concepts from the concepts/ directory>"
        #     )


def import_missing_references(missing_references: list, references: dict) -> None:

    environment_manager = colrev.env.environment_manager.EnvironmentManager()
    local_index = colrev.env.local_index.LocalIndex()
    api = crossref_api.CrossrefAPI(params={})

    for missing_reference in missing_references:
        print(f"Extracting {missing_reference}")
        pdf_path = Path.cwd() / Path(f"pdfs/{missing_reference}.pdf")

        if not local_mode:
            print(f"Fetching {pdf_path} using Git LFS...")
            try:
                subprocess.run(
                    ["git", "lfs", "pull", "--include", str(pdf_path)], check=True
                )
                print(f"Successfully fetched: {pdf_path}")
            except subprocess.CalledProcessError as e:
                print(f"Failed to fetch {pdf_path}. Error: {e}")

        try:
            colrev_pdf_id = colrev.record.record_identifier.get_colrev_pdf_id(pdf_path)
            new_record_object = local_index.retrieve_based_on_colrev_pdf_id(
                colrev_pdf_id=colrev_pdf_id
            )
            retrieved_record_dict = new_record_object.data

        except (
            colrev_exceptions.RecordNotInIndexException,
            colrev_exceptions.InvalidPDFException,
        ):

            tei = colrev.env.tei_parser.TEIParser(
                environment_manager=environment_manager,
                pdf_path=pdf_path,
            )
            retrieved_record_dict = tei.get_metadata()
            if "doi" in retrieved_record_dict:
                retrieved_record_dict = api.query_doi(
                    doi=retrieved_record_dict["doi"]
                ).data

        # remove all fields starting with "colrev_"
        retrieved_record_dict = {
            key: value
            for key, value in retrieved_record_dict.items()
            if not key.startswith("colrev")
        }
        # also remove curation_ID and language
        retrieved_record_dict.pop("curation_ID", None)
        retrieved_record_dict.pop("language", None)
        id_setter = colrev.record.record_id_setter.IDSetter(
            id_pattern=colrev.constants.IDPattern.three_authors_year,
            skip_local_index=False,
        )
        retrieved_record_dict[colrev.constants.Fields.STATUS] = RecordState.md_imported
        updated_record = id_setter.set_ids(
            records={"record": retrieved_record_dict},
        )

        retrieved_record_dict = next(iter(updated_record.values()))
        retrieved_record_dict.pop(colrev.constants.Fields.STATUS, None)

        if "ID" not in retrieved_record_dict:
            retrieved_record_dict["ID"] = missing_reference

        # TODO : if it already exists?!
        references[retrieved_record_dict["ID"]] = retrieved_record_dict

        new_file = (
            Path.cwd() / Path("pdfs") / Path(f"{retrieved_record_dict['ID']}.pdf")
        )
        note_file = Path.cwd() / Path("papers") / Path(f"{missing_reference}.md")
        summary_file = (
            Path.cwd() / Path("papers") / Path(f"{retrieved_record_dict['ID']}.md")
        )

        try:
            pdf_path.rename(new_file)
            if note_file.exists():
                note_file.rename(summary_file)
            if pdf_path != new_file:
                print(f"Renamed file: {pdf_path} -> {new_file}")
        except Exception as e:
            print(f"Error renaming file: {e}")

    write_file(records_dict=references, filename=references_file)


def check_notes(local_repo: Repo = None) -> None:

    pdfs = list(Path("pdfs").iterdir())
    papers = list(Path("papers").iterdir())
    # concepts = list(Path('concepts').iterdir())

    references = colrev.loader.load_utils.load(
        filename=references_file,
    )

    missing_references = get_missing_references(pdfs, references)
    import_missing_references(missing_references, references)

    missing_paper_summaries = get_missing_paper_summaries(papers, references)
    print(missing_paper_summaries)
    for missing_paper_summary in missing_paper_summaries:
        create_paper_summary(missing_paper_summary, references)

    if not missing_references and not missing_paper_summaries:
        return

    if local_mode and local_repo.active_branch.name == "main":
        # use inquirer library and ask to switch to a new branch
        # Ask user which branch to switch to
        branch_choices = (
            missing_paper_summaries + missing_references + ["Create new branch"]
        )
        questions = [
            inquirer.List(
                "branch",
                message="Select the branch to work on",
                choices=list(set(branch_choices)),
            )
        ]

        answers = inquirer.prompt(questions)

        if answers:
            selected_branch = answers["branch"]
            if selected_branch == "Create new branch":
                selected_branch = input("Enter the name of the new branch: ")
                local_repo.git.checkout("main")
                local_repo.git.checkout("-b", selected_branch)
                print(f"Created and switched to branch '{selected_branch}'")
            # Switch to the selected branch
            local_repo.git.checkout("-b", selected_branch)
            print(f"Switched to branch '{selected_branch}'")
        else:
            print("No branch selected.")

    assert local_repo
    local_repo.git.add("pdfs*")
    local_repo.git.add("papers*")
    local_repo.git.add("references.bib")
    local_repo.index.commit(
        "Prepare paper summaries 🚀", author=labot_actor, committer=labot_actor
    )

    if event_name == "pull_request":
        origin = local_repo.remotes.origin
        origin.push()

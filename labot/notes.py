#! /usr/bin/env python3
"""Labot notes management."""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import List

import colrev.env.local_index
import colrev.env.tei_parser
import colrev.exceptions as colrev_exceptions
import colrev.loader.load_utils
import colrev.record.record_id_setter
import colrev.record.record_pdf
import git
import inquirer
from colrev.constants import ENTRYTYPES
from colrev.constants import Fields
from colrev.constants import IDPattern
from colrev.constants import RecordState
from colrev.packages.crossref.src import crossref_api
from colrev.writer.write_utils import write_file
from git import Actor
from git import Repo
from pdfannots import process_file
from pdfannots.printer.markdown import GroupedMarkdownPrinter
from pdfannots.printer.markdown import MarkdownPrinter

import labot.utils


event_name = os.getenv("GITHUB_EVENT_NAME")
# tbd. whether the check is adequate
local_mode = event_name is None

labot_actor = Actor("digital-work-labot", "digital-work-labot@users.noreply.github.com")


class LabotNotesManager:
    def __init__(
        self,
        pdf_path: Path,
        papers_path: Path,
        references_path: Path,
        concepts_path: Path,
    ):
        self.pdf_path = pdf_path
        self.papers_path = papers_path
        self.references_path = references_path
        self.concepts_path = concepts_path
        self.references = self._load_references()
        self.local_mode = os.getenv("GITHUB_EVENT_NAME") is None
        self.actor = Actor(
            "digital-work-labot", "digital-work-labot@users.noreply.github.com"
        )

    def _load_references(self) -> dict:
        return colrev.loader.load_utils.load(filename=self.references_path)

    def get_missing_references(self) -> List[str]:
        pdfs = {pdf.stem for pdf in self.pdf_path.glob("*.pdf")}
        return sorted(pdfs - set(self.references.keys()))

    def get_missing_paper_summaries(self) -> List[str]:
        papers = {p.stem for p in self.papers_path.glob("*.md")}
        return sorted(set(self.references.keys()) - papers)

    def get_pdf_highlights(self, pdf_file: Path, grouped=True) -> str:

        printer = GroupedMarkdownPrinter() if grouped else MarkdownPrinter()
        doc = process_file(open(pdf_file, "rb"))
        output = printer.begin()
        output += "".join(printer.print_file(pdf_file, doc))
        output += printer.end()
        return output

    def create_summary(self, missing_summary: str) -> None:
        paper_metadata = self.references[missing_summary]
        paper_file = self.pdf_path / f"{missing_summary}.pdf"
        output_md = self.papers_path / f"{missing_summary}.md"

        if not paper_file.exists():
            return

        highlights = self.get_pdf_highlights(paper_file)
        paper_metadata["highlights"] = highlights

        connections = []
        for concept in self.concepts_path.iterdir():
            concept_str = concept.stem.replace("_", " ").lower()
            if (
                concept_str in paper_metadata.get("abstract", "").lower()
                or concept_str in paper_metadata["title"].lower()
            ):
                connections.append(concept.stem)

        template = labot.utils.get_template("literature_note.md.j2")
        rendered = template.render(
            paper_metadata=paper_metadata, matching_connections=connections
        )

        with open(output_md, "w") as file:
            file.write(rendered)

    def create_summaries(self, summaries: List[str]) -> None:
        for sid in summaries:
            self.create_summary(sid)

    def import_missing_references(self, missing_refs: List[str]) -> None:
        local_index = colrev.env.local_index.LocalIndex()
        api = crossref_api.CrossrefAPI(url="https://api.crossref.org/")

        for ref_id in missing_refs:
            pdf_file = self.pdf_path / f"{ref_id}.pdf"
            if not pdf_file.exists():
                continue

            if not self.local_mode:
                try:
                    subprocess.run(
                        ["git", "lfs", "pull", "--include", str(pdf_file)], check=True
                    )
                except subprocess.CalledProcessError:
                    continue

            try:
                colrev_pdf_id = colrev.record.record_identifier.get_colrev_pdf_id(
                    pdf_file
                )
                record_obj = local_index.retrieve_based_on_colrev_pdf_id(
                    colrev_pdf_id=colrev_pdf_id
                )
                record = record_obj.data
            except (
                colrev_exceptions.RecordNotInIndexException,
                colrev_exceptions.InvalidPDFException,
            ):
                try:
                    tei = colrev.env.tei_parser.TEIParser(pdf_path=pdf_file)
                    record = tei.get_metadata()
                except Exception:
                    record = {
                        Fields.ID: ref_id,
                        Fields.ENTRYTYPE: ENTRYTYPES.ARTICLE,
                        Fields.FILE: pdf_file,
                    }

                try:
                    pdf_rec = colrev.record.record_pdf.PDFRecord(
                        record, path=pdf_file.parent
                    )
                    if Fields.DOI not in record:
                        pdf_rec.set_text_from_pdf()
                        match = re.findall(
                            r"10\.\d{4,9}/[-._;/:A-Za-z0-9]*",
                            pdf_rec.data.get(Fields.TEXT_FROM_PDF, ""),
                        )
                        if match:
                            record[Fields.DOI] = match[0].upper()
                    record.pop(Fields.TEXT_FROM_PDF, None)
                    record.pop(Fields.NR_PAGES_IN_FILE, None)
                except colrev_exceptions.InvalidPDFException:
                    continue

            if Fields.DOI in record:
                try:
                    record = api.query_doi(doi=record[Fields.DOI]).data
                except colrev_exceptions.RecordNotFoundInPrepSourceException:
                    pass

            record = {k: v for k, v in record.items() if not k.startswith("colrev")}
            record.pop("curation_ID", None)
            record.pop("language", None)

            id_setter = colrev.record.record_id_setter.IDSetter(
                id_pattern=IDPattern.three_authors_year, skip_local_index=False
            )
            record[Fields.STATUS] = RecordState.md_imported
            updated = id_setter.set_ids(records={"record": record})
            record = next(iter(updated.values()))
            record.pop(Fields.STATUS, None)
            record.setdefault("ID", ref_id)

            self.references[record["ID"]] = record

            try:
                new_pdf = self.pdf_path / f"{record['ID']}.pdf"
                note_md = self.papers_path / f"{ref_id}.md"
                summary_md = self.papers_path / f"{record['ID']}.md"

                if pdf_file != new_pdf:
                    pdf_file.rename(new_pdf)
                if note_md.exists():
                    note_md.rename(summary_md)
            except Exception as e:
                print(f"Rename failed: {e}")

        write_file(records_dict=self.references, filename=self.references_path)

    def finalize_git_commit(self, ref_ids: List[str], summary_ids: List[str]) -> None:
        repo = Repo(Path.cwd())

        if self.local_mode and repo.active_branch.name == "main":
            choices = sorted(
                list(set(["main", "Create new branch"] + ref_ids + summary_ids))
            )
            selected = inquirer.prompt(
                [
                    inquirer.List(
                        "branch",
                        message="Select the branch to work on",
                        choices=choices,
                    )
                ]
            )
            if selected:
                branch = selected["branch"]
                if branch == "Create new branch":
                    branch = input("Enter branch name: ")
                    repo.git.checkout("main")
                    repo.git.checkout("-b", branch)
                else:
                    # does the branch already exist?
                    exists = branch in [h.name for h in repo.heads]

                    if exists:
                        repo.git.checkout(branch)
                    else:
                        repo.git.checkout("-b", branch)

        try:
            repo.git.add(str(self.pdf_path) + "*")
        except git.exc.GitCommandError:
            pass
        repo.git.add(str(self.papers_path) + "*")
        repo.git.add(str(self.references_path))
        repo.index.commit(
            "Prepare paper summaries 🚀", author=self.actor, committer=self.actor
        )

        if os.getenv("GITHUB_EVENT_NAME") == "pull_request":
            repo.remotes.origin.push()

    def run(
        self, select_summaries: bool = False, add_missing_refs: bool = False
    ) -> None:
        missing_refs = []
        if add_missing_refs:
            missing_refs = self.get_missing_references()
            print(f"Missing references: {len(missing_refs)}")
            self.import_missing_references(missing_refs)

        missing_summaries = self.get_missing_paper_summaries()
        if select_summaries and missing_summaries:
            response = inquirer.prompt(
                [
                    inquirer.Checkbox(
                        "to_create",
                        message="Select paper summaries to create",
                        choices=missing_summaries,
                    )
                ]
            )
            selected_summaries = response.get("to_create", [])
        else:
            selected_summaries = missing_summaries

        self.create_summaries(selected_summaries)
        self.finalize_git_commit(missing_refs, selected_summaries)


def check_notes_local() -> None:

    if Path("papers").exists() and Path("references.bib").exists():
        LabotNotesManager(
            pdf_path=Path("pdfs"),
            papers_path=Path("papers"),
            references_path=Path("references.bib"),
            concepts_path=Path("concepts"),
        ).run(select_summaries=True, add_missing_refs=True)
    else:
        LabotNotesManager(
            pdf_path=Path("data/pdfs"),
            papers_path=Path("data/obsidian/paper"),
            references_path=Path("data/records.bib"),
            concepts_path=Path("data/obsidian/concepts"),
        ).run(select_summaries=True)


def check_notes_github() -> None:
    LabotNotesManager(
        pdf_path=Path("pdfs"),
        papers_path=Path("papers"),
        references_path=Path("references.bib"),
        concepts_path=Path("concepts"),
    ).run(select_summaries=False, add_missing_refs=True)

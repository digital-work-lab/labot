#! /usr/bin/env python3
"""Labot notes management."""
from __future__ import annotations

from pathlib import Path

import colrev.env.environment_manager
import colrev.env.local_index
import colrev.env.tei_parser
import colrev.exceptions as colrev_exceptions
import colrev.loader.load_utils
from colrev.packages.crossref.src import crossref_api
from colrev.writer.write_utils import write_file

references_file = Path("references.bib")


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
            concept_str in paper_metadata["abstract"].lower()
            or concept_str in paper_metadata["title"].lower()
        ):
            matching_connections.append(concept.stem)

    with open(paper_summary, "w") as f:
        f.write(f"# {paper_metadata['title']}\n\n")
        f.write(f"## Abstract\n\n{paper_metadata.get('abstract', 'no-abstract')}\n\n")
        f.write("<Core takeaways from the research>\n\n")
        if matching_connections:
            f.write("## Connections\n\n")
            for connection in matching_connections:
                f.write(f"- [[{connection}]]\n")
            f.write("- [ ] Add other connections manually\n")
        else:
            f.write(
                "## Connections\n\n<Links to overarching concepts from the concepts/ directory>"
            )


def import_missing_references(missing_references: list, references: dict) -> None:

    environment_manager = colrev.env.environment_manager.EnvironmentManager()
    local_index = colrev.env.local_index.LocalIndex()
    api = crossref_api.CrossrefAPI(params={})

    for missing_reference in missing_references:
        print(f"Extracting {missing_reference}")
        pdf_path = Path.cwd() / Path(f"pdfs/{missing_reference}.pdf")

        try:
            colrev_pdf_id = colrev.record.record_identifier.get_colrev_pdf_id(pdf_path)
            new_record_object = local_index.retrieve_based_on_colrev_pdf_id(
                colrev_pdf_id=colrev_pdf_id
            )
            retrieved_record = new_record_object

        except colrev_exceptions.RecordNotInIndexException:

            tei = colrev.env.tei_parser.TEIParser(
                environment_manager=environment_manager,
                pdf_path=pdf_path,
            )
            retrieved_record = tei.get_metadata()
            if "doi" in retrieved_record:
                retrieved_record = api.query_doi(doi=retrieved_record["doi"])

        # TODO/TBD: rename pdf? update key?
        if missing_reference not in references:
            references[missing_reference] = retrieved_record.data
        else:
            print(f"Reference {missing_reference} already exists in references")
            continue
        break  # TODO : tbd: add all or selected?

    write_file(records_dict=references, filename=references_file)


def check_notes() -> None:

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


if __name__ == "__main__":
    check_notes()

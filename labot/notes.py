#! /usr/bin/env python3
"""Labot notes management."""
from __future__ import annotations

from pathlib import Path

import colrev.loader.load_utils


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
    with open(paper_summary, "w") as f:
        f.write(f"# {paper_metadata['title']}\n\n")
        f.write(f"## Abstract\n\n{paper_metadata.get('abstract', 'no-abstract')}\n\n")
        f.write("<Core takeaways from the research>\n\n")
        f.write(
            "## Connections\n\n<Links to overarching concepts from the concepts/ directory>"
        )


def check_notes() -> None:

    pdfs = list(Path("pdfs").iterdir())
    papers = list(Path("papers").iterdir())
    # concepts = list(Path('concepts').iterdir())

    references_file = Path("references.bib")
    references = colrev.loader.load_utils.load(
        filename=references_file,
    )

    missing_references = get_missing_references(pdfs, references)
    print(f"TODO : add references for {missing_references}")

    # TODO/TBD: rename pdf before? / get pdfs again?
    missing_paper_summaries = get_missing_paper_summaries(papers, references)
    print(missing_paper_summaries)
    for missing_paper_summary in missing_paper_summaries:
        create_paper_summary(missing_paper_summary, references)
    # print(pdfs)
    # print(papers)
    # print(references)


if __name__ == "__main__":
    check_notes()

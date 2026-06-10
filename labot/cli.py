#! /usr/bin/env python3
"""Command-line interface for Labot."""
from __future__ import annotations

from pathlib import Path

import click


@click.group()
@click.pass_context
def main(ctx: click.core.Context) -> None:
    """Labot commands:

    \b
    status        Shows status, including tasks etc.
    thesis        Thesis registration, grading, ...

    \b
    Documentation:  TODO
    """


@main.command()
@click.option(
    "-v",
    "--verbose",
    is_flag=True,
    default=False,
    help="Verbose: printing more infos",
)
@click.pass_context
def status(
    ctx: click.core.Context,
    verbose: bool,
) -> None:
    """Show status"""
    import labot.status

    labot.status.print_status()


@main.command  # (help_priority=1)
@click.option(
    "--submissions",
    is_flag=True,
    default=False,
    help="Process submissions",
)
@click.option(
    "--register",
    is_flag=True,
    default=False,
    help="Register a thesis",
)
@click.option(
    "--grade",
    is_flag=True,
    default=False,
    help="Grade a thesis",
)
@click.pass_context
def thesis(
    ctx: click.core.Context,
    submissions: bool,
    grade: bool,
    register: bool,
) -> None:
    "Thesis utils (register, submissions, grade)"

    if grade:
        import labot.thesis

        labot.thesis.grade()
        return

    # Thesis repo commands
    import labot.thesis_repo

    tr = labot.thesis_repo.ThesisRepo()

    if register:
        tr.registrations()

    if submissions:
        tr.submissions()


@main.command  # (help_priority=1)
@click.option(
    "--prep",
    is_flag=True,
    help="Prep a paper",
)
@click.option(
    "--revise",
    is_flag=True,
    help="Revise a paper",
)
@click.pass_context
def paper(
    ctx: click.core.Context,
    prep: bool,
    revise: bool,
) -> None:
    "Paper utils (init, prep, ...)"
    import labot.paper

    if prep:
        labot.paper.prep()
    elif revise:
        labot.paper.revise()


@main.command
@click.option(
    "--github",
    is_flag=True,
    help="Prep notes for github (e.g., research-ub)",
)
@click.pass_context
def notes(ctx: click.core.Context, github: bool) -> None:
    """Process notes (e.g., research-ub)"""
    import labot.notes

    if github:
        labot.notes.check_notes_github()
        return
    labot.notes.check_notes_local()


@main.command
@click.pass_context
def create_project(
    ctx: click.core.Context,
) -> None:
    "Create a project (directory)"
    import labot.create_project

    labot.create_project.main()


@main.command  # (help_priority=1)
@click.option(
    "--links",
    is_flag=True,
    help="Check and update links (setting target=blank)",
)
@click.pass_context
def handbook(
    ctx: click.core.Context,
    links: bool,
) -> None:
    "Handbook checks"
    import labot.handbook

    if links:
        labot.handbook.link_check()


@main.command
@click.pass_context
def local_cronjob(
    ctx: click.core.Context,
) -> None:
    "Run local cronjob"
    import labot.local_cron

    labot.local_cron.main()


@main.command
@click.pass_context
def polish(
    ctx: click.core.Context,
) -> None:
    "Polish files (using LLM)"
    import labot.polish

    labot.polish.main()


@main.group()
@click.pass_context
def references(ctx: click.core.Context) -> None:
    """Reference processing commands."""


@references.command()
@click.argument("input_path", type=click.Path(path_type=Path, exists=True))
@click.option("-o", "--output", "output_path", type=click.Path(path_type=Path))
@click.option("--report", "report_path", type=click.Path(path_type=Path))
@click.option("--mailto", type=str)
@click.option(
    "--crossref-mode",
    type=click.Choice(["auto", "colrev", "rest"]),
    default="auto",
    show_default=True,
)
@click.option("--auto-accept-threshold", type=float, default=0.92, show_default=True)
@click.option("--non-interactive", is_flag=True)
@click.option("--all", "display_all", is_flag=True)
@click.option("--diagnostics", is_flag=True)
@click.option("--diagnostics-limit", type=int, default=15, show_default=True)
@click.option("--minimum-match-similarity", type=float, default=0.50, show_default=True)
@click.option("--limit", "reference_limit", type=int, default=0, show_default=True)
@click.pass_context
def consolidate(
    ctx: click.core.Context,
    input_path: Path,
    output_path: Path | None,
    report_path: Path | None,
    mailto: str | None,
    crossref_mode: str,
    auto_accept_threshold: float,
    non_interactive: bool,
    display_all: bool,
    diagnostics: bool,
    diagnostics_limit: int,
    minimum_match_similarity: float,
    reference_limit: int,
) -> None:
    """Consolidate references extracted from a paper PDF or GROBID TEI file."""
    from typing import Literal, cast

    from labot.references.consolidate_grobid_references import run

    selected_crossref_mode = cast(Literal["auto", "colrev", "rest"], crossref_mode)

    raise SystemExit(
        run(
            input_path=input_path,
            output_path=output_path,
            report_path=report_path,
            mailto=mailto,
            crossref_mode=selected_crossref_mode,
            auto_accept_threshold=auto_accept_threshold,
            non_interactive=non_interactive,
            display_all=display_all,
            diagnostics=diagnostics,
            diagnostics_limit=diagnostics_limit,
            minimum_match_similarity=minimum_match_similarity,
            reference_limit=reference_limit,
        )
    )


@main.command()
@click.option("--all", "all_files", is_flag=True, help="Check all .qmd and .md files")
@click.option("--file", type=click.Path(path_type=Path, exists=True), help="Check a specific file")
@click.option("-i", "--interactive", is_flag=True, help="Interactively select a file")
@click.pass_context
def spellcheck(
    ctx: click.core.Context,
    all_files: bool,
    file: Path | None,
    interactive: bool,
) -> None:
    """Run spellcheck using a local LanguageTool server."""
    import labot.spellcheck

    raise SystemExit(
        labot.spellcheck.main(
            all_files=all_files,
            file=file,
            interactive=interactive,
        )
    )


@main.command()
@click.pass_context
def version(
    ctx: click.core.Context,
) -> None:
    """Show labot version."""

    from importlib.metadata import version

    print(f'labot version {version("labot")}')


@main.command("sync-paper-to-obsidian")
@click.option("--paper-path", type=click.Path(path_type=Path))
@click.option("--bib-path", type=click.Path(path_type=Path))
@click.option("--vault-path", type=click.Path(path_type=Path))
@click.option("--project-id", type=str)
@click.option("--dry-run", is_flag=True)
@click.option("--verbose", is_flag=True)
@click.pass_context
def sync_paper_to_obsidian(
    ctx: click.core.Context,
    paper_path: Path | None,
    bib_path: Path | None,
    vault_path: Path | None,
    project_id: str | None,
    dry_run: bool,
    verbose: bool,
) -> None:
    """Synchronize a Quarto paper repository with an Obsidian vault."""
    from labot.sync.paper_to_obsidian import run_sync_pipeline

    def prompt_path(message: str) -> Path:
        from InquirerPy import inquirer

        return Path(inquirer.filepath(message=message).execute()).expanduser()

    def prompt_text(message: str) -> str:
        from InquirerPy import inquirer

        return inquirer.text(message=message).execute().strip()

    if paper_path is None:
        paper_path = prompt_path("Path to paper .qmd:")
    if bib_path is None:
        bib_path = prompt_path("Path to bibliography .bib:")
    if vault_path is None:
        vault_path = prompt_path("Path to Obsidian vault root:")
    if project_id is None:
        project_id = prompt_text("Project ID (e.g., lrdm):")

    run_sync_pipeline(
        paper_path=paper_path,
        bib_path=bib_path,
        vault_path=vault_path,
        project_id=project_id,
        dry_run=dry_run,
        verbose=verbose,
    )

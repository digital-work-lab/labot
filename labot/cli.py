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

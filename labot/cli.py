#! /usr/bin/env python3
"""Command-line interface for Labot."""
from __future__ import annotations

from pathlib import Path

import click
from git import Repo


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
    "--init",
    is_flag=True,
    help="Initialize a paper repository",
)
@click.option(
    "--prep",
    is_flag=True,
    help="Prep a paper",
)
@click.pass_context
def paper(
    ctx: click.core.Context,
    init: bool,
    prep: bool,
) -> None:
    import labot.paper

    if init:
        labot.paper.init()
    elif prep:
        labot.paper.prep()


@main.command
@click.pass_context
def notes(
    ctx: click.core.Context,
) -> None:
    import labot.notes

    local_repo = Repo(Path.cwd())

    labot.notes.check_notes(local_repo=local_repo)


@main.command
@click.pass_context
def create_project(
    ctx: click.core.Context,
) -> None:
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
    import labot.handbook

    if links:
        labot.handbook.link_check()


@main.command()
@click.pass_context
def check(
    ctx: click.core.Context,
) -> None:
    """Check"""
    import labot.check

    labot.check.main()


@main.command()
@click.pass_context
def version(
    ctx: click.core.Context,
) -> None:
    """Show colrev version."""

    from importlib.metadata import version

    print(f'colrev version {version("colrev")}')

#! /usr/bin/env python3
"""Command-line interface for Labot."""
from __future__ import annotations

import click
import click_completion.core


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
    "--grade",
    is_flag=True,
    default=False,
    help="Grade a thesis",
)
@click.pass_context
def thesis(
    ctx: click.core.Context,
    grade: bool,
) -> None:
    import labot.thesis

    if grade:
        labot.thesis.grade()


@main.command  # (help_priority=1)
@click.option(
    "--init",
    is_flag=True,
    help="Initialize a paper repository",
)
@click.pass_context
def paper(
    ctx: click.core.Context,
    init: bool,
) -> None:
    import labot.paper

    if init:
        labot.paper.init()


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


@main.command(hidden=True)
@click.option(
    "-i", "--case-insensitive/--no-case-insensitive", help="Case insensitive completion"
)
@click.argument(
    "shell",
    required=False,
    type=click_completion.DocumentedChoice(click_completion.core.shells),
)
def show_click(shell, case_insensitive) -> None:  # type: ignore
    """Show the click-completion-command completion code"""
    extra_env = (
        {"_CLICK_COMPLETION_COMMAND_CASE_INSENSITIVE_COMPLETE": "ON"}
        if case_insensitive
        else {}
    )
    click.echo(click_completion.core.get_code(shell, extra_env=extra_env))


@main.command(hidden=True)
@click.option(
    "--append/--overwrite", help="Append the completion code to the file", default=None
)
@click.option(
    "-i", "--case-insensitive/--no-case-insensitive", help="Case insensitive completion"
)
@click.argument(
    "shell",
    required=False,
    type=click_completion.DocumentedChoice(click_completion.core.shells),
)
@click.argument("path", required=False)
def install_click(append, case_insensitive, shell, path) -> None:  # type: ignore
    """Install the click-completion-command completion"""
    extra_env = (
        {"_CLICK_COMPLETION_COMMAND_CASE_INSENSITIVE_COMPLETE": "ON"}
        if case_insensitive
        else {}
    )
    shell, path = click_completion.core.install(  # nosec
        shell=shell, path=path, append=append, extra_env=extra_env
    )
    click.echo(f"{shell} completion installed in {path}")

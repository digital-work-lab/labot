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


# @main.command(help_priority=1)
# @click.option(
#     "--type",
#     type=click.Choice(TYPE_IDENTIFIER_ENDPOINT_DICT[EndpointType.review_type]),
#     default="colrev.literature_review",
#     help="Review type for the setup.",
# )
# @click.option(
#     "-f",
#     "--force",
#     is_flag=True,
#     default=False,
#     help="Force mode",
# )
# @click.option(
#     "--light",
#     is_flag=True,
#     default=False,
#     help="Setup a lightweight repository (without Docker services)",
# )
# @click.option(
#     "--example",
#     is_flag=True,
#     default=False,
#     help="Add search results example",
# )
# @click.option(
#     "-lpdf",
#     "--local_pdf_collection",
#     is_flag=True,
#     default=False,
#     help="Add a local PDF collection repository",
# )
# @click.pass_context
# @catch_exception(handle=(colrev_exceptions.CoLRevException))
# def init(
#     ctx: click.core.Context,
#     type: str,
#     example: bool,
#     force: bool,
#     light: bool,
#     local_pdf_collection: bool,
# ) -> None:
#     """Initialize (define review objectives and type)

#     Docs: https://colrev.readthedocs.io/en/latest/manual/problem_formulation/init.html
#     """
#     import colrev.ops.init

#     colrev.ops.init.Initializer(
#         review_type=type,
#         target_path=Path.cwd(),
#         example=example,
#         force_mode=force,
#         light=light,
#         local_pdf_collection=local_pdf_collection,
#         exact_call=EXACT_CALL,
#     )


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

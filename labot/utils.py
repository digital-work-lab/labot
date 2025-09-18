#! /usr/bin/env python3
"""Labot utils."""
import typing
from pathlib import Path

from jinja2 import Environment
from jinja2 import PackageLoader
from jinja2 import Template


def get_template(filename: str) -> Template:

    env = Environment(loader=PackageLoader("labot", "templates"))
    template = env.get_template(filename)
    return template


def get_git_dir(*, path_str: typing.Optional[str] = None) -> Path:
    """Get the git directory"""
    if path_str:
        original_dir = Path(path_str)
    else:
        original_dir = Path.cwd()

    while ".git" not in [f.name for f in original_dir.iterdir() if f.is_dir()]:
        if original_dir.parent == original_dir:  # reached root
            break
        original_dir = original_dir.parent

    if original_dir.parent == original_dir:  # reached root
        raise Exception(
            "Failed to locate a .git directory. Ensure you are within a Git repository."
        )

    return original_dir

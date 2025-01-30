#! /usr/bin/env python3
"""Labot utils."""

from jinja2 import Environment
from jinja2 import PackageLoader, Template


def get_template(filenmae: str) -> Template:

    env = Environment(loader=PackageLoader("labot", "templates"))
    template = env.get_template("literature_note.md.j2.md")
    return template
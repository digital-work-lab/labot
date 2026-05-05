#!/usr/bin/env python3
"""Check Quarto/Markdown files with LanguageTool."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
import re
import sys

import requests

LANGUAGETOOL_URL = "http://localhost:8081/v2/check"
IGNORE_FILE = Path(".languagetool-ignore")


def load_ignored_terms() -> set[str]:
    """Load ignored terms from .languagetool-ignore."""
    if not IGNORE_FILE.is_file():
        return set()

    return {
        line.strip()
        for line in IGNORE_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }


def remove_yaml_frontmatter(text: str) -> str:
    return re.sub(r"^---\n.*?\n---\n", " ", text, flags=re.DOTALL)

def remove_code_blocks(text: str) -> str:
    return re.sub(
        r"(?ms)^[ \t]*(```|~~~).*?^[ \t]*\1[ \t]*$",
        " ",
        text,
    )

def remove_inline_code(text: str) -> str:
    return re.sub(r"`[^`]+`", " ", text)


def remove_html_tags(text: str) -> str:
    return re.sub(r"<[^>]+>", " ", text)


def remove_urls(text: str) -> str:
    return re.sub(r"https?://\S+|www\.\S+", " ", text)


def remove_shortcodes(text: str) -> str:
    text = re.sub(r"\{\{<.*?>\}\}", " ", text, flags=re.DOTALL)
    text = re.sub(r"\{\{.*?\}\}", " ", text, flags=re.DOTALL)
    return text


def remove_latex(text: str) -> str:
    text = re.sub(r"\$\$.*?\$\$", " ", text, flags=re.DOTALL)
    text = re.sub(r"\$[^$\n]+\$", " ", text)
    text = re.sub(r"\\[a-zA-Z]+\{.*?\}", " ", text)
    text = re.sub(r"\\[a-zA-Z]+", " ", text)
    return text


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def should_ignore(problematic_text: str, ignored_terms: set[str]) -> bool:
    problematic_text = problematic_text.strip()

    if not problematic_text:
        return True

    if problematic_text in ignored_terms:
        return True

    if re.fullmatch(r"[\W\d_]+", problematic_text):
        return True

    if len(problematic_text) <= 2:
        return True

    html_like = {"div", "td", "tr", "th", "href", "src", "url", "pagebreak", "iconify"}
    if problematic_text.lower() in html_like:
        return True

    if "\\" in problematic_text:
        return True

    if "_" in problematic_text or "-" in problematic_text:
        return True

    return False


def preprocess_text(text: str) -> str:
    text = remove_yaml_frontmatter(text)
    text = remove_code_blocks(text)
    text = remove_inline_code(text)
    text = remove_html_tags(text)
    text = remove_urls(text)
    text = remove_shortcodes(text)
    text = remove_latex(text)
    return normalize_whitespace(text)


def resolve_files(*, all_files: bool, file: Path | None, interactive: bool) -> list[Path]:
    if file is not None:
        return [file]

    if interactive:
        from InquirerPy import inquirer

        candidates = sorted(Path(".").rglob("*.qmd")) + sorted(Path(".").rglob("*.md"))
        if not candidates:
            return []
        selected = inquirer.fuzzy(
            message="Select file to spellcheck:",
            choices=[str(path) for path in candidates],
        ).execute()
        return [Path(selected)]

    if all_files:
        return sorted(Path(".").rglob("*.qmd")) + sorted(Path(".").rglob("*.md"))

    return sorted(Path(".").rglob("*.qmd"))


def main(*, all_files: bool = False, file: Path | None = None, interactive: bool = False) -> int:
    ignored_terms = load_ignored_terms()
    files = resolve_files(all_files=all_files, file=file, interactive=interactive)

    if not files:
        print("No files found.")
        return 0

    has_errors = False
    problematic_terms: Counter[str] = Counter()

    for item in files:
        original_text = item.read_text(encoding="utf-8")
        text = preprocess_text(original_text)

        response = requests.post(
            LANGUAGETOOL_URL,
            data={"text": text, "language": "auto", "preferredVariants": "en-US,de-DE"},
            timeout=30,
        )

        if response.status_code != 200:
            print(f"ERROR: {item} ({response.status_code})")
            print(response.text)
            continue

        matches = response.json().get("matches", [])
        for match in matches:
            context = match.get("context", {})
            context_text = context.get("text", "").replace("\n", " ")
            context_offset = context.get("offset", 0)
            match_length = context.get("length", 0)

            problematic_text = context_text[context_offset : context_offset + match_length].strip()
            if should_ignore(problematic_text, ignored_terms):
                continue

            has_errors = True
            message = match.get("message", "Unknown issue")
            print(f"{item}:{match.get('offset', 0)} {message}")
            print(f"  problematic: {problematic_text}")

            replacements = match.get("replacements", [])
            if replacements:
                suggestions = ", ".join(replacement["value"] for replacement in replacements[:5])
                print(f"  suggestions: {suggestions}")
            print()

            problematic_terms[problematic_text] += 1

    with open("problematic_terms.txt", "w", encoding="utf-8") as stream:
        for term, frequency in problematic_terms.most_common():
            stream.write(f"{frequency}\t{term}\n")

    print(f"Saved {len(problematic_terms)} problematic terms to problematic_terms.txt")

    return 1 if has_errors else 0


if __name__ == "__main__":
    sys.exit(main())

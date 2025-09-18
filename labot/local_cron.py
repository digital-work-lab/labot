import json
import os
import re
from pathlib import Path

from git import Repo

CONFIG_PATH = Path.home() / ".labot/config.json"

START_MARKER = "<!-- labot local-cronjob -->"
END_MARKER = "<!-- END -->"


def load_config():
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"Settings file not found: {CONFIG_PATH}")
    with open(CONFIG_PATH) as f:
        config = json.load(f)
    return config


def parse_volume_issue(name):
    """Parse '43_2' into (43, 2)."""
    match = re.match(r"^(\d+)_(\d+)$", name)
    return (int(match.group(1)), int(match.group(2))) if match else None


def find_latest_issue(journal_path):
    """Return the latest volume/issue or volume-only entry."""
    latest = (0, 0)

    for entry in os.listdir(journal_path):
        entry_path = journal_path / entry
        if not entry_path.is_dir():
            continue

        # Case 1: flat '43_2'
        parsed = parse_volume_issue(entry)
        if parsed:
            latest = max(latest, parsed)
            continue

        # Case 2: nested '43/2'
        if entry.isdigit():
            volume = int(entry)
            sub_entries = list((journal_path / entry).iterdir())
            sub_issues = [
                int(e.name) for e in sub_entries if e.is_dir() and e.name.isdigit()
            ]
            if sub_issues:
                issue = max(sub_issues)
                latest = max(latest, (volume, issue))
            else:
                # Case 3: volume-only folder
                latest = max(latest, (volume, 0))

    return latest if latest != (0, 0) else None


def format_latest(latest):
    return (
        f"{latest[0]}_{latest[1]}"
        if latest and latest[1] > 0
        else (str(latest[0]) if latest else "No valid issues found")
    )


def main():
    import colrev.env.local_index

    journal_folders = colrev.env.local_index.LocalIndex().get_curations()
    journal_folders = [
        folder / Path("data/pdfs") for folder in journal_folders if folder.is_dir()
    ]

    results = []
    for journal_folder in sorted(journal_folders):
        latest = find_latest_issue(journal_folder)
        latest_str = format_latest(latest)
        # journal_folder = .../curation_name/data/pdfs → we use curation_name
        results.append((journal_folder.parent.parent.name, latest_str))

    # Create Markdown table as a string
    markdown_table = "| Journal | Latest Volume/Issue |\n"
    markdown_table += "|---------|---------------------|\n"
    for journal, latest in results:
        markdown_table += f"| {journal} | {latest} |\n"

    config = load_config()
    jour_page = Path(config["handbook_path"]) / Path(
        "docs/20-research/22-literature.md"
    )
    content = jour_page.read_text(encoding="utf-8")

    # Replace content between START_MARKER and END_MARKER (inclusive of markers, but we keep them)
    block_re = re.compile(
        r"(<!--\s*labot\s+local-cronjob\s*-->)(.*?)(<!--\s*END\s*-->)",
        flags=re.IGNORECASE | re.DOTALL,
    )

    replacement = f"{START_MARKER}\n\n{markdown_table}\n\n{END_MARKER}"

    if block_re.search(content):
        new_content = block_re.sub(replacement, content, count=1)
    else:
        # Markers not found: append a new section with markers at the end
        appendix = (
            "\n\n## Journals and Conferences\n\n"
            "{: .resource }\n"
            "> A selection of journal and conference papers is available "
            "[on Nextcloud](https://nc-2272638881871040784.nextcloud-ionos.com/index.php/apps/files/files/373460?dir=/20-research/22_literature).\n\n"
            "Overview of journals:\n\n"
            f"{replacement}\n"
        )
        new_content = content.rstrip() + appendix

    if new_content != content:
        jour_page.write_text(new_content, encoding="utf-8")

        repo = Repo(config["handbook_path"])
        repo.git.add(str(jour_page))
        # avoid failing when nothing changed elsewhere
        if repo.is_dirty(untracked_files=True):
            repo.git.commit(
                "-m", "Update PDF Collection table (automated)", "--no-verify"
            )
            repo.remote(name="origin").push()
    else:
        print("No changes to apply.")


if __name__ == "__main__":
    main()

import json
import os
import re
from pathlib import Path

from git import Repo

import colrev.loader.load_utils  # as required

CONFIG_PATH = Path.home() / ".labot/config.json"
CURATED_BASE = Path("/home/gerit/.colrev/curated_metadata")

START_MARKER = "<!-- labot local-cronjob -->"
END_MARKER = "<!-- END -->"


def load_config():
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"Settings file not found: {CONFIG_PATH}")
    with open(CONFIG_PATH) as f:
        config = json.load(f)
    return config


# ---------------------------------------------------------------------------
# journal-style helpers (volume/issue)
# ---------------------------------------------------------------------------
def parse_volume_issue(name: str):
    """Parse '43_2' into (43, 2)."""
    match = re.match(r"^(\d+)_(\d+)$", name)
    return (int(match.group(1)), int(match.group(2))) if match else None


def find_latest_issue_in_pdfs(pdf_dir: Path):
    """Return the latest (volume, issue) present in data/pdfs, or None."""
    if not pdf_dir.is_dir():
        return None

    latest = (0, 0)

    for entry in os.listdir(pdf_dir):
        entry_path = pdf_dir / entry
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
            sub_entries = list(entry_path.iterdir())
            sub_issues = [
                int(e.name) for e in sub_entries if e.is_dir() and e.name.isdigit()
            ]
            if sub_issues:
                issue = max(sub_issues)
                latest = max(latest, (volume, issue))
            else:
                # volume-only folder
                latest = max(latest, (volume, 0))

    return latest if latest != (0, 0) else None


# ---------------------------------------------------------------------------
# conference-style helpers (year)
# ---------------------------------------------------------------------------
def find_latest_year_in_pdfs(pdf_dir: Path):
    """Return the latest year present in data/pdfs (e.g., 2024), or None."""
    if not pdf_dir.is_dir():
        return None

    latest_year = 0
    for entry in os.listdir(pdf_dir):
        entry_path = pdf_dir / entry
        if not entry_path.is_dir():
            continue
        if entry.isdigit():
            year = int(entry)
            latest_year = max(latest_year, year)

    return latest_year if latest_year > 0 else None


# ---------------------------------------------------------------------------
# record helpers
# ---------------------------------------------------------------------------
def safe_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return default


def detect_curation_type(records: dict):
    """
    Heuristic:
    - if we find at least one record with volume → journal
    - else if we find at least one record with year → conference
    - else unknown
    """
    has_volume = False
    has_year = False

    for rec in records.values():
        if rec.get("volume"):
            has_volume = True
        if rec.get("year"):
            has_year = True

    if has_volume:
        return "journal"
    elif has_year:
        return "conference"
    else:
        return "unknown"


def find_latest_from_records_journal(records: dict):
    """Iterate over loaded records and find the highest (volume, issue)."""
    latest = (0, 0)

    for rec in records.values():
        vol = rec.get("volume")
        if not vol:
            continue

        issue = rec.get("number") or rec.get("issue")
        vol_i = safe_int(vol, 0)
        iss_i = safe_int(issue, 0)

        latest = max(latest, (vol_i, iss_i))

    return latest if latest != (0, 0) else None


def find_latest_from_records_conference(records: dict):
    """Find the latest year in the records (for conference-style curations)."""
    latest_year = 0
    for rec in records.values():
        year = rec.get("year")
        if year:
            year_i = safe_int(year, 0)
            latest_year = max(latest_year, year_i)
    return latest_year if latest_year > 0 else None


def format_latest_journal(latest):
    return (
        f"{latest[0]}_{latest[1]}"
        if latest and latest[1] > 0
        else (str(latest[0]) if latest else "—")
    )


def format_latest_conference(year):
    return str(year) if year else "—"


# ---------------------------------------------------------------------------
# status comparison
# ---------------------------------------------------------------------------
def compare_record_vs_pdfs_journal(record_vi, pdf_vi):
    if record_vi is None:
        return "no vol/iss in records"
    if pdf_vi is None:
        return "missing PDFs for latest"
    if pdf_vi >= record_vi:
        return "✅ Up-to-date"
    else:
        return "📝 TODO"


def compare_record_vs_pdfs_conference(record_year, pdf_year):
    if record_year is None:
        return "no year in records"
    if pdf_year is None:
        return "missing PDFs for latest year"
    if pdf_year >= record_year:
        return "✅ Up-to-date"
    else:
        return "📝 TODO"


def main():
    config = load_config()

    results = []


    print('Updating 22-literature')
    # iterate over /home/gerit/.colrev/curated_metadata/<curation>
    for curation_dir in sorted(CURATED_BASE.iterdir()):
        if not curation_dir.is_dir():
            continue
        print(f"- checking {curation_dir}")

        records_file = curation_dir / "data" / "records.bib"
        pdf_dir = curation_dir / "data" / "pdfs"

        if not records_file.exists():
            # skip non-standard curations
            continue

        # load records via colrev
        records = colrev.loader.load_utils.load(filename=records_file)

        curation_type = detect_curation_type(records)

        if curation_type == "journal":
            latest_rec = find_latest_from_records_journal(records)
            latest_pdf = find_latest_issue_in_pdfs(pdf_dir)
            status = compare_record_vs_pdfs_journal(latest_rec, latest_pdf)

            latest_rec_str = format_latest_journal(latest_rec)
            latest_pdf_str = format_latest_journal(latest_pdf)

        elif curation_type == "conference":
            latest_rec = find_latest_from_records_conference(records)
            latest_pdf = find_latest_year_in_pdfs(pdf_dir)
            status = compare_record_vs_pdfs_conference(latest_rec, latest_pdf)

            latest_rec_str = format_latest_conference(latest_rec)
            latest_pdf_str = format_latest_conference(latest_pdf)

        else:
            # unknown structure
            latest_rec_str = "—"
            latest_pdf_str = "—"
            status = "unknown structure"

        results.append(
            {
                "curation": curation_dir.name,
                "type": curation_type,
                "latest_records": latest_rec_str,
                "latest_pdfs": latest_pdf_str,
                "status": status,
            }
        )

    # build markdown table (now with type column)
    markdown_table = (
        "| Curation | Type | Latest in records.bib | Latest in data/pdfs | Status |\n"
    )
    markdown_table += "|----------|------|------------------------|---------------------|--------|\n"
    for row in results:
        markdown_table += (
            f"| {row['curation']} | {row['type']} | {row['latest_records']} | "
            f"{row['latest_pdfs']} | {row['status']} |\n"
        )

    # write into handbook page like before
    jour_page = Path(config["handbook_path"]) / Path(
        "docs/20-research/22-literature.md"
    )
    content = jour_page.read_text(encoding="utf-8")

    block_re = re.compile(
        r"(<!--\s*labot\s+local-cronjob\s*-->)(.*?)(<!--\s*END\s*-->)",
        flags=re.IGNORECASE | re.DOTALL,
    )

    replacement = f"{START_MARKER}\n\n{markdown_table}\n\n{END_MARKER}"

    if block_re.search(content):
        new_content = block_re.sub(replacement, content, count=1)
    else:
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
        if repo.is_dirty(untracked_files=True):
            repo.git.commit(
                "-m", "Update PDF Collection table (automated)", "--no-verify"
            )
            repo.remote(name="origin").push()
    else:
        print("No changes to apply.")


if __name__ == "__main__":
    main()

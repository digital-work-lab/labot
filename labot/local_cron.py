import json
import os
import re
from pathlib import Path
from datetime import datetime, timezone, date

from git import Repo

import colrev.loader.load_utils  # as required

CONFIG_PATH = Path.home() / ".labot/config.json"
CURATED_BASE = Path("/home/gerit/.colrev/curated_metadata")

START_MARKER = "<!-- labot local-cronjob -->"
END_MARKER = "<!-- END -->"

NEXTCLOUD_BASE = (
    "https://nc-2272638881871040784.nextcloud-ionos.com/"
    "index.php/apps/files/files"
)


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
# last-modified helpers
# ---------------------------------------------------------------------------
def get_last_modified_date(path: Path) -> date | None:
    """Return the last-modified date of a file as a date object."""
    if not path.exists():
        return None
    mtime = path.stat().st_mtime
    return datetime.fromtimestamp(mtime, tz=timezone.utc).date()


def get_latest_pdf_modified_date(pdf_dir: Path) -> date | None:
    """Return the latest last-modified date across all PDFs in pdf_dir."""
    if not pdf_dir.is_dir():
        return None

    latest_mtime = None
    for root, _, files in os.walk(pdf_dir):
        for fname in files:
            if not fname.lower().endswith(".pdf"):
                continue
            fpath = Path(root) / fname
            mtime = fpath.stat().st_mtime
            if latest_mtime is None or mtime > latest_mtime:
                latest_mtime = mtime

    if latest_mtime is None:
        return None
    return datetime.fromtimestamp(latest_mtime, tz=timezone.utc).date()


def format_journal_date(d: date | None, today: date | None = None) -> str:
    """Journal rules:
    - <= 3 months (≈90 days): green (normal)
    - <= 1 year (≈365 days): orange (bold)
    - older: red (bold)
    """
    if d is None:
        return "—"

    if today is None:
        today = date.today()

    delta_days = (today - d).days
    if delta_days <= 90:
        return f'<span style="color:green">{d.isoformat()}</span>'
    elif delta_days <= 365:
        return f'<strong><span style="color:orange">{d.isoformat()}</span></strong>'
    else:
        return f'<strong><span style="color:red">{d.isoformat()}</span></strong>'


def format_conference_date(d: date | None, today: date | None = None) -> str:
    """Conference rules:
    - <= 1 year (≈365 days): green (normal)
    - > 1 year and <= 2 years (≈730 days): orange (bold)
    - > 2 years: red (bold)
    """
    if d is None:
        return "—"

    if today is None:
        today = date.today()

    delta_days = (today - d).days
    if delta_days <= 365:
        return f'<span style="color:green">{d.isoformat()}</span>'
    elif delta_days <= 730:
        return f'<strong><span style="color:orange">{d.isoformat()}</span></strong>'
    else:
        return f'<strong><span style="color:red">{d.isoformat()}</span></strong>'


# ---------------------------------------------------------------------------
# git URL helpers
# ---------------------------------------------------------------------------
def _convert_remote_to_http(remote_url: str) -> str:
    """Convert common Git remote formats to https://... form."""
    if remote_url.startswith("git@github.com:"):
        repo_part = remote_url[len("git@github.com:") :]
        if repo_part.endswith(".git"):
            repo_part = repo_part[:-4]
        return f"https://github.com/{repo_part}"
    if remote_url.startswith("https://github.com/"):
        repo_part = remote_url[len("https://github.com/") :]
        if repo_part.endswith(".git"):
            repo_part = repo_part[:-4]
        return f"https://github.com/{repo_part}"
    # fallback: just strip .git
    if remote_url.endswith(".git"):
        remote_url = remote_url[:-4]
    return remote_url


def get_git_file_url(path: Path) -> str | None:
    """Return a web URL to the given file based on its Git remote."""
    try:
        repo = Repo(path, search_parent_directories=True)
    except Exception:
        return None

    if not repo.remotes:
        return None

    try:
        remote = repo.remotes.origin
    except AttributeError:
        remote = repo.remotes[0]

    remote_url = remote.url
    http_base = _convert_remote_to_http(remote_url)

    try:
        rel_path = path.relative_to(Path(repo.working_tree_dir))
    except ValueError:
        rel_path = path.name

    try:
        branch = repo.active_branch.name
    except Exception:
        branch = "main"

    return f"{http_base}/blob/{branch}/{rel_path.as_posix()}"


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
# main
# ---------------------------------------------------------------------------
def main():
    config = load_config()

    results = []

    print("Updating literature")
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

            latest_rec_str = format_latest_journal(latest_rec)
            latest_pdf_str = format_latest_journal(latest_pdf)

            rec_last_mod = get_last_modified_date(records_file)
            pdf_last_mod = get_latest_pdf_modified_date(pdf_dir)
            rec_last_mod_str = format_journal_date(rec_last_mod)
            pdf_last_mod_str = format_journal_date(pdf_last_mod)

        elif curation_type == "conference":
            latest_rec = find_latest_from_records_conference(records)
            latest_pdf = find_latest_year_in_pdfs(pdf_dir)

            latest_rec_str = format_latest_conference(latest_rec)
            latest_pdf_str = format_latest_conference(latest_pdf)

            rec_last_mod = get_last_modified_date(records_file)
            pdf_last_mod = get_latest_pdf_modified_date(pdf_dir)
            rec_last_mod_str = format_conference_date(rec_last_mod)
            pdf_last_mod_str = format_conference_date(pdf_last_mod)

        else:
            # unknown structure
            latest_rec_str = "—"
            latest_pdf_str = "—"
            rec_last_mod_str = "—"
            pdf_last_mod_str = "—"

        records_url = get_git_file_url(records_file)
        pdfs_url = NEXTCLOUD_BASE  # same base link for all

        results.append(
            {
                "curation": curation_dir.name,
                "type": curation_type,
                "latest_records_value": latest_rec_str,
                "latest_records_date": rec_last_mod_str,
                "latest_pdfs_value": latest_pdf_str,
                "latest_pdfs_date": pdf_last_mod_str,
                "records_url": records_url,
                "pdfs_url": pdfs_url,
            }
        )

    # build HTML table (split value / last-updated vertically; last cols right-aligned)
    html_table = """
<table class="table table-sm">
  <colgroup>
    <col style="width: 50%;">
    <col style="width: 8%;">
    <col style="width: 21%;">
    <col style="width: 21%;">
  </colgroup>
  <thead>
    <tr>
      <th>Journal / Conference</th>
      <th>Type</th>
      <th style="text-align:right;">Latest in records.bib<br>(last updated)</th>
      <th style="text-align:right;">Latest in data/pdfs<br>(last updated)</th>
    </tr>
  </thead>
  <tbody>
"""
    for row in results:
        # records cell: separate value vs last-updated
        rec_val = row["latest_records_value"]
        rec_date = row["latest_records_date"]

        if rec_val == "—" and rec_date == "—":
            records_cell = "—"
        else:
            if row.get("records_url") and rec_val != "—":
                rec_val_html = f'<a href="{row["records_url"]}">{rec_val}</a>'
            else:
                rec_val_html = rec_val
            records_cell = (
                f'<div>{rec_val_html}</div>'
                f'<div style="font-size:0.85em;">{rec_date}</div>'
            )

        # pdfs cell: separate value vs last-updated
        pdf_val = row["latest_pdfs_value"]
        pdf_date = row["latest_pdfs_date"]

        if pdf_val == "—" and pdf_date == "—":
            pdfs_cell = "—"
        else:
            if row.get("pdfs_url") and pdf_val != "—":
                pdf_val_html = f'<a href="{row["pdfs_url"]}">{pdf_val}</a>'
            else:
                pdf_val_html = pdf_val
            pdfs_cell = (
                f'<div>{pdf_val_html}</div>'
                f'<div style="font-size:0.85em;">{pdf_date}</div>'
            )

        html_table += (
            "    <tr>"
            f"<td>{row['curation']}</td>"
            f"<td>{row['type']}</td>"
            f'<td style="text-align:right;">{records_cell}</td>'
            f'<td style="text-align:right;">{pdfs_cell}</td>'
            "</tr>\n"
        )

    html_table += "  </tbody>\n</table>\n"


    report_path = Path(config["handbook_path"]) / Path("assets/reports/pdf_collection_table.qmd")
    report_path.parent.mkdir(parents=True, exist_ok=True)

    generated = (
        "<!-- This file is generated. Do not edit by hand. -->\n\n"
        f"{html_table}\n\n"
        f"<!-- generated: {date.today().isoformat()} -->\n"
    )

    old = report_path.read_text(encoding="utf-8") if report_path.exists() else ""
    if generated != old:
        report_path.write_text(generated, encoding="utf-8")

        repo = Repo(config["handbook_path"])
        repo.git.add(str(report_path))
        if repo.is_dirty(untracked_files=True):
            repo.git.commit("-m", "Update PDF Collection table (automated)", "--no-verify")
            repo.remote(name="origin").push()
    else:
        print("No changes to apply.")


if __name__ == "__main__":
    main()

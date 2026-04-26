from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Any

import click
import colrev.loader.load_utils
import colrev.writer.write_utils
import pandas as pd
from bib_dedupe.bib_dedupe import block, match, prep

CITEKEY_PATTERN = re.compile(r"\[@([A-Za-z0-9_:-]+)")
MULTI_CITE_PATTERN = re.compile(r";\s*@([A-Za-z0-9_:-]+)")
CITATION_BLOCK_PATTERN = re.compile(r"\[[^\]]*@[^\]]*\]")
CITATION_KEY_PATTERN = re.compile(r"@([A-Za-z0-9_:-]+)")
FIGURE_MD_PATTERN = re.compile(r"!\[\]\(([^)]+)\)")


def load_paper(paper_path: Path) -> str:
    return paper_path.read_text(encoding="utf-8")


def load_bib(bib_path: Path) -> dict[str, dict[str, Any]]:
    return colrev.loader.load_utils.load(filename=bib_path)


def load_obsidian_bib(vault_path: Path) -> dict[str, dict[str, Any]]:
    obsidian_bib_path = vault_path / "references" / "references.bib"
    if not obsidian_bib_path.is_file():
        return {}
    return colrev.loader.load_utils.load(filename=obsidian_bib_path)


def _records_to_df(records: dict[str, dict[str, Any]], source: str) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for key, record in records.items():
        row = dict(record)
        row["source"] = source
        row["source_key"] = key
        row["ID"] = f"{source}::{key}"
        row.setdefault("ENTRYTYPE", "misc")
        row.setdefault("title", "")
        row.setdefault("author", "")
        row.setdefault("year", "")
        row.setdefault("journal", "")
        row.setdefault("booktitle", "")
        row.setdefault("series", "")
        row.setdefault("volume", "")
        row.setdefault("number", "")
        row.setdefault("pages", "")
        row.setdefault("abstract", "")
        row.setdefault("doi", "")
        row.setdefault("search_set", "")
        row.setdefault("container_title", row.get("journal") or row.get("booktitle", ""))
        rows.append(row)
    return pd.DataFrame(rows)


def dedupe_and_sync_citekeys(
    project_records: dict[str, dict[str, Any]],
    obsidian_records: dict[str, dict[str, Any]],
) -> dict[str, str]:
    if not project_records or not obsidian_records:
        return {}

    project_df = _records_to_df(project_records, "project")
    obsidian_df = _records_to_df(obsidian_records, "obsidian")
    dedupe_df = pd.concat([project_df, obsidian_df], ignore_index=True)
    lookup = {
        row["ID"]: (row["source"], row["source_key"])
        for row in dedupe_df.to_dict("records")
    }

    dedupe_df = prep(dedupe_df, cpu=1, verbosity_level=0)
    blocked_df = block(dedupe_df, cpu=1, verbosity_level=0)
    matched_df = match(blocked_df, cpu=1, verbosity_level=0)

    remap: dict[str, str] = {}
    for pair in matched_df.to_dict("records"):
        if pair.get("duplicate_label") != "duplicate":
            continue
        source_1, key_1 = lookup.get(pair.get("ID_1"), (None, None))
        source_2, key_2 = lookup.get(pair.get("ID_2"), (None, None))
        if source_1 == "project" and source_2 == "obsidian":
            remap[key_1] = key_2
        if source_1 == "obsidian" and source_2 == "project":
            remap[key_2] = key_1
    return remap


def _remap_records(
    records: dict[str, dict[str, Any]],
    remap: dict[str, str],
) -> dict[str, dict[str, Any]]:
    remapped: dict[str, dict[str, Any]] = {}
    for key, record in records.items():
        new_key = remap.get(key, key)
        if new_key in remapped:
            continue
        updated = dict(record)
        updated["ID"] = new_key
        remapped[new_key] = updated
    return remapped


def _remap_paper_citekeys(paper_content: str, remap: dict[str, str]) -> str:
    content = paper_content
    for old_key, new_key in remap.items():
        pattern = rf"(?<![A-Za-z0-9_:-])@{re.escape(old_key)}\b"
        content = re.sub(pattern, f"@{new_key}", content)
    return content


def extract_citations(paper_content: str) -> set[str]:
    keys = set(CITEKEY_PATTERN.findall(paper_content))
    keys.update(MULTI_CITE_PATTERN.findall(paper_content))
    return keys


def filter_bib(records: dict[str, dict[str, Any]], cited_keys: set[str]) -> dict[str, dict[str, Any]]:
    return {k: v for k, v in records.items() if k in cited_keys}


def scan_obsidian_notes(vault_path: Path) -> set[str]:
    return {path.stem for path in vault_path.rglob("*.md")}


def transform_citations(paper_content: str, note_names: set[str]) -> tuple[str, int]:
    transformed_links = 0

    def repl(match_obj: re.Match[str]) -> str:
        nonlocal transformed_links
        block_text = match_obj.group(0)
        keys = [k for k in CITATION_KEY_PATTERN.findall(block_text) if k in note_names]
        if not keys:
            return block_text
        backlinks = "".join(f"[[{key}]]" for key in keys)
        transformed_links += len(keys)
        return f"{block_text}{backlinks}"

    return CITATION_BLOCK_PATTERN.sub(repl, paper_content), transformed_links


def _list_figure_files(figures_dir: Path) -> list[Path]:
    if not figures_dir.is_dir():
        return []
    return [path for path in figures_dir.rglob("*") if path.is_file()]


def _normalize_figure_reference(raw_path: str) -> Path | None:
    clean = raw_path.strip().strip('"').strip("'")
    clean = clean.split("?", maxsplit=1)[0].split("#", maxsplit=1)[0]
    path = Path(clean.replace("\\", "/"))
    parts = [part for part in path.parts if part not in {".", ""}]
    if "figures" not in parts:
        return None
    idx = parts.index("figures")
    return Path(*parts[idx + 1 :])


def sync_figures(
    paper_content: str,
    paper_path: Path,
    vault_path: Path,
    project_id: str,
    dry_run: bool,
) -> tuple[str, int, list[str]]:
    source_figures_dir = paper_path.parent / "figures"
    target_root = vault_path / "assets" / project_id
    copied_files = _list_figure_files(source_figures_dir)

    if not dry_run:
        for source_file in copied_files:
            rel = source_file.relative_to(source_figures_dir)
            target_file = target_root / rel
            target_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_file, target_file)

    missing_refs: list[str] = []

    def repl(match_obj: re.Match[str]) -> str:
        raw = match_obj.group(1)
        rel = _normalize_figure_reference(raw)
        if rel is None:
            return match_obj.group(0)
        if not (source_figures_dir / rel).is_file():
            missing_refs.append(str(source_figures_dir / rel))
            return match_obj.group(0)
        return f"![](assets/{project_id}/{rel.as_posix()})"

    updated_content = FIGURE_MD_PATTERN.sub(repl, paper_content)
    return updated_content, len(copied_files), sorted(set(missing_refs))


def _load_output_bib(output_bib_path: Path) -> dict[str, dict[str, Any]]:
    if not output_bib_path.is_file():
        return {}
    return colrev.loader.load_utils.load(filename=output_bib_path)


def _merge_bib_records(
    existing_records: dict[str, dict[str, Any]],
    imported_records: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    merged = dict(existing_records)
    for key, value in imported_records.items():
        if key not in merged:
            merged[key] = value
    return merged


def write_outputs(
    content: str,
    filtered_bib: dict[str, dict[str, Any]],
    vault_path: Path,
    project_id: str,
    dry_run: bool,
) -> tuple[Path, Path, int]:
    output_paper_path = vault_path / "publications" / f"{project_id}.md"
    output_bib_path = vault_path / "references.bib"
    merged_bib = _merge_bib_records(_load_output_bib(output_bib_path), filtered_bib)
    if dry_run:
        return output_paper_path, output_bib_path, len(merged_bib)

    output_paper_path.parent.mkdir(parents=True, exist_ok=True)
    output_bib_path.parent.mkdir(parents=True, exist_ok=True)
    output_paper_path.write_text(content, encoding="utf-8")
    colrev.writer.write_utils.write_file(merged_bib, filename=output_bib_path)
    return output_paper_path, output_bib_path, len(merged_bib)


def run_sync_pipeline(
    paper_path: Path,
    bib_path: Path,
    vault_path: Path,
    project_id: str,
    dry_run: bool = False,
    verbose: bool = False,
) -> None:
    def log(message: str) -> None:
        if verbose:
            click.echo(message)

    paper_content = load_paper(paper_path)
    project_records = load_bib(bib_path)
    obsidian_records = load_obsidian_bib(vault_path)

    remap = dedupe_and_sync_citekeys(project_records, obsidian_records)
    remapped_content = _remap_paper_citekeys(paper_content, remap)
    remapped_records = _remap_records(project_records, remap)

    cited_keys = extract_citations(remapped_content)
    filtered_records = filter_bib(remapped_records, cited_keys)
    missing_citekeys = sorted(cited_keys - set(remapped_records))

    note_names = scan_obsidian_notes(vault_path)
    linked_content, transformed_links = transform_citations(remapped_content, note_names)
    final_content, figures_copied, missing_figures = sync_figures(
        linked_content, paper_path, vault_path, project_id, dry_run
    )
    output_paper_path, output_bib_path, total_output_entries = write_outputs(
        final_content, filtered_records, vault_path, project_id, dry_run
    )

    click.echo(f"Citations found: {len(cited_keys)}")
    click.echo(f"Bib entries kept: {len(filtered_records)}")
    click.echo(f"Bib entries in output file: {total_output_entries}")
    click.echo(f"Citekeys remapped: {len(remap)}")
    click.echo(f"Figures copied: {figures_copied}")
    click.echo(f"Links transformed: {transformed_links}")

    if missing_citekeys:
        click.echo(f"Warning: missing citekeys in bibliography: {', '.join(missing_citekeys)}")
    if missing_figures:
        click.echo(f"Warning: missing figure files: {', '.join(missing_figures)}")
    unmatched = len(project_records) - len(remap)
    if obsidian_records and unmatched > 0:
        click.echo(
            f"Warning: {unmatched} project references had no dedupe match in Obsidian bibliography"
        )

    if dry_run:
        click.echo("Dry-run completed: no files were written.")
        return

    log(f"Paper written to: {output_paper_path}")
    log(f"Bibliography written to: {output_bib_path}")

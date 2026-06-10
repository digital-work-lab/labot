"""Extract references from GROBID TEI and consolidate them with Crossref metadata.

Workflow
--------
1. Reuse an existing TEI file when available, otherwise start/reuse GROBID and process a PDF to TEI, or load an existing TEI file.
   By default, reference consolidation in GROBID is disabled so the source
   records reflect the PDF rather than GROBID-injected Crossref metadata. The
   raw PDF reference strings are extracted from TEI and used for Crossref lookup.
2. Extract references with CoLRev's TEIParser.
3. Set stable CoLRev IDs.
4. Lookup each reference with the CoLRev ``colrev.crossref`` package endpoint
   where possible. The adapter first tries local Python entry points, then the
   documented CLI search pattern ``colrev search --add colrev.crossref -p
   "query=..."``. If neither is available, it falls back to Crossref REST.
5. Print a colorized report that starts each item with a formatted-reference diff.
6. Ask interactively for confirmation when similarity is below the auto-accept
   threshold.
7. Export records with colrev.writer.write_utils.write_file().

Install sketch
--------------
    pip install colrev requests rich docker inquirer lxml
    # Optional, if available in your environment:
    pip install colrev-crossref

Examples
--------
    python consolidate_grobid_references.py paper.pdf --mailto you@example.org
    python consolidate_grobid_references.py paper.tei.xml -o references.ris
    python consolidate_grobid_references.py paper.pdf --non-interactive --output refs.bib

Notes
-----
The public CoLRev documentation describes ``colrev.crossref`` primarily as a
CoLRev package endpoint for search/prep workflows rather than as a stable Python
function. This script therefore uses a small adapter: local package API if
available, the documented CoLRev CLI search form when available, and finally a
Crossref REST fallback. The rest of the pipeline remains CoLRev-based: TEI
extraction, ID setting, and writer-based export.
"""

from __future__ import annotations

__version__ = "0.7.3-diagnostics-opt-in"

import csv
import hashlib
import importlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable, Literal

import requests

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.prompt import Prompt
    from rich.table import Table
    from rich.text import Text
except ImportError:  # pragma: no cover - rich is optional at runtime
    Console = None  # type: ignore[assignment]
    Panel = None  # type: ignore[assignment]
    Prompt = None  # type: ignore[assignment]
    Table = None  # type: ignore[assignment]
    Text = None  # type: ignore[assignment]

try:
    from docker.errors import APIError
except ImportError:  # pragma: no cover
    APIError = RuntimeError  # type: ignore[assignment]

try:
    from colrev.env.grobid_service import GrobidService
    from colrev.env.tei_parser import TEIParser
    import colrev.record.record_id_setter
    from colrev.constants import IDPattern
    import colrev.loader.load_utils
    import colrev.writer.write_utils
    from colrev.record.record import Record as CoLRevRecord
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "This script requires CoLRev. Install it in the active environment, e.g.\n"
        "    pip install colrev\n"
        f"Original import error: {exc}"
    ) from exc

Record = dict[str, Any]
Decision = Literal["accept", "merge_missing", "keep", "quit"]

console = Console() if Console is not None else None


# ---------------------------------------------------------------------------
# Console helpers
# ---------------------------------------------------------------------------


def cprint(message: str, style: str | None = None) -> None:
    if console is not None:
        console.print(message, style=style)
    else:
        print(message)


def prompt_choice(prompt: str, choices: list[str], default: str) -> str:
    if Prompt is not None:
        return str(Prompt.ask(prompt, choices=choices, default=default))
    raw = input(f"{prompt} ({'/'.join(choices)}) [{default}]: ").strip()
    return raw if raw in choices else default


def color_old(value: Any) -> str:
    return f"[red]{value or '∅'}[/red]" if console is not None else str(value or "∅")


def color_new(value: Any) -> str:
    return f"[green]{value or '∅'}[/green]" if console is not None else str(value or "∅")


def ensure_trailing_period(value: str) -> str:
    value = normalize_text(value)
    if not value:
        return ""
    if value.endswith((".", "!", "?")):
        return value
    return value + "."


def normalize_page_range(value: Any) -> str:
    """Normalize page-range dash variants for review/diff purposes.

    BibTeX traditionally uses double dashes in page ranges (1433--1450),
    whereas Crossref often returns a single hyphen (1433-1450). Treat those as
    equivalent in the formatted-reference diff and report.
    """
    text = normalize_text(value)
    text = text.replace("‐", "-").replace("‑", "-").replace("‒", "-")
    text = text.replace("–", "-").replace("—", "-")
    return re.sub(r"(?<=\d)\s*-+\s*(?=\d)", "-", text)


def normalize_author_for_reference_diff(value: Any) -> str:
    """Normalize author names for the review diff only.

    The formatted-reference diff should focus on substantive metadata changes.
    Crossref/GROBID often differ only in abbreviated initials such as
    ``N. Berente`` vs. ``N Berente`` or ``J. P. Smith`` vs. ``J P Smith``.
    Remove only abbreviation dots in author initials; exported records remain
    unchanged.
    """
    text = normalize_text(value)
    text = re.sub(r"\b([A-Z])\.(?=\s|$)", r"\1", text)
    text = re.sub(r"\b((?:[A-Z]\.){2,})", lambda m: m.group(1).replace(".", ""), text)
    return normalize_text(text)


def format_reference(record: Record) -> str:
    """Create a compact, human-readable reference preview for diffing.

    This is intentionally independent from any citation style engine: it is a
    stable review string that makes Crossref-vs-TEI changes visible before any
    optional field-level details. The actual export remains handled by CoLRev
    writers.
    """
    authors = normalize_author_for_reference_diff(record.get("author", "")) or "Unknown author"
    year = extract_year(record) or normalize_text(record.get("year", "")) or "n.d."
    title = normalize_text(record.get("title", ""))
    container = normalize_text(record.get("journal", "")) or normalize_text(record.get("booktitle", ""))
    volume = normalize_text(record.get("volume", ""))
    number = normalize_text(record.get("number", "")) or normalize_text(record.get("issue", ""))
    pages = normalize_page_range(record.get("pages", "") or record.get("page", ""))
    publisher = normalize_text(record.get("publisher", ""))
    doi = normalize_doi(record.get("doi", ""))
    url = normalize_text(record.get("url", ""))

    parts = [f"{authors} ({year})."]
    if title:
        parts.append(ensure_trailing_period(title))

    container_bits = []
    if container:
        container_bits.append(container)
    if volume and number:
        container_bits.append(f"{volume}({number})")
    elif volume:
        container_bits.append(volume)
    elif number:
        container_bits.append(f"({number})")
    if pages:
        container_bits.append(pages)

    if container_bits:
        parts.append(ensure_trailing_period(", ".join(container_bits)))
    elif publisher:
        parts.append(ensure_trailing_period(publisher))

    if doi:
        parts.append(f"https://doi.org/{doi}")
    elif url:
        parts.append(url)

    return normalize_text(" ".join(parts))


def _append_diff_segment(
    old_text: Any,
    new_text: Any,
    old_segment: str,
    new_segment: str,
    tag: str,
) -> None:
    """Append one SequenceMatcher opcode segment to rich/plain buffers."""
    if Text is not None and isinstance(old_text, Text) and isinstance(new_text, Text):
        if tag == "equal":
            old_text.append(old_segment)
            new_text.append(new_segment)
        elif tag == "delete":
            old_text.append(old_segment, style="bold red")
        elif tag == "insert":
            new_text.append(new_segment, style="bold green")
        elif tag == "replace":
            old_text.append(old_segment, style="bold red")
            new_text.append(new_segment, style="bold green")
        return

    if tag == "equal":
        old_text.append(old_segment)
        new_text.append(new_segment)
    elif tag == "delete":
        old_text.append(f"[-{old_segment}-]")
    elif tag == "insert":
        new_text.append(f"[+{new_segment}+]")
    elif tag == "replace":
        old_text.append(f"[-{old_segment}-]")
        new_text.append(f"[+{new_segment}+]")


def build_formatted_reference_char_diff(original: Record, candidate: Record) -> tuple[Any, Any, bool]:
    """Return old/new reference previews with character-level differences marked."""
    original_ref = format_reference(original)
    candidate_ref = format_reference(candidate)
    has_changes = original_ref != candidate_ref

    if Text is not None:
        old_text: Any = Text("GROBID/TEI: ", style="bold")
        new_text: Any = Text("Crossref : ", style="bold")
    else:
        old_text = ["GROBID/TEI: "]
        new_text = ["Crossref : "]

    matcher = SequenceMatcher(None, original_ref, candidate_ref)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        _append_diff_segment(
            old_text=old_text,
            new_text=new_text,
            old_segment=original_ref[i1:i2],
            new_segment=candidate_ref[j1:j2],
            tag=tag,
        )

    return old_text, new_text, has_changes


def print_formatted_reference_char_diff(original: Record, candidate: Record) -> None:
    old_text, new_text, has_changes = build_formatted_reference_char_diff(original, candidate)
    if not has_changes:
        cprint("Formatted reference unchanged.", "green")
        return

    if console is not None and Text is not None:
        console.print(old_text, soft_wrap=True)
        console.print(new_text, soft_wrap=True)
        return

    print("".join(old_text))
    print("".join(new_text))


def formatted_reference_diff_text(original: Record, candidate: Record) -> str:
    old_text, new_text, has_changes = build_formatted_reference_char_diff(original, candidate)
    if not has_changes:
        return ""

    if Text is not None and isinstance(old_text, Text) and isinstance(new_text, Text):
        return old_text.plain + "\n" + new_text.plain

    return "".join(old_text) + "\n" + "".join(new_text)


# ---------------------------------------------------------------------------
# Normalization and matching
# ---------------------------------------------------------------------------


def normalize_text(value: Any) -> str:
    text = "" if value is None else str(value)
    text = re.sub(r"\s+", " ", text).strip()
    return text




def compact_stderr(stderr: str, max_length: int = 500) -> str:
    text = normalize_text(stderr)
    if len(text) <= max_length:
        return text
    return text[: max_length - 1].rstrip() + "…"

def normalize_for_similarity(value: Any) -> str:
    text = normalize_text(value).lower()
    text = re.sub(r"https?://(dx\.)?doi\.org/", "", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_doi(value: Any) -> str:
    doi = normalize_text(value).lower()
    doi = re.sub(r"^https?://(dx\.)?doi\.org/", "", doi)
    doi = doi.replace("doi:", "").strip().rstrip(".")
    return doi


def similarity(left: Any, right: Any) -> float:
    left_norm = normalize_for_similarity(left)
    right_norm = normalize_for_similarity(right)
    if not left_norm or not right_norm:
        return 0.0
    return SequenceMatcher(None, left_norm, right_norm).ratio()


def first_author(author_field: Any) -> str:
    text = normalize_text(author_field)
    if not text:
        return ""
    return re.split(r"\s+and\s+", text, maxsplit=1)[0]


def extract_year(record: Record) -> str:
    year = normalize_text(record.get("year"))
    match = re.search(r"\d{4}", year)
    return match.group(0) if match else ""


def _make_colrev_record(record: Record) -> Any:
    """Create a CoLRev Record object across minor constructor variations."""
    try:
        return CoLRevRecord(data=dict(record))
    except TypeError:
        return CoLRevRecord(dict(record))


def _fallback_record_similarity(source: Record, candidate: Record) -> float:
    """Fallback only for environments with incompatible CoLRev APIs."""
    score = 0.0

    source_doi = normalize_doi(source.get("doi"))
    candidate_doi = normalize_doi(candidate.get("doi"))
    if source_doi and candidate_doi:
        score += 0.40 if source_doi == candidate_doi else -0.20

    title_score = similarity(source.get("title"), candidate.get("title"))
    score += 0.40 * title_score

    source_year = extract_year(source)
    candidate_year = extract_year(candidate)
    if source_year and candidate_year:
        score += 0.10 if source_year == candidate_year else -0.05

    author_score = similarity(first_author(source.get("author")), first_author(candidate.get("author")))
    score += 0.10 * author_score

    return max(0.0, min(1.0, score))


def record_similarity(source: Record, candidate: Record) -> float:
    """Return CoLRev's record similarity for a source/candidate pair.

    This intentionally delegates to
    ``colrev.record.record.Record.get_record_similarity``. A small compatibility
    wrapper tries common call signatures because local CoLRev installations may
    differ slightly.
    """
    try:
        source_record = _make_colrev_record(source)
        candidate_record = _make_colrev_record(candidate)
        call_attempts = [
            lambda: source_record.get_record_similarity(record=candidate_record),
            lambda: source_record.get_record_similarity(record=dict(candidate)),
            lambda: source_record.get_record_similarity(candidate_record),
            lambda: source_record.get_record_similarity(dict(candidate)),
        ]
        for call in call_attempts:
            try:
                value = call()
            except TypeError:
                continue
            if isinstance(value, tuple):
                value = value[0]
            return max(0.0, min(1.0, float(value)))
    except Exception:
        pass

    return _fallback_record_similarity(source, candidate)


def build_bibliographic_query(record: Record) -> str:
    """Build the Crossref query for a reference.

    When GROBID citation consolidation is disabled, the parsed TEI fields can be
    sparse or abbreviated. If ``includeRawCitations=1`` was used, GROBID stores
    the original PDF reference string in ``note type="raw_reference"``. That
    raw string is usually the best input for Crossref's bibliographic search,
    so we use it first and fall back to structured fields only when it is absent.
    """
    raw_reference = normalize_text(record.get("raw_reference", ""))
    if raw_reference:
        return raw_reference

    parts = [
        record.get("title", ""),
        first_author(record.get("author", "")),
        record.get("journal", "") or record.get("booktitle", ""),
        extract_year(record),
    ]
    return " ".join(normalize_text(part) for part in parts if normalize_text(part))


# ---------------------------------------------------------------------------
# GROBID / TEI extraction
# ---------------------------------------------------------------------------


def ensure_grobid_running(image: str | None = "grobid/grobid:0.9.0") -> Any:
    if image:
        GrobidService.GROBID_IMAGE = image

    grobid_service = GrobidService()
    if grobid_service.check_grobid_availability(wait=False):
        cprint(f"GROBID ready at {grobid_service.GROBID_URL}", "green")
        return grobid_service

    cprint("Starting GROBID...", "yellow")
    try:
        grobid_service.start()
    except APIError as exc:
        if "port is already allocated" in str(exc):
            cprint("Port 8070 is already in use; assuming an existing GROBID service.", "yellow")
        else:
            raise

    if not grobid_service.check_grobid_availability(wait=True):
        raise RuntimeError("GROBID failed to start")

    cprint(f"GROBID ready at {grobid_service.GROBID_URL}", "green")
    return grobid_service


def process_pdf_to_tei(
    pdf_path: Path,
    tei_path: Path,
    grobid_service: Any,
    *,
    consolidate_header: str,
    consolidate_citations: str,
    include_raw_citations: bool,
) -> Path:
    url = grobid_service.GROBID_URL.rstrip("/") + "/api/processFulltextDocument"

    request_data = {
        "consolidateHeader": consolidate_header,
        "consolidateCitations": consolidate_citations,
    }
    if include_raw_citations:
        request_data["includeRawCitations"] = "1"

    cprint(
        "GROBID options: "
        f"consolidateHeader={consolidate_header}, "
        f"consolidateCitations={consolidate_citations}, "
        f"includeRawCitations={int(include_raw_citations)}",
        "dim",
    )

    for attempt in range(1, 4):
        try:
            with pdf_path.open("rb") as file_handle:
                response = requests.post(
                    url,
                    files={"input": file_handle},
                    data=request_data,
                    timeout=600,
                )
            response.raise_for_status()
            tei_path.write_text(response.text, encoding="utf-8")
            return tei_path
        except requests.RequestException as exc:
            cprint(f"GROBID attempt {attempt}/3 failed: {exc}", "yellow")
            time.sleep(2)

    raise RuntimeError("GROBID processing failed after three attempts")


def _tei_local_name(tag: str) -> str:
    """Return the local XML name for a possibly namespaced TEI tag."""
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def extract_raw_references_from_tei(tei_path: Path) -> tuple[dict[str, str], list[str]]:
    """Extract GROBID ``note type="raw_reference"`` strings from TEI.

    CoLRev's ``TEIParser.get_references()`` does not reliably expose the raw
    reference string. We parse the TEI once and attach those strings to the
    corresponding CoLRev records by ``xml:id`` and, as a fallback, by order.
    """
    raw_by_id: dict[str, str] = {}
    raw_sequence: list[str] = []

    try:
        root = ET.parse(tei_path).getroot()
    except ET.ParseError:
        return raw_by_id, raw_sequence

    xml_id_key = "{http://www.w3.org/XML/1998/namespace}id"
    for bibl_struct in root.iter():
        if _tei_local_name(bibl_struct.tag) != "biblStruct":
            continue

        raw_reference = ""
        for child in bibl_struct.iter():
            if _tei_local_name(child.tag) != "note":
                continue
            if child.attrib.get("type") != "raw_reference":
                continue
            raw_reference = normalize_text("".join(child.itertext()))
            break

        if not raw_reference:
            continue

        raw_sequence.append(raw_reference)
        tei_id = bibl_struct.attrib.get(xml_id_key) or bibl_struct.attrib.get("id", "")
        if tei_id:
            raw_by_id[tei_id] = raw_reference

    return raw_by_id, raw_sequence


def load_references_from_tei(tei_path: Path) -> dict[str, Record]:
    parser = TEIParser(tei_path=tei_path)
    bibliography_list = parser.get_references()
    raw_by_tei_id, raw_sequence = extract_raw_references_from_tei(tei_path)

    raw_attached = 0
    for index, record in enumerate(bibliography_list):
        # Preserve the GROBID/TEI ID in case IDs are reset by CoLRev.
        tei_id = normalize_text(record.get("ID", ""))
        record["tei_id"] = tei_id

        raw_reference = raw_by_tei_id.get(tei_id, "")
        if not raw_reference and index < len(raw_sequence):
            raw_reference = raw_sequence[index]
        if raw_reference:
            record["raw_reference"] = raw_reference
            raw_attached += 1

    records = {str(record["ID"]): record for record in bibliography_list if record.get("ID")}
    id_setter = colrev.record.record_id_setter.IDSetter(
        id_pattern=IDPattern.three_authors_year,
    )
    records = id_setter.set_ids(records=records)

    for record in records.values():
        record.pop("tei_id", None)

    if raw_sequence:
        cprint(
            f"Attached raw PDF reference strings to {raw_attached}/{len(bibliography_list)} records.",
            "dim",
        )
    else:
        cprint(
            "No raw PDF reference strings found in TEI. "
            "For PDFs, use --include-raw-citations or regenerate the TEI.",
            "yellow",
        )

    return records


# ---------------------------------------------------------------------------
# Crossref lookup
# ---------------------------------------------------------------------------


@dataclass
class LookupResult:
    candidate: Record | None
    similarity: float
    source: str
    raw: dict[str, Any] | None = None
    note: str = ""
    query: str = ""
    query_kind: str = ""
    top_candidates: list[dict[str, Any]] | None = None
    from_cache: bool = False


class CrossrefLookup:
    """Crossref lookup adapter.

    Prefer the CoLRev ``colrev.crossref`` package endpoint. The adapter first
    tries local Python entry points, then the documented CoLRev CLI search
    route, and only then falls back to Crossref REST when ``mode='auto'``.
    """

    def __init__(
        self,
        mailto: str | None,
        mode: Literal["auto", "colrev", "rest"],
        cache_path: Path | None,
        sleep_seconds: float,
        refresh_cache: bool = False,
    ) -> None:
        self.mailto = mailto
        self.mode = mode
        self.sleep_seconds = sleep_seconds
        self.refresh_cache = refresh_cache
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "colrev-grobid-reference-consolidator/0.4 "
                    f"(mailto:{mailto})" if mailto else "colrev-grobid-reference-consolidator/0.4"
                )
            }
        )
        self.cache_path = cache_path
        self.cache: dict[str, dict[str, Any]] = self._load_cache(cache_path)
        self._colrev_lookup_warned = False

    @staticmethod
    def _load_cache(cache_path: Path | None) -> dict[str, dict[str, Any]]:
        if cache_path is None or not cache_path.is_file():
            return {}
        try:
            return json.loads(cache_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}

    def save_cache(self) -> None:
        if self.cache_path is None:
            return
        self.cache_path.write_text(
            json.dumps(self.cache, indent=2, ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )

    def lookup(self, record: Record) -> LookupResult:
        if self.mode in {"auto", "colrev"}:
            result = self._lookup_with_colrev_crossref(record)
            if result.candidate is not None or self.mode == "colrev":
                return result

        return self._lookup_with_crossref_rest(record)

    def _lookup_with_colrev_crossref(self, record: Record) -> LookupResult:
        """Lookup through the CoLRev ``colrev.crossref`` package endpoint.

        The CoLRev manual documents ``colrev.crossref`` as a package endpoint
        that can be added to search/prep operations, for example::

            colrev search --add colrev.crossref -p "query=microsourcing"

        Because local package APIs differ across CoLRev versions, this method
        tries two CoLRev-native routes before allowing the REST fallback:

        1. local Python callables exposed by an installed crossref package;
        2. the documented CoLRev CLI search endpoint in a temporary project.
        """
        api_result = self._lookup_with_colrev_crossref_python(record)
        if api_result.candidate is not None:
            return api_result

        cli_result = self._lookup_with_colrev_crossref_cli(record)
        if cli_result.candidate is not None:
            return cli_result

        if self.mode == "colrev":
            notes = "; ".join(
                note
                for note in [api_result.note, cli_result.note]
                if note
            )
            return LookupResult(
                candidate=None,
                similarity=0.0,
                source="colrev.crossref",
                note=notes or "No supported colrev.crossref route succeeded.",
            )

        if not self._colrev_lookup_warned:
            cprint(
                "No usable colrev.crossref route succeeded; using Crossref REST fallback.",
                "yellow",
            )
            self._colrev_lookup_warned = True

        return LookupResult(
            candidate=None,
            similarity=0.0,
            source="colrev.crossref",
            note="CoLRev package/API and CLI routes did not return a candidate.",
        )

    def _lookup_with_colrev_crossref_python(self, record: Record) -> LookupResult:
        """Best-effort adapter for local ``colrev.crossref`` Python APIs.

        Adjust this method if your local package exposes a known, stable API.
        The expected normalized return is a CoLRev-style record dict.
        """
        module_names = [
            "colrev_crossref",
            "colrev_crossref.search_source",
            "colrev_crossref.prep",
            "colrev.packages.crossref.src.colrev_crossref",
            "colrev.packages.crossref.src.colrev_crossref.search_source",
            "colrev.packages.crossref.src.colrev_crossref.prep",
            "colrev.ops.built_in.search_sources.crossref",
            "colrev.ops.built_in.prep.crossref",
        ]
        callable_names = [
            "lookup",
            "search",
            "query",
            "get_masterdata",
            "get_masterdata_from_crossref",
            "get_record",
        ]

        for module_name in module_names:
            try:
                module = importlib.import_module(module_name)
            except ImportError:
                continue

            for callable_name in callable_names:
                candidate_callable = getattr(module, callable_name, None)
                if not callable(candidate_callable):
                    continue
                try:
                    raw_result = candidate_callable(record)  # type: ignore[misc]
                except TypeError:
                    try:
                        raw_result = candidate_callable(build_bibliographic_query(record))  # type: ignore[misc]
                    except Exception as exc:
                        return LookupResult(
                            candidate=None,
                            similarity=0.0,
                            source=f"{module_name}.{callable_name}",
                            note=f"Callable failed with query argument: {exc}",
                        )
                except Exception as exc:
                    return LookupResult(
                        candidate=None,
                        similarity=0.0,
                        source=f"{module_name}.{callable_name}",
                        note=f"Callable failed with record argument: {exc}",
                    )

                normalized = self._normalize_colrev_crossref_result(raw_result)
                if normalized is not None:
                    return LookupResult(
                        candidate=normalized,
                        similarity=record_similarity(record, normalized),
                        source=f"{module_name}.{callable_name}",
                        raw=raw_result if isinstance(raw_result, dict) else None,
                    )

        return LookupResult(
            candidate=None,
            similarity=0.0,
            source="colrev.crossref-python",
            note="No directly callable Python API was found.",
        )

    def _lookup_with_colrev_crossref_cli(self, record: Record) -> LookupResult:
        """Use the documented ``colrev search --add colrev.crossref`` route.

        This is intentionally conservative and isolated in a temporary project
        because the script itself is not necessarily running inside a CoLRev
        review project.
        """
        colrev_bin = shutil.which("colrev")
        if colrev_bin is None:
            return LookupResult(
                candidate=None,
                similarity=0.0,
                source="colrev.crossref-cli",
                note="No `colrev` executable found on PATH.",
            )

        query = build_bibliographic_query(record)
        if not query:
            return LookupResult(
                candidate=None,
                similarity=0.0,
                source="colrev.crossref-cli",
                note="Empty bibliographic query.",
            )

        with tempfile.TemporaryDirectory(prefix="colrev-crossref-lookup-") as tmpdir_str:
            tmpdir = Path(tmpdir_str)
            init_result = self._run_colrev_cli([colrev_bin, "init"], cwd=tmpdir)
            if init_result.returncode != 0:
                return LookupResult(
                    candidate=None,
                    similarity=0.0,
                    source="colrev.crossref-cli",
                    note=(
                        "`colrev init` failed in temporary project: "
                        + compact_stderr(init_result.stderr)
                    ),
                )

            search_result = self._run_colrev_cli(
                [
                    colrev_bin,
                    "search",
                    "--add",
                    "colrev.crossref",
                    "-p",
                    f"query={query}",
                ],
                cwd=tmpdir,
            )
            if search_result.returncode != 0:
                return LookupResult(
                    candidate=None,
                    similarity=0.0,
                    source="colrev.crossref-cli",
                    note=(
                        "`colrev search --add colrev.crossref` failed: "
                        + compact_stderr(search_result.stderr)
                    ),
                )

            candidates = self._load_colrev_cli_candidates(tmpdir)
            if not candidates:
                return LookupResult(
                    candidate=None,
                    similarity=0.0,
                    source="colrev.crossref-cli",
                    note="CoLRev CLI completed but no bibliography records were found.",
                )

            best_candidate: Record | None = None
            best_score = 0.0
            for candidate in candidates:
                candidate_score = record_similarity(record, candidate)
                if candidate_score > best_score:
                    best_candidate = candidate
                    best_score = candidate_score

            return LookupResult(
                candidate=best_candidate,
                similarity=best_score,
                source="colrev.crossref-cli",
                note=f"query={query}",
            )

    @staticmethod
    def _run_colrev_cli(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        env = dict(os.environ)
        env.setdefault("COLREV_COLOR", "false")
        return subprocess.run(
            command,
            cwd=cwd,
            input="\n",
            text=True,
            capture_output=True,
            timeout=180,
            env=env,
            check=False,
        )

    @staticmethod
    def _load_colrev_cli_candidates(project_dir: Path) -> list[Record]:
        candidates: list[Record] = []
        for file_path in sorted(project_dir.rglob("*.bib")):
            try:
                loaded = colrev.loader.load_utils.load(filename=file_path)
            except Exception:
                continue
            candidates.extend(dict(record) for record in loaded.values())
        return candidates

    @staticmethod
    def _normalize_colrev_crossref_result(raw_result: Any) -> Record | None:
        if raw_result is None:
            return None
        if isinstance(raw_result, dict):
            # Some APIs return the record directly; others wrap it.
            for key in ("record", "metadata", "item", "candidate"):
                if isinstance(raw_result.get(key), dict):
                    return dict(raw_result[key])
            if "title" in raw_result or "doi" in raw_result or "DOI" in raw_result:
                result = dict(raw_result)
                if "DOI" in result and "doi" not in result:
                    result["doi"] = result.pop("DOI")
                return result
        if isinstance(raw_result, list) and raw_result and isinstance(raw_result[0], dict):
            return dict(raw_result[0])
        return None

    def _lookup_with_crossref_rest(self, record: Record) -> LookupResult:
        cache_key = self._cache_key(record)
        if not self.refresh_cache and cache_key in self.cache:
            return self._lookup_result_from_cache(record, self.cache[cache_key])

        doi = normalize_doi(record.get("doi"))
        if doi:
            result = self._lookup_doi(doi, record)
        else:
            result = self._search_bibliographic(record)

        if result.raw is not None:
            self.cache[cache_key] = result.raw
            self.save_cache()

        time.sleep(self.sleep_seconds)
        return result

    def _lookup_result_from_cache(self, record: Record, cached: dict[str, Any]) -> LookupResult:
        """Recreate a LookupResult from the REST cache.

        Supports the newer envelope cache with all top candidates and the older
        legacy cache that stored only one Crossref work item.
        """
        if cached.get("cache_version") == 2:
            kind = normalize_text(cached.get("kind", "crossref-search"))
            query = normalize_text(cached.get("query", ""))
            items = cached.get("items", []) or []
            if kind == "crossref-doi" and cached.get("item"):
                items = [cached["item"]]
            result = self._result_from_crossref_items(
                source_record=record,
                items=items,
                source="crossref-rest-cache",
                query=query,
                query_kind="doi" if kind == "crossref-doi" else "bibliographic",
                raw=cached,
            )
            result.from_cache = True
            return result

        # Legacy cache from earlier script versions: only one Crossref work item.
        candidate = normalize_crossref_work(cached)
        top_candidates = []
        if candidate is not None:
            top_candidates.append(self._candidate_diagnostic(record, candidate, rank=1))
        return LookupResult(
            candidate=candidate,
            similarity=record_similarity(record, candidate) if candidate else 0.0,
            source="crossref-rest-cache-legacy",
            raw=cached,
            note=(
                "Legacy cache entry contains only the previously selected best "
                "candidate; use --refresh-cache to retrieve top candidates."
            ),
            query=build_bibliographic_query(record),
            query_kind="cache-legacy",
            top_candidates=top_candidates,
            from_cache=True,
        )

    def _lookup_doi(self, doi: str, source_record: Record) -> LookupResult:
        url = f"https://api.crossref.org/works/{doi}"
        params = {"mailto": self.mailto} if self.mailto else {}
        try:
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            item = response.json().get("message", {})
        except requests.RequestException as exc:
            return LookupResult(
                None,
                0.0,
                "crossref-rest",
                note=str(exc),
                query=doi,
                query_kind="doi",
            )

        raw = {"cache_version": 2, "kind": "crossref-doi", "query": doi, "item": item}
        return self._result_from_crossref_items(
            source_record=source_record,
            items=[item],
            source="crossref-rest-doi",
            query=doi,
            query_kind="doi",
            raw=raw,
        )

    def _search_bibliographic(self, record: Record) -> LookupResult:
        query = build_bibliographic_query(record)
        if not query:
            return LookupResult(None, 0.0, "crossref-rest", note="Empty query", query_kind="empty")

        url = "https://api.crossref.org/works"
        params: dict[str, Any] = {
            "query.bibliographic": query,
            "rows": 5,
            "select": ",".join(
                [
                    "DOI",
                    "type",
                    "title",
                    "author",
                    "issued",
                    "published-print",
                    "published-online",
                    "container-title",
                    "volume",
                    "issue",
                    "page",
                    "publisher",
                    "URL",
                    "ISBN",
                    "ISSN",
                ]
            ),
        }
        if self.mailto:
            params["mailto"] = self.mailto

        try:
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            items = response.json().get("message", {}).get("items", [])
        except requests.RequestException as exc:
            return LookupResult(
                None,
                0.0,
                "crossref-rest",
                note=str(exc),
                query=query,
                query_kind="bibliographic",
            )

        raw = {"cache_version": 2, "kind": "crossref-search", "query": query, "items": items}
        return self._result_from_crossref_items(
            source_record=record,
            items=items,
            source="crossref-rest-search",
            query=query,
            query_kind="bibliographic",
            raw=raw,
        )

    def _result_from_crossref_items(
        self,
        *,
        source_record: Record,
        items: list[dict[str, Any]],
        source: str,
        query: str,
        query_kind: str,
        raw: dict[str, Any] | None,
    ) -> LookupResult:
        best_candidate: Record | None = None
        best_score = 0.0
        diagnostics: list[dict[str, Any]] = []

        for rank, item in enumerate(items, start=1):
            candidate = normalize_crossref_work(item)
            if candidate is None:
                continue
            candidate_score = record_similarity(source_record, candidate)
            diagnostics.append(self._candidate_diagnostic(source_record, candidate, rank=rank))
            if candidate_score > best_score:
                best_candidate = candidate
                best_score = candidate_score

        return LookupResult(
            candidate=best_candidate,
            similarity=best_score,
            source=source,
            raw=raw,
            query=query,
            query_kind=query_kind,
            top_candidates=diagnostics,
        )

    @staticmethod
    def _candidate_diagnostic(source_record: Record, candidate: Record, rank: int) -> dict[str, Any]:
        container = normalize_text(candidate.get("journal", "")) or normalize_text(candidate.get("booktitle", ""))
        raw_reference = normalize_text(source_record.get("raw_reference", ""))
        candidate_reference = format_reference(candidate)
        return {
            "rank": rank,
            "similarity": record_similarity(source_record, candidate),
            "raw_reference_similarity": similarity(raw_reference, candidate_reference) if raw_reference else 0.0,
            "title_similarity": similarity(source_record.get("title", ""), candidate.get("title", "")),
            "source_title": normalize_text(source_record.get("title", "")),
            "title": normalize_text(candidate.get("title", "")),
            "year": extract_year(candidate),
            "doi": normalize_doi(candidate.get("doi", "")),
            "container": container,
            "candidate_reference": candidate_reference,
        }

    @staticmethod
    def _cache_key(record: Record) -> str:
        doi = normalize_doi(record.get("doi"))
        query = doi or build_bibliographic_query(record)
        return hashlib.sha256(query.encode("utf-8")).hexdigest()


def crossref_year(item: dict[str, Any]) -> str:
    for field in ("published-print", "published-online", "issued"):
        date_parts = item.get(field, {}).get("date-parts")
        if date_parts and date_parts[0]:
            return str(date_parts[0][0])
    return ""


def crossref_authors(item: dict[str, Any]) -> str:
    authors = []
    for author in item.get("author", []) or []:
        family = normalize_text(author.get("family", ""))
        given = normalize_text(author.get("given", ""))
        if family and given:
            authors.append(f"{family}, {given}")
        elif family:
            authors.append(family)
        elif given:
            authors.append(given)
    return " and ".join(authors)


def first_list_value(value: Any) -> str:
    if isinstance(value, list) and value:
        return normalize_text(value[0])
    return normalize_text(value)


def normalize_crossref_work(item: dict[str, Any]) -> Record | None:
    if not item:
        return None

    crossref_type = item.get("type", "")
    entrytype_map = {
        "journal-article": "article",
        "proceedings-article": "inproceedings",
        "book-chapter": "incollection",
        "book": "book",
        "monograph": "book",
        "posted-content": "misc",
        "report": "techreport",
        "dissertation": "phdthesis",
    }
    entrytype = entrytype_map.get(crossref_type, "misc")

    record: Record = {
        "ENTRYTYPE": entrytype,
        "title": first_list_value(item.get("title", [])),
        "author": crossref_authors(item),
        "year": crossref_year(item),
        "doi": normalize_doi(item.get("DOI", "")),
        "volume": normalize_text(item.get("volume", "")),
        "number": normalize_text(item.get("issue", "")),
        "pages": normalize_text(item.get("page", "")),
        "publisher": normalize_text(item.get("publisher", "")),
        "url": normalize_text(item.get("URL", "")),
    }

    container_title = first_list_value(item.get("container-title", []))
    if container_title:
        if entrytype == "article":
            record["journal"] = container_title
        else:
            record["booktitle"] = container_title

    isbn = first_list_value(item.get("ISBN", []))
    issn = first_list_value(item.get("ISSN", []))
    if isbn:
        record["isbn"] = isbn
    if issn:
        record["issn"] = issn

    return {key: value for key, value in record.items() if value not in (None, "", [])}


# ---------------------------------------------------------------------------
# Reconciliation and reporting
# ---------------------------------------------------------------------------


COMPARE_FIELDS = [
    "ENTRYTYPE",
    "title",
    "author",
    "year",
    "journal",
    "booktitle",
    "volume",
    "number",
    "pages",
    "doi",
    "publisher",
    "url",
    "isbn",
    "issn",
]


def normalize_field_for_change_detection(field: str, value: Any) -> str:
    """Normalize a field for deciding whether a review-visible change exists."""
    if field == "author":
        return normalize_for_similarity(normalize_author_for_reference_diff(value))
    if field in {"pages", "page"}:
        return normalize_for_similarity(normalize_page_range(value))
    return normalize_for_similarity(value)


def diff_fields(original: Record, candidate: Record) -> dict[str, tuple[str, str]]:
    changes = {}
    for field in COMPARE_FIELDS:
        old = normalize_text(original.get(field, ""))
        new = normalize_text(candidate.get(field, ""))
        if not new:
            continue
        if normalize_field_for_change_detection(field, old) != normalize_field_for_change_detection(field, new):
            changes[field] = (old, new)
    return changes


def merged_record(original: Record, candidate: Record, mode: Decision) -> Record:
    merged = dict(original)
    if mode == "keep":
        return merged

    for key, value in candidate.items():
        if value in (None, "", []):
            continue
        if key == "ID":
            continue
        if mode == "merge_missing" and merged.get(key):
            continue
        merged[key] = value

    # Keep the original CoLRev ID stable.
    merged["ID"] = original.get("ID", merged.get("ID", ""))
    return merged



def truncate_for_display(value: Any, max_length: int = 240) -> str:
    text = normalize_text(value)
    if len(text) <= max_length:
        return text
    return text[: max_length - 1].rstrip() + "…"


def parsed_field_snapshot(record: Record) -> dict[str, str]:
    return {
        "author": truncate_for_display(record.get("author", ""), 160),
        "title": truncate_for_display(record.get("title", ""), 180),
        "year": extract_year(record) or normalize_text(record.get("year", "")),
        "container": truncate_for_display(record.get("journal", "") or record.get("booktitle", ""), 120),
        "volume": normalize_text(record.get("volume", "")),
        "number": normalize_text(record.get("number", "") or record.get("issue", "")),
        "pages": normalize_page_range(record.get("pages", "") or record.get("page", "")),
        "doi": normalize_doi(record.get("doi", "")),
        "raw_reference": truncate_for_display(record.get("raw_reference", ""), 260),
    }


def print_matching_diagnostics(
    items: list[ReviewItem],
    *,
    minimum_match_similarity: float,
    limit: int,
) -> None:
    """Print diagnostics for records that were not accepted as matches.

    This is designed to explain whether the failure is caused by missing raw
    citations, weak TEI parsing, Crossref returning no candidates, stale legacy
    cache entries, or CoLRev similarity falling below the threshold.
    """
    if not items or limit == 0:
        return

    if limit < 0:
        selected = items
    else:
        selected = items[:limit]

    cprint("\nMatching diagnostics for non-matched references", "bold cyan")
    cprint(
        "These references had no candidate or the best candidate was below "
        f"--minimum-match-similarity={minimum_match_similarity:.2f}.",
        "dim",
    )

    for index, item in enumerate(selected, start=1):
        result = item.result
        reason = "no Crossref candidate returned"
        if result.candidate is not None:
            reason = (
                f"best CoLRev similarity {result.similarity:.2f} below "
                f"threshold {minimum_match_similarity:.2f}"
            )
        title = normalize_text(item.original.get("title", "")) or truncate_for_display(item.original.get("raw_reference", ""), 80)
        cprint(f"\n[{index}/{len(selected)}] {item.record_id}: {reason}", "bold")
        cprint(f"Lookup source: {result.source}; query_kind={result.query_kind or 'unknown'}; from_cache={result.from_cache}", "dim")
        if result.note:
            cprint(f"Note: {result.note}", "yellow")
        cprint(f"Record title/raw hint: {truncate_for_display(title, 120)}", "dim")

        fields = parsed_field_snapshot(item.original)
        if Table is not None and console is not None:
            table = Table(show_header=True, header_style="bold", title="Source record used for matching")
            table.add_column("Field")
            table.add_column("Value")
            for field, value in fields.items():
                table.add_row(field, value or "∅")
            console.print(table)
        else:
            print("Source record used for matching:")
            for field, value in fields.items():
                print(f"  {field}: {value or '∅'}")

        cprint("Crossref query:", "bold")
        cprint(truncate_for_display(result.query or build_bibliographic_query(item.original), 500))

        top_candidates = result.top_candidates or []
        if not top_candidates:
            cprint("Top Crossref candidates: none returned or unavailable from this lookup route.", "yellow")
            continue

        if Table is not None and console is not None:
            cand_table = Table(show_header=True, header_style="bold", title="Top Crossref candidates")
            cand_table.add_column("#", justify="right")
            cand_table.add_column("CoLRev sim", justify="right")
            cand_table.add_column("Raw-ref sim", justify="right")
            cand_table.add_column("Title sim", justify="right")
            cand_table.add_column("Year")
            cand_table.add_column("DOI")
            cand_table.add_column("Title")
            for candidate in top_candidates:
                cand_table.add_row(
                    str(candidate.get("rank", "")),
                    f"{float(candidate.get('similarity', 0.0)):.2f}",
                    f"{float(candidate.get('raw_reference_similarity', 0.0)):.2f}",
                    f"{float(candidate.get('title_similarity', 0.0)):.2f}",
                    normalize_text(candidate.get("year", "")) or "∅",
                    normalize_text(candidate.get("doi", "")) or "∅",
                    truncate_for_display(candidate.get("title", ""), 130) or "∅",
                )
            console.print(cand_table)
        else:
            print("Top Crossref candidates:")
            for candidate in top_candidates:
                print(
                    f"  {candidate.get('rank')}. "
                    f"sim={float(candidate.get('similarity', 0.0)):.2f}, "
                    f"raw-ref-sim={float(candidate.get('raw_reference_similarity', 0.0)):.2f}, "
                    f"title-sim={float(candidate.get('title_similarity', 0.0)):.2f}, "
                    f"year={candidate.get('year') or '∅'}, doi={candidate.get('doi') or '∅'}\n"
                    f"     {truncate_for_display(candidate.get('title', ''), 130)}"
                )

    remaining = len(items) - len(selected)
    if remaining > 0:
        cprint(
            f"\nDiagnostics suppressed for {remaining} additional non-matched references. "
            "Use --diagnostics to print these details; use --diagnostics-limit -1 to print all.",
            "dim",
        )

def print_candidate_report(record_id: str, original: Record, result: LookupResult) -> None:
    candidate = result.candidate
    if candidate is None:
        cprint(f"\n[bold]{record_id}[/bold]: no candidate ({result.note or result.source})", "yellow")
        return

    # Start each item with a compact, character-level formatted-reference diff.
    # The heavier panel/table metadata view is intentionally hidden behind the
    # interactive "d" decision to keep review flow fast.
    cprint("\nFormatted reference diff", "bold")
    print_formatted_reference_char_diff(original, candidate)
    cprint(
        f"Candidate: {result.source}, similarity={result.similarity:.2f} — "
        f"{normalize_text(candidate.get('title', '')) or 'untitled'}",
        "dim",
    )


def print_candidate_details(record_id: str, original: Record, result: LookupResult) -> None:
    candidate = result.candidate
    if candidate is None:
        cprint(f"{record_id}: no candidate ({result.note or result.source})", "yellow")
        return

    header = (
        f"{record_id}: {result.source}, similarity={result.similarity:.2f}\n"
        f"{normalize_text(original.get('title', ''))}"
    )
    if Panel is not None and console is not None:
        console.print(Panel(header, title="Reference match", expand=False))
    else:
        print("\n" + header)

    changes = diff_fields(original, candidate)
    if not changes:
        cprint("No metadata changes detected.", "green")
        return

    if Table is None or console is None:
        for field, (old, new) in changes.items():
            print(f"  {field}: {old or '∅'} -> {new or '∅'}")
        return

    table = Table(show_header=True, header_style="bold")
    table.add_column("Field")
    table.add_column("GROBID/TEI")
    table.add_column("Crossref")
    for field, (old, new) in changes.items():
        table.add_row(field, color_old(old), color_new(new))
    console.print(table)


def decide(
    record_id: str,
    original: Record,
    result: LookupResult,
    auto_accept_threshold: float,
    non_interactive: bool,
) -> Decision:
    if result.candidate is None:
        return "keep"

    if result.similarity >= auto_accept_threshold:
        cprint(
            f"Auto-accepting {record_id} at similarity {result.similarity:.2f}",
            "green",
        )
        return "accept"

    if non_interactive:
        cprint(
            f"Keeping {record_id}: similarity {result.similarity:.2f} below auto threshold.",
            "yellow",
        )
        return "keep"

    while True:
        cprint(
            "Low/medium similarity match. Choose: "
            "[bold]a[/bold]=accept Crossref, [bold]m[/bold]=merge missing only, "
            "[bold]k[/bold]=keep original, [bold]d[/bold]=details, [bold]q[/bold]=quit",
            "yellow",
        )
        choice = prompt_choice("Decision", choices=["a", "m", "k", "d", "q"], default="k")
        if choice == "d":
            print_candidate_details(record_id, original, result)
            continue
        return {"a": "accept", "m": "merge_missing", "k": "keep", "q": "quit"}[choice]  # type: ignore[return-value]


def write_report_csv(rows: Iterable[dict[str, Any]], report_path: Path) -> None:
    rows = list(rows)
    if not rows:
        return
    fieldnames = [
        "ID",
        "decision",
        "similarity",
        "source",
        "changed_fields",
        "original_title",
        "candidate_title",
        "raw_reference",
        "lookup_query",
        "lookup_query_kind",
        "top_candidate_count",
        "best_raw_reference_similarity",
        "original_doi",
        "candidate_doi",
        "formatted_reference_diff",
        "note",
    ]
    with report_path.open("w", newline="", encoding="utf-8") as file_handle:
        writer = csv.DictWriter(file_handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


@dataclass
class ReviewItem:
    record_id: str
    original: Record
    result: LookupResult
    changes: dict[str, tuple[str, str]]
    has_formatted_reference_changes: bool

    @property
    def has_changes(self) -> bool:
        return bool(self.changes) or self.has_formatted_reference_changes


def has_formatted_reference_changes(original: Record, candidate: Record) -> bool:
    """Return whether the normalized review reference changed."""
    return format_reference(original) != format_reference(candidate)


def print_non_matched_references(non_matches: list[ReviewItem]) -> None:
    if not non_matches:
        return

    cprint("\nNon-matched references", "bold yellow")
    for item in non_matches:
        cprint(f"- {format_reference(item.original)}", "yellow")



def first_n_records(records: dict[str, Record], limit: int) -> dict[str, Record]:
    """Return the first ``limit`` records for lookup/review.

    ``limit`` is intentionally applied immediately before the Crossref lookup
    loop as a defensive guard. This prevents diagnostics runs from querying all
    references when an earlier caller forgets to pre-slice the record dict.
    Use ``--limit 0`` or a negative value to process all references.
    """
    if limit <= 0 or limit >= len(records):
        return records
    return dict(list(records.items())[:limit])

def lookup_all_records(
    records: dict[str, Record],
    lookup: CrossrefLookup,
    minimum_match_similarity: float,
    lookup_limit: int,
) -> tuple[list[ReviewItem], list[ReviewItem]]:
    """Run Crossref lookups before starting the review phase.

    The lookup limit is applied here, not only in ``main()``, so a diagnostics
    run cannot accidentally query every reference before slicing results.
    """
    original_count = len(records)
    records = first_n_records(records, lookup_limit)
    matched_items: list[ReviewItem] = []
    non_matches: list[ReviewItem] = []

    if lookup_limit > 0 and len(records) < original_count:
        cprint(
            f"Lookup limit active: querying first {len(records)}/{original_count} references "
            f"(--limit {lookup_limit}; use --limit 0 for all).",
            "yellow",
        )
    cprint(f"Querying Crossref for {len(records)} references before review...", "bold")
    for index, (record_id, original) in enumerate(records.items(), start=1):
        original.setdefault("ID", record_id)
        query_hint = "raw" if normalize_text(original.get("raw_reference", "")) else "structured"
        cprint(f"[{index}/{len(records)}] Querying {record_id} ({query_hint} query)", "dim")
        result = lookup.lookup(original)
        candidate = result.candidate
        if candidate is None or result.similarity < minimum_match_similarity:
            non_matches.append(
                ReviewItem(
                    record_id=record_id,
                    original=original,
                    result=result,
                    changes={},
                    has_formatted_reference_changes=False,
                )
            )
            continue

        changes = diff_fields(original, candidate)
        matched_items.append(
            ReviewItem(
                record_id=record_id,
                original=original,
                result=result,
                changes=changes,
                has_formatted_reference_changes=has_formatted_reference_changes(original, candidate),
            )
        )

    return matched_items, non_matches


def print_lookup_statistics(
    *,
    exact_matches: int,
    matched_with_changes: int,
    non_matches: int,
    display_all: bool,
) -> None:
    """Print review statistics after all Crossref queries and before review."""
    cprint("\nReference matching statistics", "bold")
    cprint(f"Exact matches (formatted reference unchanged): {exact_matches}", "green")
    cprint(f"Matches with potential changes: {matched_with_changes}", "yellow")
    cprint(f"No matches: {non_matches}", "red" if non_matches else "green")
    if exact_matches and not display_all:
        cprint("Exact matches are skipped by default; use --all to display them.", "dim")


def consolidate_records(
    records: dict[str, Record],
    lookup: CrossrefLookup,
    auto_accept_threshold: float,
    non_interactive: bool,
    report_path: Path,
    display_all: bool,
    minimum_match_similarity: float,
    diagnostics: bool,
    diagnostics_limit: int,
    reference_limit: int,
) -> dict[str, Record]:
    consolidated: dict[str, Record] = {record_id: dict(record) for record_id, record in records.items()}
    report_rows: list[dict[str, Any]] = []

    matched_items, non_matches = lookup_all_records(
        records=records,
        lookup=lookup,
        minimum_match_similarity=minimum_match_similarity,
        lookup_limit=reference_limit,
    )

    # Exact-match statistics and the default review queue are based on the
    # formatted reference, not on field-level metadata differences. Crossref may
    # add metadata such as publisher, URL, or ISSN while the human-readable
    # reference remains unchanged. Those records should be counted as exact
    # formatted-reference matches and skipped unless --all is set.
    skipped_unchanged = [
        item for item in matched_items
        if not item.has_formatted_reference_changes
    ]
    changed_matched = [
        item for item in matched_items
        if item.has_formatted_reference_changes
    ]
    review_items = [
        item for item in matched_items
        if item.has_formatted_reference_changes or display_all
    ]
    review_items.sort(key=lambda item: item.result.similarity, reverse=True)

    print_lookup_statistics(
        exact_matches=len(skipped_unchanged),
        matched_with_changes=len(changed_matched),
        non_matches=len(non_matches),
        display_all=display_all,
    )

    if skipped_unchanged and not display_all:
        cprint(
            f"Skipping {len(skipped_unchanged)} matched references without changes "
            "(--all displays them).",
            "green",
        )

    if review_items:
        cprint(
            f"\nReviewing {len(review_items)} matched references in decreasing "
            "CoLRev record similarity...",
            "bold",
        )
    else:
        cprint("\nNo changed matched references to review.", "green")

    for index, item in enumerate(review_items, start=1):
        record_id = item.record_id
        original = item.original
        result = item.result
        candidate = result.candidate or {}

        cprint(
            f"\n[{index}/{len(review_items)}] {record_id} "
            f"(similarity={result.similarity:.2f})",
            "bold",
        )
        print_candidate_report(record_id, original, result)

        if not item.has_changes:
            cprint("No changes detected; keeping original record.", "green")
            decision: Decision = "keep"
        else:
            decision = decide(
                record_id=record_id,
                original=original,
                result=result,
                auto_accept_threshold=auto_accept_threshold,
                non_interactive=non_interactive,
            )
        if decision == "quit":
            cprint("Aborted by user. Writing records processed so far plus untouched originals.", "red")
            break

        consolidated[record_id] = merged_record(original, candidate, decision)
        report_rows.append(
            {
                "ID": record_id,
                "decision": decision,
                "similarity": f"{result.similarity:.3f}",
                "source": result.source,
                "changed_fields": ";".join(item.changes.keys()),
                "original_title": normalize_text(original.get("title", "")),
                "candidate_title": normalize_text(candidate.get("title", "")),
                "raw_reference": normalize_text(original.get("raw_reference", "")),
                "lookup_query": normalize_text(result.query),
                "lookup_query_kind": normalize_text(result.query_kind),
                "top_candidate_count": len(result.top_candidates or []),
                "best_raw_reference_similarity": (
                    f"{float((result.top_candidates or [{}])[0].get('raw_reference_similarity', 0.0)):.3f}"
                    if result.top_candidates else ""
                ),
                "original_doi": normalize_doi(original.get("doi", "")),
                "candidate_doi": normalize_doi(candidate.get("doi", "")),
                "formatted_reference_diff": formatted_reference_diff_text(original, candidate) if candidate else "",
                "note": result.note,
            }
        )

    for item in skipped_unchanged:
        candidate = item.result.candidate or {}
        report_rows.append(
            {
                "ID": item.record_id,
                "decision": "skip_unchanged",
                "similarity": f"{item.result.similarity:.3f}",
                "source": item.result.source,
                "changed_fields": "",
                "original_title": normalize_text(item.original.get("title", "")),
                "candidate_title": normalize_text(candidate.get("title", "")),
                "raw_reference": normalize_text(item.original.get("raw_reference", "")),
                "lookup_query": normalize_text(item.result.query),
                "lookup_query_kind": normalize_text(item.result.query_kind),
                "top_candidate_count": len(item.result.top_candidates or []),
                "best_raw_reference_similarity": (
                    f"{float((item.result.top_candidates or [{}])[0].get('raw_reference_similarity', 0.0)):.3f}"
                    if item.result.top_candidates else ""
                ),
                "original_doi": normalize_doi(item.original.get("doi", "")),
                "candidate_doi": normalize_doi(candidate.get("doi", "")),
                "formatted_reference_diff": "",
                "note": item.result.note,
            }
        )

    for item in non_matches:
        report_rows.append(
            {
                "ID": item.record_id,
                "decision": "non_matched",
                "similarity": f"{item.result.similarity:.3f}",
                "source": item.result.source,
                "changed_fields": "",
                "original_title": normalize_text(item.original.get("title", "")),
                "candidate_title": normalize_text((item.result.candidate or {}).get("title", "")),
                "raw_reference": normalize_text(item.original.get("raw_reference", "")),
                "lookup_query": normalize_text(item.result.query),
                "lookup_query_kind": normalize_text(item.result.query_kind),
                "top_candidate_count": len(item.result.top_candidates or []),
                "best_raw_reference_similarity": (
                    f"{float((item.result.top_candidates or [{}])[0].get('raw_reference_similarity', 0.0)):.3f}"
                    if item.result.top_candidates else ""
                ),
                "original_doi": normalize_doi(item.original.get("doi", "")),
                "candidate_doi": normalize_doi((item.result.candidate or {}).get("doi", "")),
                "formatted_reference_diff": "",
                "note": item.result.note,
            }
        )

    if diagnostics:
        diagnostic_items = sorted(
            non_matches,
            key=lambda item: item.result.similarity,
            reverse=True,
        )
        print_matching_diagnostics(
            diagnostic_items,
            minimum_match_similarity=minimum_match_similarity,
            limit=diagnostics_limit,
        )

    print_non_matched_references(non_matches)
    write_report_csv(report_rows, report_path)
    cprint(f"Report written to {report_path}", "green")
    return consolidated


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


def export_records(records: dict[str, Record], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    colrev.writer.write_utils.write_file(records, filename=output_path)
    cprint(f"Export written to {output_path}", "green")

# ---------------------------------------------------------------------------
# Public module entry point
# ---------------------------------------------------------------------------


def resolve_paths(
    input_path: Path,
    output_path: Path | None,
    report_path: Path | None,
) -> tuple[Path, Path, Path]:
    """Resolve TEI, export, and report paths from the user-provided input."""
    if input_path.suffix.lower() == ".pdf":
        tei_path = input_path.with_suffix(".tei.xml")
    else:
        tei_path = input_path

    if output_path is None:
        output_path = input_path.with_suffix(".consolidated.bib")

    if report_path is None:
        report_path = input_path.with_suffix(".crossref_report.csv")

    return tei_path, output_path, report_path


def run(
    *,
    input_path: Path,
    output_path: Path | None = None,
    report_path: Path | None = None,
    mailto: str | None = None,
    crossref_mode: Literal["auto", "colrev", "rest"] = "auto",
    auto_accept_threshold: float = 0.92,
    non_interactive: bool = False,
    display_all: bool = False,
    diagnostics: bool = False,
    diagnostics_limit: int = 15,
    minimum_match_similarity: float = 0.50,
    reference_limit: int = 0,
    cache_path: Path | None = Path(".crossref_lookup_cache.json"),
    refresh_cache: bool = False,
    sleep_seconds: float = 0.10,
    grobid_image: str = "grobid/grobid:0.9.0",
    grobid_consolidate_header: Literal["0", "1", "2", "3"] = "1",
    grobid_consolidate_citations: Literal["0", "1", "2"] = "0",
    include_raw_citations: bool = True,
    force_grobid: bool = False,
) -> int:
    """Extract references from PDF/TEI and consolidate them with Crossref metadata.

    This is the programmatic entry point used by the labot Click command, e.g.::

        labot references consolidate paper.pdf -o references.bib

    The heavy implementation stays in this module; the CLI layer should only
    parse options and pass them into this function.
    """
    if not input_path.is_file():
        cprint(f"Input file not found: {input_path}", "red")
        return 2

    tei_path, resolved_output_path, resolved_report_path = resolve_paths(
        input_path=input_path,
        output_path=output_path,
        report_path=report_path,
    )

    if input_path.suffix.lower() == ".pdf":
        if tei_path.is_file() and not force_grobid:
            cprint(
                f"Reusing existing TEI: {tei_path} "
                "(force_grobid=True regenerates it from the PDF).",
                "green",
            )
        else:
            grobid_service = ensure_grobid_running(image=grobid_image)
            process_pdf_to_tei(
                input_path,
                tei_path,
                grobid_service,
                consolidate_header=grobid_consolidate_header,
                consolidate_citations=grobid_consolidate_citations,
                include_raw_citations=include_raw_citations,
            )
            cprint(f"TEI written to {tei_path}", "green")
    elif not tei_path.is_file():
        cprint(f"TEI file not found: {tei_path}", "red")
        return 2

    records = load_references_from_tei(tei_path)
    cprint(f"Extracted {len(records)} references from {tei_path}", "green")

    if cache_path is None:
        cprint("Crossref REST cache disabled.", "dim")
    else:
        cprint(f"Crossref REST cache active: {cache_path}", "dim")
        if refresh_cache:
            cprint("Existing cache entries will be ignored and refreshed.", "dim")

    lookup = CrossrefLookup(
        mailto=mailto,
        mode=crossref_mode,
        cache_path=cache_path,
        sleep_seconds=sleep_seconds,
        refresh_cache=refresh_cache,
    )

    consolidated = consolidate_records(
        records=records,
        lookup=lookup,
        auto_accept_threshold=auto_accept_threshold,
        non_interactive=non_interactive,
        report_path=resolved_report_path,
        display_all=display_all,
        minimum_match_similarity=minimum_match_similarity,
        diagnostics=diagnostics,
        diagnostics_limit=diagnostics_limit,
        reference_limit=reference_limit,
    )

    export_records(consolidated, resolved_output_path)
    return 0

import os
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Iterator

import inquirer
from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches
from docx.shared import Pt


# Function to list only markdown files in the current directory, excluding paper.md and CONTRIBUTING.md
def get_files_in_current_directory():
    excluded_files = {"paper.md", "CONTRIBUTING.md"}
    return [
        f
        for f in os.listdir(".")
        if os.path.isfile(f) and f.endswith(".md") and f not in excluded_files
    ]


def _extract_status_from_comment(line: str) -> str | None:
    """
    Extracts a status value from a single-line HTML comment like:
    <!-- status:open -->, <!-- status:done -->, etc.
    Returns the status (lowercased) or None if not found.
    """
    if line.startswith("<!--") and line.endswith("-->"):
        m = re.search(r"status\s*:\s*([a-zA-Z_-]+)", line, flags=re.IGNORECASE)
        if m:
            return m.group(1).strip().lower()
    return None


def parse_comments(lines):
    """
    Parses a markdown file into a list of tuples:
    (id, comment_text, response_text, status)

    Rules:
    - A section starts with a line beginning "# " (the ID).
    - 'Response' starts with the first line beginning with "> ".
    - A single-line HTML comment <!-- status:XYZ --> *before* the response
      sets the status for the section. The last one seen before the response wins.
    - Multiline HTML comments (<!-- ... --> across multiple lines) are ignored.
    """
    comments = []
    current_id = None
    current_comment = []
    current_response = []
    current_status = None  # capture from <!-- status:... --> before response
    mode = "id"  # Tracks if we are in ID, comment, or response mode
    in_multiline_comment = False

    for raw_line in lines:
        line = raw_line.rstrip("\n")

        # Detect start/end of multiline HTML comments
        if (
            not in_multiline_comment
            and line.strip().startswith("<!--")
            and not line.strip().endswith("-->")
        ):
            in_multiline_comment = True

        if in_multiline_comment:
            if line.strip().endswith("-->"):
                in_multiline_comment = False
            # ignore content inside multiline comments
            continue

        stripped = line.strip()

        # Single-line HTML comment (could include status)
        if stripped.startswith("<!--") and stripped.endswith("-->"):
            # If we haven't entered response mode yet, allow status capture
            if mode != "response":
                status = _extract_status_from_comment(stripped)
                if status:
                    current_status = status
            # skip the comment line itself
            continue

        # Start of a new comment section
        if stripped.startswith("# "):
            # Save the previous comment if present
            if current_id is not None:
                comment_str = "\n".join(current_comment).strip()
                current_response_str = "\n".join(current_response).strip()
                comments.append(
                    (
                        current_id,
                        comment_str,
                        current_response_str,
                        current_status or "open",
                    )
                )
            # Reset for the new section
            current_id = stripped[2:].strip()
            current_comment = []
            current_response = []
            current_status = None
            mode = "comment"
            continue

        # Start of the response section (first line beginning with "> ")
        if stripped.startswith("> "):
            mode = "response"
            # remove the "> " prefix but keep the rest (including trailing spaces)
            current_response.append(stripped[2:])
            continue

        # Accumulate content
        if mode == "comment":
            current_comment.append(stripped)
        elif mode == "response":
            # keep the original line (without stripping right side)
            current_response.append(line)

    # Append the last collected comment and response after the loop
    if current_id is not None:
        comments.append(
            (
                current_id,
                "\n".join(current_comment).strip(),
                "\n".join(current_response).strip(),
                current_status or "open",
            )
        )

    return comments


class MarkdownBlockKind(Enum):
    PARAGRAPH = "paragraph"
    ORDERED_LIST_ITEM = "ordered-list-item"
    UNORDERED_LIST_ITEM = "unordered-list-item"


@dataclass(frozen=True)
class MarkdownBlock:
    kind: MarkdownBlockKind
    text: str
    list_number: int | None = None


_LIST_ITEM_PATTERN = re.compile(
    r"^\s*(?:(?P<number>\d+)(?:[.)])|(?P<bullet>[-*+]))\s+(?P<text>.*)$"
)


# ---------- markdown block + hard-break handling ----------


def _lines_to_markdown_paragraph(lines: list[str]) -> str:
    """
    Convert a list of lines (no empty lines) into a single paragraph string.

    - Normal lines are joined with spaces.
    - Lines ending with >=2 spaces become a hard line break (encoded as '\n').
    """
    buf: list[str] = []
    first_in_run = True

    for line in lines:
        # Detect hard break: at least two trailing spaces
        if re.search(r"\s{2,}$", line):
            core = re.sub(r"\s+$", "", line)
            if core:
                if not first_in_run:
                    buf.append(" ")
                buf.append(core)
            # hard break inside same paragraph
            buf.append("\n")
            first_in_run = True  # next non-empty chunk starts a new "run"
        else:
            core = line.strip()
            if core:
                if not first_in_run:
                    buf.append(" ")
                buf.append(core)
                first_in_run = False

    # Remove trailing hard breaks/spaces
    text = "".join(buf)
    return text.strip("\n ")


def split_markdown_into_paragraphs(block: str) -> list[str]:
    """
    Split a block of markdown text into paragraphs.

    - Empty lines (or lines that become empty after stripping the '> ' prefix)
      start a new paragraph.
    - Inside a paragraph, lines are joined with spaces (except for hard breaks).
    """
    paragraphs: list[str] = []
    current_lines: list[str] = []

    for raw_line in block.splitlines():
        line = raw_line

        # In responses, we may still see '>' lines if parsing changes later;
        # strip an optional leading '> ' defensively.
        if line.lstrip().startswith("> "):
            line = line.lstrip()[2:]

        if line.strip() == "":
            # paragraph break
            if current_lines:
                paragraphs.append(_lines_to_markdown_paragraph(current_lines))
                current_lines = []
            continue

        current_lines.append(line)

    if current_lines:
        paragraphs.append(_lines_to_markdown_paragraph(current_lines))

    return paragraphs


def _response_prefix_removed(line: str) -> str:
    """Remove a response quote prefix while retaining significant trailing spaces."""
    if line.lstrip().startswith("> "):
        return line.lstrip()[2:]
    return line


def _markdown_blocks(text: str) -> Iterator[MarkdownBlock]:
    """Yield prose and list items, joining source-wrapped lines within each block."""
    current_lines: list[str] = []
    current_kind = MarkdownBlockKind.PARAGRAPH
    current_number: int | None = None

    def flush() -> MarkdownBlock | None:
        nonlocal current_lines
        if not current_lines:
            return None
        result = MarkdownBlock(
            current_kind,
            _lines_to_markdown_paragraph(current_lines),
            current_number,
        )
        current_lines = []
        return result

    for raw_line in text.splitlines():
        line = _response_prefix_removed(raw_line)
        if not line.strip():
            pending = flush()
            if pending:
                yield pending
            current_kind = MarkdownBlockKind.PARAGRAPH
            current_number = None
            continue

        match = _LIST_ITEM_PATTERN.match(line)
        if match:
            pending = flush()
            if pending:
                yield pending
            current_kind = (
                MarkdownBlockKind.ORDERED_LIST_ITEM
                if match.group("number")
                else MarkdownBlockKind.UNORDERED_LIST_ITEM
            )
            current_number = (
                int(match.group("number")) if match.group("number") else None
            )
            current_lines = [match.group("text")]
        else:
            current_lines.append(line)

    pending = flush()
    if pending:
        yield pending


# ---------- UPDATED: markdown-to-docx writer ----------


def _add_markdown_runs(paragraph, text: str) -> None:
    """
    Internal helper: add runs for bold/italic inside a single 'logical line'
    (i.e., no '\n' here).
    """
    pos = 0
    # Patterns for bold (**text** or __text__) and italic (*text* or _text_)
    # Note: We treat ***...*** as bold+italic
    pattern = r"(\*\*\*|___|__|\*\*|\*|_)(.+?)\1"

    for match in re.finditer(pattern, text):
        if match.start() > pos:
            paragraph.add_run(text[pos : match.start()])

        style = match.group(1)
        matched_text = match.group(2)

        run = paragraph.add_run(matched_text)
        if style in ("***", "___"):
            run.bold = True
            run.italic = True
        elif style in ("**", "__"):
            run.bold = True
        elif style in ("*", "_"):
            run.italic = True

        pos = match.end()

    if pos < len(text):
        paragraph.add_run(text[pos:])


def add_markdown_text(paragraph, text: str) -> None:
    """
    Adds text with Markdown-style bold and italic formatting to a Word paragraph.

    Interprets '\n' as a hard line break inside the same paragraph (Markdown's
    "two spaces then newline" rule, already converted to '\n' earlier).
    """
    # Split by our internal hard-break marker
    parts = text.split("\n")

    for i, part in enumerate(parts):
        if part:
            _add_markdown_runs(paragraph, part)
        if i < len(parts) - 1:
            # hard line break inside the same paragraph
            paragraph.add_run().add_break()


def set_cell_background(cell, fill_hex: str):
    """
    Set background color of a table cell.
    fill_hex should be a hex RGB string WITHOUT '#', e.g., 'C6E0B4'.
    """
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    shd = tcPr.find(qn("w:shd"))
    if shd is None:
        shd = OxmlElement("w:shd")
        tcPr.append(shd)
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill_hex)


def status_to_color_hex(status: str) -> str:
    """
    Map a status string to a light background color.
    - done/ok/closed -> green
    - later -> grey
    - anything else (incl. open) -> orange
    """
    s = (status or "").lower().strip()
    if s in {"done", "ok", "closed"}:
        return "C6E0B4"  # light green
    if s == "later":
        return "D9D9D9"  # light grey
    return "F8CBAD"  # light orange


def _set_list_number(paragraph, number: int) -> None:
    """Give an ordered-list paragraph its own numbering instance and start value."""
    paragraph.style = "List Number"
    style_num_id = paragraph.style.element.pPr.numPr.numId.val
    numbering = paragraph.part.numbering_part.element
    style_num = next(num for num in numbering.num_lst if num.numId == style_num_id)
    abstract_id = style_num.abstractNumId.val
    num_id = max((int(num.numId) for num in numbering.num_lst), default=0) + 1

    num = OxmlElement("w:num")
    num.set(qn("w:numId"), str(num_id))
    abstract_num_id = OxmlElement("w:abstractNumId")
    abstract_num_id.set(qn("w:val"), str(abstract_id))
    num.append(abstract_num_id)
    level_override = OxmlElement("w:lvlOverride")
    level_override.set(qn("w:ilvl"), "0")
    start_override = OxmlElement("w:startOverride")
    start_override.set(qn("w:val"), str(number))
    level_override.append(start_override)
    num.append(level_override)
    numbering.append(num)

    num_properties = paragraph._p.get_or_add_pPr().get_or_add_numPr()
    num_properties.get_or_add_ilvl().val = 0
    num_properties.get_or_add_numId().val = num_id


def _format_markdown_block(paragraph, block: MarkdownBlock) -> None:
    paragraph.paragraph_format.space_after = Pt(6)
    if block.kind is MarkdownBlockKind.ORDERED_LIST_ITEM:
        # A fresh numbering instance guarantees the Markdown number is displayed
        # and prevents Word from continuing a list from another table cell.
        _set_list_number(paragraph, block.list_number or 1)
    elif block.kind is MarkdownBlockKind.UNORDERED_LIST_ITEM:
        paragraph.style = "List Bullet"
    add_markdown_text(paragraph, block.text)


def _fill_cell_with_markdown(cell, text: str) -> None:
    """
    Fill a table cell with markdown-like paragraphs.
    """
    blocks = list(_markdown_blocks(text))
    if not blocks:
        return

    # reuse the first paragraph in the cell
    first_para = cell.paragraphs[0]
    first_para.text = ""
    _format_markdown_block(first_para, blocks[0])

    for block in blocks[1:]:
        p = cell.add_paragraph()
        _format_markdown_block(p, block)


def create_word_table(comments, output_filename="revision_table.docx"):
    # Create a new Word document
    doc = Document()
    doc.add_heading("Revision Table", level=1)

    # Add table with three columns
    table = doc.add_table(rows=1, cols=3)
    table.style = "Table Grid"
    table.autofit = False

    # Set column widths
    table.columns[0].width = Inches(1.0)
    table.columns[1].width = Inches(4.0)
    table.columns[2].width = Inches(4.0)

    # Add header row
    hdr_cells = table.rows[0].cells
    hdr_cells[0].text = "ID"
    hdr_cells[1].text = "Comment"
    hdr_cells[2].text = "Response"

    # Populate table rows with formatted Markdown content
    for comment_number, comment_text, response_text, status in comments:
        row_cells = table.add_row().cells
        row_cells[0].text = comment_number

        # Comment cell (same paragraph logic if you want it there as well)
        _fill_cell_with_markdown(row_cells[1], comment_text)

        # Response cell (with background color by status)
        _fill_cell_with_markdown(row_cells[2], response_text)
        set_cell_background(row_cells[2], status_to_color_hex(status))

    # Set page orientation to landscape (swap width/height)
    section = doc.sections[0]
    new_width, new_height = section.page_height, section.page_width
    section.page_width = new_width
    section.page_height = new_height

    # Save the document
    doc.save(output_filename)
    print(f"Revision table saved to {output_filename}")


def main() -> None:
    # Prompt user to select a file
    files = get_files_in_current_directory()
    questions = [
        inquirer.List("file", message="Select the file to process", choices=files),
    ]
    selected_file = inquirer.prompt(questions)["file"]

    # Load the content of the selected file
    with open(selected_file, encoding="utf-8") as file:
        lines = file.readlines()

    # Parse comments and create Word table
    comments = parse_comments(lines)
    create_word_table(
        comments, output_filename=Path(selected_file).with_suffix(".docx")
    )


if __name__ == "__main__":
    main()

import os
import re
from pathlib import Path
import inquirer
from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches


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
            current_response.append(stripped[2:].strip())
            continue

        # Accumulate content
        if mode == "comment":
            current_comment.append(stripped)
        elif mode == "response":
            current_response.append(stripped)

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


def add_markdown_text(paragraph, text):
    """Adds text with Markdown-style bold and italic formatting to a Word paragraph."""
    # Patterns for bold (**text** or __text__) and italic (*text* or _text_)
    # Note: We treat ***...*** as bold+italic
    pos = 0
    for match in re.finditer(r"(\*\*\*|___|__|\*\*|\*|_)(.+?)\1", text):
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

        # Comment cell
        comment_paragraph = row_cells[1].paragraphs[0]
        add_markdown_text(comment_paragraph, comment_text)

        # Response cell (with background color by status)
        response_paragraph = row_cells[2].paragraphs[0]
        add_markdown_text(response_paragraph, response_text)
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
    create_word_table(comments, output_filename=Path(selected_file).with_suffix(".docx"))


if __name__ == "__main__":
    main()

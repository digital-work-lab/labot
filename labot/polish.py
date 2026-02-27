#!/usr/bin/env python3
import os
import sys
import glob
import time
from pathlib import Path

import questionary
from openai import OpenAI
import openai


def get_openai_client():
    api_key = os.getenv("OPENAI_KEY")
    if not api_key:
        print("ERROR: Please export OPENAI_KEY before running this script.")
        print("       Example: export OPENAI_KEY='sk-...'\n")
        sys.exit(1)
    return OpenAI(api_key=api_key)


SYSTEM_PROMPT = """You are a careful copy editor.

Tasks:
1. Spell-check and fix typos.
2. Improve grammar and clarity while preserving meaning.
3. Ensure terminology is used consistently.
4. Ensure all headings are in sentence case (only the first word
   and proper nouns capitalized).

Important formatting rules:
- Preserve the original file format (Markdown / plain text).
- Do not remove line breaks.
- Do NOT wrap the output in explanations or comments.
- Output ONLY the revised document content.
"""

def choose_files(patterns):
    # Collect matching files
    files = []
    for pattern in patterns:
        files.extend(glob.glob(pattern))

    # Deduplicate and sort
    files = sorted(set(files))

    if not files:
        print("No files found for patterns:", ", ".join(patterns))
        sys.exit(1)

    choices = questionary.checkbox(
        "Select the files you want to revise:",
        choices=files,
    ).ask()

    if not choices:
        print("No files selected. Exiting.")
        sys.exit(0)

    return [Path(f) for f in choices]


def revise_text(client, text: str, max_retries: int = 5) -> str:
    for attempt in range(max_retries):
        try:
            resp = client.chat.completions.create(
                model="gpt-4o-mini",  # gpt-5.1
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": (
                            "Revise the following document as specified. "
                            "Return ONLY the revised document content.\n\n"
                            "----- BEGIN DOCUMENT -----\n"
                            f"{text}\n"
                            "----- END DOCUMENT -----"
                        ),
                    },
                ],
                temperature=0.1,
            )
            return resp.choices[0].message.content

        except openai.RateLimitError as e:
            wait_for = 2 ** attempt
            print(f"  ⚠️ Rate limit hit, retrying in {wait_for}s... ({e})")
            time.sleep(wait_for)

        except openai.APIError as e:
            status_code = getattr(e, "status_code", None)
            if status_code is not None and 500 <= status_code < 600 and attempt < max_retries - 1:
                wait_for = 2 ** attempt
                print(f"  ⚠️ Server error {status_code}, retrying in {wait_for}s...")
                time.sleep(wait_for)
            else:
                raise

    raise RuntimeError("Failed to revise text after multiple retries.")


def process_file(client, path: Path):
    print(f"Processing: {path}")

    encoding_tried = ["utf-8", "utf-8-sig"]
    original_text = None

    for enc in encoding_tried:
        try:
            original_text = path.read_text(encoding=enc)
            break
        except UnicodeDecodeError:
            continue

    if original_text is None:
        print(f"  Skipping {path}: unable to read with utf-8 encodings.")
        return

    revised = revise_text(client, original_text)

    # Safety: ensure we don't write None or empty string by mistake
    if revised is None:
        print(f"  Skipping {path}: model returned no content.")
        return

    # Strip trailing spaces but DO NOT add any wrapper text
    revised = revised.rstrip() + "\n"

    path.write_text(revised, encoding="utf-8")
    print(f"  ✅ Overwritten: {path}")


def main():
    # Default patterns (adapt if needed)
    patterns = ["*.md", "*.qmd", "*.markdown", "*.txt"]

    client = get_openai_client()
    files = choose_files(patterns)

    for idx, path in enumerate(files, start=1):
        process_file(client, path)

        # Proactive throttling: sleep a bit after each request
        if idx < len(files):
            time.sleep(1)


if __name__ == "__main__":
    main()

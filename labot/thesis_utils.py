#! /usr/bin/env python3
"""Utils for theses."""

import re
from docx import Document

def _extract_text_from_word(file_path: str) -> str:
    try:
        document = Document(file_path)
        text = []

        for paragraph in document.paragraphs:
            text.append(paragraph.text)

        return "\n".join(text)

    except Exception as e:
        return f"An error occurred: {e}"

def _clean_name(raw_name: str) -> str:
    parts = raw_name.split(",")
    if len(parts) == 2:
        last_name = parts[0].replace(" ", "").strip()
        first_name = parts[1].strip()
        return f"{last_name}, {first_name}"
    return raw_name.strip()

def _extract_information(text: str) -> dict:

    name_pattern = r"Name:\s*([^\n]+)"
    student_id_pattern = r"Matrikelnummer:\s*(\d+)"
    topic_pattern = r"Englisch \(zur Aufnahme ins Zeugnis\):\n([^\n]+)"
    date_pattern_1 = r"Bamberg, den\s*(\d{2}\.\d{2}\.\d{4})"
    date_pattern_2 = r"Bamberg, den\s*([\d-]+)"
    work_time_pattern = r"(\d+)\s*Monate"
    zulassung_date_pattern = r"Die Zulassung erfolgte am:\s*(\d{2}\.\d{2}\.\d{4})"

    name_match = re.search(name_pattern, text)
    student_id_match = re.search(student_id_pattern, text)
    date_match = re.search(date_pattern_1, text)
    if date_match:
        # convert to YYYY-MM-DD
        date = date_match.group(1)
        date = re.sub(r"(\d{2})\.(\d{2})\.(\d{4})", r"\3-\2-\1", date)
    else:
        date_match = re.search(date_pattern_2, text)
    topic_match = re.search(topic_pattern, text)
    work_time_match = re.search(work_time_pattern, text)
    zulassung_date_match = re.search(zulassung_date_pattern, text)

    raw_name = name_match.group(1).strip() if name_match else None
    name = _clean_name(raw_name) if raw_name else None
    student_id = student_id_match.group(1) if student_id_match else None
    topic = topic_match.group(1).strip() if topic_match else None
    date = date_match.group(1) if date_match else None
    date = re.sub(r"(\d{2})\.(\d{2})\.(\d{4})", r"\3-\2-\1", date) if date else None
    work_time = work_time_match.group(1) if work_time_match else "NA"
    zulassung_date = zulassung_date_match.group(1) if zulassung_date_match else "NA"

    level = "bachelor" if "bachelorarbeit" in text.lower() else "master"

    return {
        "student": name,
        "student_id": student_id,
        "Topic": topic,
        "Date": date,
        "Work Time": work_time + " months",
        "Zulassung Date": zulassung_date,
        "Level": level,
    }

def append_infos_from_word(registration: dict) -> dict:

    extracted_text = _extract_text_from_word(registration["word_file"])
    info = _extract_information(extracted_text)
    registration.update(info)
    return registration
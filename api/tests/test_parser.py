import io

import pytest
from openpyxl import Workbook

from app.pipeline.parser import COLUMNS, FileFormatError, parse_upload

HEADER = ",".join(COLUMNS)
ROW = "123456789012,Asha Verma,2007-04-18,female,CSE,E1"


def parse(text: str, filename: str = "f.csv", max_rows: int = 100):
    return parse_upload(filename, text.encode(), max_rows)


def test_row_numbers_match_the_spreadsheet_and_blank_rows_are_skipped():
    rows = parse(f"{HEADER}\n{ROW}\n,,,,,\n{ROW}\n")
    assert [r.row_number for r in rows] == [2, 4]
    assert rows[0].values["full_name"] == "Asha Verma"


def test_headers_are_matched_loosely():
    text = (
        "﻿APAAR ID, Student Name ,DOB,Gender,Programme Code,Enrollment No,Remarks\n" + ROW + ",x\n"
    )
    (row,) = parse(text)
    assert row.values == dict(zip(COLUMNS, ROW.split(","), strict=True))


def test_short_rows_are_padded_instead_of_crashing():
    (row,) = parse(f"{HEADER}\n123456789012,Asha\n")
    assert row.values["enrolment_no"] == ""


@pytest.mark.parametrize(
    ("text", "filename", "message"),
    [
        ("", "f.csv", "empty"),
        (HEADER + "\n", "f.csv", "no student rows"),
        ("apaar_id,full_name\n1,2\n", "f.csv", "Missing column"),
        (f"{HEADER},apaar_id\n{ROW},1\n", "f.csv", "more than once"),
        (f"{HEADER}\n{ROW}\n", "f.pdf", "Unsupported"),
        (f"{HEADER}\n{ROW}\n{ROW}\n{ROW}\n", "f.csv", "more than 2 rows"),
    ],
)
def test_file_level_problems_are_reported(text, filename, message):
    with pytest.raises(FileFormatError, match=message):
        parse(text, filename, max_rows=2)


def test_non_utf8_csv_is_rejected_with_advice():
    with pytest.raises(FileFormatError, match="UTF-8"):
        parse_upload("f.csv", "apaar_id,full_name\n1,Zo\xeb\n".encode("latin-1"), 10)


def test_xlsx_numbers_and_dates_become_clean_strings():
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(list(COLUMNS))
    # Excel hands back a typed-in APAAR ID as a float and a date cell as a datetime
    from datetime import datetime

    sheet.append([123456789012.0, "Asha Verma", datetime(2007, 4, 18), "female", "CSE", 42])
    buffer = io.BytesIO()
    workbook.save(buffer)

    (row,) = parse_upload("f.xlsx", buffer.getvalue(), 10)

    assert row.row_number == 2
    assert row.values["apaar_id"] == "123456789012"
    assert row.values["date_of_birth"] == "2007-04-18"
    assert row.values["enrolment_no"] == "42"


def test_corrupt_xlsx_is_rejected():
    with pytest.raises(FileFormatError, match="could not be opened"):
        parse_upload("f.xlsx", b"this is not a zip file", 10)

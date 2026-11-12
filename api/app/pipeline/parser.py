"""Turn an uploaded CSV or Excel file into rows of plain strings.

Only file-level problems are raised here (unreadable file, missing columns).
Everything about an individual row is left to the validation stages so it ends
up in the row-level error report instead of failing the whole upload.
"""

import csv
import io
import re
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import PurePath

from openpyxl import load_workbook

COLUMNS = ("apaar_id", "full_name", "date_of_birth", "gender", "programme_code", "enrolment_no")
ALLOWED_EXTENSIONS = (".csv", ".xlsx")

# headers institutes commonly use instead of the template's
_ALIASES = {
    "apaar": "apaar_id",
    "apaar_no": "apaar_id",
    "apaar_number": "apaar_id",
    "name": "full_name",
    "student_name": "full_name",
    "dob": "date_of_birth",
    "sex": "gender",
    "programme": "programme_code",
    "program_code": "programme_code",
    "enrollment_no": "enrolment_no",
    "enrolment_number": "enrolment_no",
    "enrollment_number": "enrolment_no",
}


class FileFormatError(Exception):
    """The file as a whole cannot be processed. The message is shown to the uploader."""


@dataclass
class ParsedRow:
    row_number: int  # as seen in the spreadsheet: the header is row 1
    values: dict[str, str]


def parse_upload(filename: str, content: bytes, max_rows: int) -> list[ParsedRow]:
    extension = PurePath(filename).suffix.lower()
    if extension == ".csv":
        records = _read_csv(content)
    elif extension == ".xlsx":
        records = _read_xlsx(content)
    else:
        raise FileFormatError("Unsupported file type. Upload a .csv or .xlsx file.")
    return _to_rows(records, max_rows)


def _read_csv(content: bytes) -> Iterator[list[str]]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise FileFormatError(
            "The CSV file is not UTF-8 encoded. In Excel, save it as 'CSV UTF-8'."
        ) from None
    # NUL bytes cannot be stored in Postgres text/JSONB and never belong in a CSV
    text = text.replace("\x00", "")
    try:
        for record in csv.reader(io.StringIO(text, newline="")):
            yield [cell.strip() for cell in record]
    except csv.Error as exc:
        raise FileFormatError(f"The CSV file could not be read: {exc}") from None


def _read_xlsx(content: bytes) -> Iterator[list[str]]:
    try:
        workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except Exception:  # openpyxl raises several unrelated types for a corrupt file
        raise FileFormatError("The Excel file could not be opened. Is it a valid .xlsx?") from None
    try:
        sheet = workbook.worksheets[0]
        for record in sheet.iter_rows(values_only=True):
            yield [_cell_to_str(cell) for cell in record]
    finally:
        workbook.close()


def _cell_to_str(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    # Excel stores a typed-in APAAR ID as a number, which arrives as 123456789012.0
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _normalise_header(header: str) -> str:
    name = re.sub(r"[^a-z0-9]+", "_", header.strip().lower()).strip("_")
    return _ALIASES.get(name, name)


def _to_rows(records: Iterator[list[str]], max_rows: int) -> list[ParsedRow]:
    numbered = enumerate(records, start=1)
    header: list[str] | None = None
    for _, record in numbered:
        if any(record):
            header = [_normalise_header(cell) for cell in record]
            break
    if header is None:
        raise FileFormatError("The file is empty.")

    missing = [column for column in COLUMNS if column not in header]
    if missing:
        raise FileFormatError(
            f"Missing column(s): {', '.join(missing)}. "
            f"The header row must contain: {', '.join(COLUMNS)}."
        )
    repeated = sorted({column for column in COLUMNS if header.count(column) > 1})
    if repeated:
        raise FileFormatError(f"Column(s) appear more than once: {', '.join(repeated)}.")
    index = {column: header.index(column) for column in COLUMNS}

    rows: list[ParsedRow] = []
    for row_number, record in numbered:
        if not any(record):
            continue
        if len(rows) >= max_rows:
            raise FileFormatError(f"The file has more than {max_rows:,} rows. Split it and retry.")
        values = {
            column: record[position] if position < len(record) else ""
            for column, position in index.items()
        }
        rows.append(ParsedRow(row_number, values))
    if not rows:
        raise FileFormatError("The file has a header but no student rows.")
    return rows

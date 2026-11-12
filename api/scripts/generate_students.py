"""Generate a synthetic student file for uploading. Never use real student data.

    docker compose exec api python scripts/generate_students.py \
        --rows 200 --programmes CSE,ECE,ME --errors 8 --out /app/data/sahyadri.csv

APAAR IDs are random 11 digits plus the check digit the mock registry expects,
so every clean row passes the registry stage. `--errors N` then breaks N rows,
cycling through one of each kind of mistake the pipeline should catch.
"""

import argparse
import csv
import random
import sys
from pathlib import Path

from faker import Faker

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.apaar import verhoeff_check_digit  # noqa: E402
from app.pipeline.parser import COLUMNS  # noqa: E402


def make_apaar_id(rng: random.Random) -> str:
    body = str(rng.randint(1, 9)) + "".join(str(rng.randint(0, 9)) for _ in range(10))
    return body + verhoeff_check_digit(body)


def break_row(kind: int, row: dict[str, str], previous: dict[str, str]) -> None:
    match kind % 7:
        case 0:  # too short
            row["apaar_id"] = row["apaar_id"][:9]
        case 1:  # well-formed but not in the (mock) registry
            last = int(row["apaar_id"][-1])
            row["apaar_id"] = row["apaar_id"][:-1] + str((last + 1) % 10)
        case 2:
            row["full_name"] = ""
        case 3:
            row["date_of_birth"] = "31/02/2007"
        case 4:
            row["programme_code"] = "XYZ"
        case 5:  # same student twice in one file
            row["apaar_id"] = previous["apaar_id"]
        case 6:
            row["gender"] = "unknown"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--rows", type=int, default=100)
    parser.add_argument("--programmes", default="CSE", help="comma-separated programme codes")
    parser.add_argument("--errors", type=int, default=0, help="number of rows to break on purpose")
    parser.add_argument("--prefix", default="2026", help="prefix for enrolment numbers")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    rng = random.Random(args.seed)
    fake = Faker("en_IN")
    fake.seed_instance(args.seed)
    programmes = [code.strip().upper() for code in args.programmes.split(",")]

    apaar_ids: set[str] = set()
    while len(apaar_ids) < args.rows:
        apaar_ids.add(make_apaar_id(rng))

    # sort before shuffling: set order varies between runs, and --seed should be reproducible
    ordered = sorted(apaar_ids)
    rng.shuffle(ordered)

    rows = []
    for number, apaar_id in enumerate(ordered, start=1):
        gender = rng.choice(["male", "female"])
        name = fake.name_male() if gender == "male" else fake.name_female()
        programme = programmes[number % len(programmes)]
        rows.append(
            {
                "apaar_id": apaar_id,
                "full_name": name,
                "date_of_birth": fake.date_of_birth(minimum_age=17, maximum_age=22).isoformat(),
                "gender": gender,
                "programme_code": programme,
                "enrolment_no": f"{args.prefix}{programme}{number:05d}",
            }
        )

    # never break row 0, so "duplicate of the previous row" always has a clean row to copy
    broken = rng.sample(range(1, len(rows)), k=min(args.errors, len(rows) - 1))
    for kind, index in enumerate(sorted(broken)):
        break_row(kind, rows[index], rows[index - 1])

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} rows ({len(broken)} deliberately broken) to {args.out}")


if __name__ == "__main__":
    main()

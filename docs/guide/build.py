"""Build docs/AcadLedger-System-Guide.pdf from guide.html.

    python3 docs/guide/build.py

Needs Pillow and Google Chrome. The screenshots in img/ are full captures of the
running app; this crops them to the part each figure shows, then prints the page
to PDF with headless Chrome.
"""

import subprocess
import tempfile
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

# name -> (top, bottom) in pixels of the original capture
CROPS = {
    "home": (0, 1120),
    "uploads": (0, 1000),
    "upload-errors": (1270, 2390),
    "upload-ready": (0, 1340),
    "institute": (0, 1300),
    "students-qr": (0, 1262),
    "verified": (0, 1290),
    "dashboard": (0, 1596),
    "audit": (0, 1292),
}


def main() -> None:
    out = HERE / "figures"
    out.mkdir(exist_ok=True)
    for name, (top, bottom) in CROPS.items():
        image = Image.open(HERE / "img" / f"{name}.png").convert("RGB")
        image.crop((0, top, image.width, bottom)).save(out / f"{name}.png", optimize=True)

    pdf = HERE.parent / "AcadLedger-System-Guide.pdf"
    # A throwaway profile: without one, headless Chrome hangs if Chrome is already open.
    with tempfile.TemporaryDirectory() as profile:
        subprocess.run(
            [
                CHROME,
                "--headless=new",
                "--disable-gpu",
                "--no-first-run",
                f"--user-data-dir={profile}",
                "--no-pdf-header-footer",
                f"--print-to-pdf={pdf}",
                (HERE / "guide.html").as_uri(),
            ],
            check=True,
            capture_output=True,
            timeout=120,
        )
    print(f"wrote {pdf}")


if __name__ == "__main__":
    main()

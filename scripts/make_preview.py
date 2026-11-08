"""Build docs/preview.png: a contact sheet of the first 12 sample thumbnails.

    python scripts/make_preview.py [--template templates/card.json] [--count 12]
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image

from csv_to_assets.pipeline import read_rows
from csv_to_assets.render_png import render_png
from csv_to_assets.template import load_template

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--template", type=Path, default=ROOT / "templates" / "card.json")
    ap.add_argument("--csv", type=Path, default=ROOT / "samples" / "books.csv")
    ap.add_argument("--out", type=Path, default=ROOT / "docs" / "preview.png")
    ap.add_argument("--count", type=int, default=12)
    ap.add_argument("--columns", type=int, default=4)
    ap.add_argument("--thumb-width", type=int, default=300)
    args = ap.parse_args()

    template = load_template(args.template)
    rows = read_rows(args.csv)[: args.count]
    tw = args.thumb_width
    th = round(tw * template.height / template.width)
    gap = 16
    cols = args.columns
    n_rows = -(-len(rows) // cols)

    sheet = Image.new("RGB", (cols * tw + (cols + 1) * gap, n_rows * th + (n_rows + 1) * gap), (236, 233, 226))
    for i, row in enumerate(rows):
        img = render_png(template, row, size=(tw, th), base_dir=args.csv.parent)
        x = gap + (i % cols) * (tw + gap)
        y = gap + (i // cols) * (th + gap)
        sheet.paste(img, (x, y))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(args.out, optimize=True)
    print(f"wrote {args.out} ({sheet.width}x{sheet.height})")


if __name__ == "__main__":
    main()

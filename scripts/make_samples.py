"""Generate the neutral sample dataset: samples/books.csv plus placeholder covers.

The covers are deliberately abstract (geometric patterns drawn with Pillow)
so the repository ships no third-party artwork. Re-run this script to
regenerate everything deterministically.

    python scripts/make_samples.py
"""

from __future__ import annotations

import csv
import math
import random
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "samples"
COVERS = SAMPLES / "covers"

SERIES = [
    ("Reading Level A", "#2F6F9F", "Grades K-1"),
    ("Reading Level B", "#3C8D6E", "Grades 1-2"),
    ("Reading Level C", "#C0652B", "Grades 2-3"),
    ("Reading Level D", "#7D4FA3", "Grades 3-4"),
    ("Reading Level E", "#B33A4B", "Grades 4-5"),
]

TOPICS = [
    ("Animals Near Home", "Finding the creatures that share our streets"),
    ("Weather Watch", "Clouds, wind and what tomorrow brings"),
    ("Maps and Journeys", "How people find their way"),
    ("Shapes All Around", "Spotting circles, squares and triangles"),
    ("Kitchen Science", "Simple experiments with everyday things"),
    ("Life in a Pond", "Who lives above and below the surface"),
    ("Tools and Machines", "From levers to wheels"),
    ("Night Sky", "Stars, planets and the moon"),
]

PATTERNS = ("stripes", "dots", "waves", "grid", "blocks")


def _mix(c1: tuple[int, int, int], c2: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    return tuple(int(a + (b - a) * t) for a, b in zip(c1, c2))  # type: ignore[return-value]


def _hex(c: str) -> tuple[int, int, int]:
    c = c.lstrip("#")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


def draw_cover(path: Path, base: str, pattern: str, seed: int, size: tuple[int, int] = (520, 480)) -> None:
    rng = random.Random(seed)
    w, h = size
    bg = _hex(base)
    light = _mix(bg, (255, 255, 255), 0.35)
    dark = _mix(bg, (0, 0, 0), 0.25)
    img = Image.new("RGB", size, light)
    d = ImageDraw.Draw(img)

    if pattern == "stripes":
        step = 36
        for i in range(-h, w + h, step):
            d.polygon([(i, 0), (i + step // 2, 0), (i + step // 2 - h, h), (i - h, h)], fill=bg)
    elif pattern == "dots":
        r = 18
        for y in range(r, h, r * 3):
            for x in range(r + (r if (y // (r * 3)) % 2 else 0), w, r * 3):
                d.ellipse((x - r, y - r, x + r, y + r), fill=bg if rng.random() > 0.2 else dark)
    elif pattern == "waves":
        for k in range(8):
            pts = [(x, h * 0.15 + k * h * 0.11 + 18 * math.sin(x / 48 + k)) for x in range(0, w + 1, 8)]
            pts += [(w, h), (0, h)]
            d.polygon(pts, fill=_mix(bg, dark, k / 8))
    elif pattern == "grid":
        cell = 60
        for y in range(0, h, cell):
            for x in range(0, w, cell):
                if rng.random() > 0.45:
                    d.rectangle((x + 4, y + 4, x + cell - 4, y + cell - 4), fill=bg if rng.random() > 0.3 else dark)
    else:  # blocks
        for _ in range(14):
            bw, bh = rng.randint(80, 220), rng.randint(60, 200)
            x, y = rng.randint(-40, w - 40), rng.randint(-40, h - 40)
            d.rectangle((x, y, x + bw, y + bh), fill=_mix(bg, dark, rng.random() * 0.6))

    # A soft circular highlight gives every cover a focal point.
    cx, cy, rad = int(w * 0.68), int(h * 0.4), int(min(w, h) * 0.22)
    d.ellipse((cx - rad, cy - rad, cx + rad, cy + rad), fill=_mix(light, (255, 255, 255), 0.5))
    img.save(path, optimize=True)


def main() -> None:
    COVERS.mkdir(parents=True, exist_ok=True)
    rows = []
    n = 0
    for s_idx, (series, color, grade) in enumerate(SERIES):
        for unit, (topic, subtitle) in enumerate(TOPICS, start=1):
            n += 1
            level = "ABCDE"[s_idx]
            cover_name = f"cover-{level.lower()}-{unit:02d}.png"
            pattern = PATTERNS[(s_idx + unit) % len(PATTERNS)]
            draw_cover(COVERS / cover_name, color, pattern, seed=n)
            rows.append(
                {
                    "id": f"RL-{level}-{unit:02d}",
                    "title": f"{topic}",
                    "subtitle": subtitle,
                    "series": f"{series} - Unit {unit}",
                    "grade_band": grade,
                    "level": level,
                    "pages": str(16 + 8 * s_idx + (unit % 3) * 4),
                    "color": color,
                    "cover_image": f"covers/{cover_name}",
                }
            )

    with (SAMPLES / "books.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {len(rows)} rows and {len(rows)} covers to {SAMPLES}")


if __name__ == "__main__":
    main()

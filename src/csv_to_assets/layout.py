"""Renderer-independent layout helpers: colours, text fitting, image geometry.

Both the PNG and PDF renderers call into this module so that a template lays
out identically regardless of output format. Text measurement is injected as
a callable so the same wrapping code works with Pillow and reportlab metrics.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

RGB = tuple[int, int, int]
Measure = Callable[[str, float], float]  # (text, font_size) -> width

_NAMED = {
    "white": (255, 255, 255),
    "black": (0, 0, 0),
    "transparent": None,
}


def parse_color(value: str | None, default: RGB = (0, 0, 0)) -> RGB | None:
    """Parse ``#rgb``, ``#rrggbb`` or a few named colours. ``None`` means transparent."""
    if value is None or value == "":
        return default
    v = value.strip().lower()
    if v in _NAMED:
        return _NAMED[v]
    if v.startswith("#"):
        v = v[1:]
    if len(v) == 3:
        v = "".join(ch * 2 for ch in v)
    if len(v) != 6:
        raise ValueError(f"unrecognised colour {value!r}")
    try:
        return int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16)
    except ValueError as exc:
        raise ValueError(f"unrecognised colour {value!r}") from exc


def contrast_text_color(bg: RGB) -> RGB:
    """Black or white, whichever reads better on ``bg`` (WCAG luminance)."""
    r, g, b = (c / 255 for c in bg)
    lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
    return (20, 20, 20) if lum > 0.55 else (255, 255, 255)


@dataclass(frozen=True)
class FittedText:
    lines: tuple[str, ...]
    size: float
    line_height: float

    @property
    def height(self) -> float:
        return self.line_height * len(self.lines)


def wrap_lines(text: str, size: float, max_width: float, measure: Measure) -> list[str]:
    """Greedy word wrap. Over-long single words are broken by character."""
    lines: list[str] = []
    for paragraph in text.split("\n"):
        words = paragraph.split()
        if not words:
            lines.append("")
            continue
        current = ""
        for word in words:
            trial = f"{current} {word}".strip()
            if measure(trial, size) <= max_width or not current:
                if not current and measure(word, size) > max_width:
                    # Break a single word that cannot fit on its own line.
                    chunk = ""
                    for ch in word:
                        if measure(chunk + ch, size) <= max_width or not chunk:
                            chunk += ch
                        else:
                            lines.append(chunk)
                            chunk = ch
                    current = chunk
                else:
                    current = trial
            else:
                lines.append(current)
                current = word
        lines.append(current)
    return lines


def fit_text(
    text: str,
    size: float,
    max_width: float,
    max_height: float,
    measure: Measure,
    *,
    min_size: float = 8,
    max_lines: int | None = None,
    leading: float = 1.2,
    shrink: bool = True,
) -> FittedText:
    """Wrap ``text`` into the box, shrinking the font until it fits.

    If it still does not fit at ``min_size`` the last line is truncated with
    an ellipsis rather than overflowing the box.
    """
    current = size
    while True:
        lines = wrap_lines(text, current, max_width, measure)
        line_h = current * leading
        too_many = max_lines is not None and len(lines) > max_lines
        too_tall = line_h * len(lines) > max_height
        if not (too_many or too_tall) or not shrink or current <= min_size:
            break
        current = max(min_size, current - 1)

    limit = len(lines)
    if max_lines is not None:
        limit = min(limit, max_lines)
    by_height = max(1, int(max_height // (current * leading)))
    limit = max(1, min(limit, by_height))

    if len(lines) > limit:
        kept = lines[:limit]
        last = kept[-1]
        while last and measure(last + "…", current) > max_width:
            last = last[:-1].rstrip()
        kept[-1] = last + "…"
        lines = kept

    return FittedText(tuple(lines), current, current * leading)


def fit_image(
    src_w: int, src_h: int, box_w: float, box_h: float, mode: str
) -> tuple[float, float, float, float]:
    """Return ``(draw_w, draw_h, offset_x, offset_y)`` for placing an image in a box.

    ``cover`` fills the box (callers must clip), ``contain`` letterboxes,
    ``stretch`` ignores aspect ratio.
    """
    if mode == "stretch":
        return box_w, box_h, 0.0, 0.0
    scale_w = box_w / src_w
    scale_h = box_h / src_h
    scale = max(scale_w, scale_h) if mode == "cover" else min(scale_w, scale_h)
    w, h = src_w * scale, src_h * scale
    return w, h, (box_w - w) / 2, (box_h - h) / 2

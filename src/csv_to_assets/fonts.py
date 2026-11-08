"""Font resolution shared by the PNG and PDF renderers.

Templates name fonts by family (``"DejaVuSans-Bold"``) or by path. Names are
looked up in the bundled ``fonts/`` directory first, then treated as a path
relative to the template. Anything unresolvable falls back to Pillow's
built-in font for PNGs and Helvetica for PDFs, so a template never fails
just because a font is missing on a build machine.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PIL import ImageFont

FONT_DIR = Path(__file__).parent / "fonts"
DEFAULT_FONT = "DejaVuSans"
DEFAULT_BOLD_FONT = "DejaVuSans-Bold"


def bundled_fonts() -> list[str]:
    return sorted(p.stem for p in FONT_DIR.glob("*.ttf"))


def resolve_font_path(name: str | None, base_dir: Path | None = None) -> Path | None:
    """Return a TTF path for ``name`` or ``None`` if it cannot be found."""
    if not name:
        name = DEFAULT_FONT
    candidates = [FONT_DIR / f"{name}.ttf", FONT_DIR / name]
    p = Path(name)
    if p.is_absolute():
        candidates.append(p)
    elif base_dir is not None:
        candidates.append(base_dir / p)
    for c in candidates:
        if c.is_file():
            return c
    return None


@lru_cache(maxsize=256)
def _load_pil(path: str | None, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    if path is not None:
        return ImageFont.truetype(path, size=size)
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # Pillow < 10.1
        return ImageFont.load_default()


def pil_font(name: str | None, size: float, base_dir: Path | None = None):
    """A Pillow font object at ``size`` pixels (cached per path/size)."""
    path = resolve_font_path(name, base_dir)
    return _load_pil(str(path) if path else None, max(1, int(round(size))))


_registered: set[str] = set()


def pdf_font(name: str | None, base_dir: Path | None = None) -> str:
    """Register a TTF with reportlab (once) and return its PDF font name.

    Returns ``"Helvetica"`` when the font cannot be resolved.
    """
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    path = resolve_font_path(name, base_dir)
    if path is None:
        return "Helvetica"
    font_name = path.stem
    if font_name not in _registered:
        pdfmetrics.registerFont(TTFont(font_name, str(path)))
        _registered.add(font_name)
    return font_name

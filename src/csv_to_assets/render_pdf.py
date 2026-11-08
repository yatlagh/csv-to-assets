"""Render one CSV row through a template into a single-page vector PDF.

The PDF is drawn natively with reportlab (text stays selectable, shapes stay
vectors); only raster images from the CSV are embedded as bitmaps. Template
units map to PDF points, so a 600x800 template produces a 600x800 pt page
unless ``size`` overrides it.
"""

from __future__ import annotations

from pathlib import Path
from typing import IO, Mapping

from PIL import Image
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen import canvas as rl_canvas

from . import fonts
from .layout import contrast_text_color, fit_image, fit_text, parse_color
from .template import Element, Template, bind


def _rgb(c: tuple[int, int, int]) -> tuple[float, float, float]:
    return c[0] / 255, c[1] / 255, c[2] / 255


def _open_image(src: str, base_dir: Path) -> Image.Image | None:
    if not src:
        return None
    p = Path(src)
    if not p.is_absolute():
        p = base_dir / p
    if not p.is_file():
        raise FileNotFoundError(f"image not found: {p}")
    return Image.open(p).convert("RGB")


def _rounded_clip(c: rl_canvas.Canvas, x: float, y: float, w: float, h: float, r: float) -> None:
    path = c.beginPath()
    path.roundRect(x, y, w, h, r)
    c.clipPath(path, stroke=0, fill=0)


def _draw_image(c, img: Image.Image, x0, y0, x1, y1, page_h, fit: str, radius: float) -> None:
    bw, bh = x1 - x0, y1 - y0
    w, h, ox, oy = fit_image(img.width, img.height, bw, bh, fit)
    c.saveState()
    _rounded_clip(c, x0, page_h - y1, bw, bh, radius)
    # reportlab's origin is bottom-left; flip the y coordinate.
    c.drawImage(ImageReader(img), x0 + ox, page_h - (y0 + oy + h), width=w, height=h)
    c.restoreState()


def _draw_text_block(c, text: str, box, el: Element, scale: float, base_dir: Path, page_h: float, *, color, font_name, size) -> None:
    x0, y0, x1, y1 = box
    max_w, max_h = x1 - x0, y1 - y0
    pdf_font = fonts.pdf_font(font_name, base_dir)

    def measure(s: str, pt: float) -> float:
        return pdfmetrics.stringWidth(s, pdf_font, pt)

    fitted = fit_text(
        text,
        size,
        max_w,
        max_h,
        measure,
        min_size=float(el.get("min_size", 8)) * scale,
        max_lines=el.get("max_lines"),
        leading=float(el.get("leading", 1.2)),
        shrink=bool(el.get("shrink", True)),
    )
    align = el.get("align", "left")
    valign = el.get("valign", "top")
    total_h = fitted.height
    if valign == "middle":
        top = y0 + (max_h - total_h) / 2
    elif valign == "bottom":
        top = y1 - total_h
    else:
        top = y0

    ascent = pdfmetrics.getAscent(pdf_font) / 1000 * fitted.size
    baseline_pad = (fitted.line_height - ascent) / 2

    c.setFont(pdf_font, fitted.size)
    c.setFillColorRGB(*_rgb(color))
    y = top
    for line in fitted.lines:
        baseline = page_h - (y + baseline_pad + ascent)
        if align == "center":
            c.drawCentredString(x0 + max_w / 2, baseline, line)
        elif align == "right":
            c.drawRightString(x1, baseline, line)
        else:
            c.drawString(x0, baseline, line)
        y += fitted.line_height


def render_pdf(
    template: Template,
    row: Mapping[str, str],
    out: str | Path | IO[bytes],
    *,
    size: tuple[int, int] | None = None,
    base_dir: Path | None = None,
) -> None:
    """Render ``row`` with ``template`` to ``out`` (a path or binary file)."""
    base_dir = Path(base_dir or ".")
    s = template.scale_for(size)
    W, H = template.width * s, template.height * s

    c = rl_canvas.Canvas(str(out) if isinstance(out, (str, Path)) else out, pagesize=(W, H))
    c.setTitle(row.get("title") or template.name)
    c.setAuthor("csv-to-assets")

    bg = template.background
    bg_color = parse_color(bind(bg.get("color"), row), default=(255, 255, 255)) or (255, 255, 255)
    c.setFillColorRGB(*_rgb(bg_color))
    c.rect(0, 0, W, H, stroke=0, fill=1)

    bg_src = bind(bg.get("image", ""), row)
    if bg_src:
        img = _open_image(bg_src, base_dir)
        if img is not None:
            _draw_image(c, img, 0, 0, W, H, H, bg.get("fit", "cover"), 0)

    for el in template.elements:
        x0, y0, x1, y1 = (v * s for v in el.box)
        radius = float(el.get("radius", 0)) * s

        if el.type == "rect":
            fill = parse_color(bind(el.get("fill"), row), default=(0, 0, 0))
            outline = parse_color(bind(el.get("outline"), row), default=None) if el.get("outline") else None
            opacity = float(el.get("opacity", 1.0))
            c.saveState()
            if fill is not None:
                c.setFillColorRGB(*_rgb(fill), alpha=opacity)
            if outline is not None:
                c.setStrokeColorRGB(*_rgb(outline))
                c.setLineWidth(float(el.get("outline_width", 1)) * s)
            c.roundRect(x0, H - y1, x1 - x0, y1 - y0, radius, stroke=1 if outline else 0, fill=1 if fill else 0)
            c.restoreState()

        elif el.type == "image":
            img = _open_image(bind(el.get("src"), row), base_dir)
            if img is not None:
                _draw_image(c, img, x0, y0, x1, y1, H, el.get("fit", "contain"), radius)

        elif el.type == "text":
            color = parse_color(bind(el.get("color"), row), default=(20, 20, 20)) or (20, 20, 20)
            _draw_text_block(
                c, bind(el.get("text"), row), (x0, y0, x1, y1), el, s, base_dir, H,
                color=color, font_name=el.get("font"), size=float(el.get("size", 24)) * s,
            )

        elif el.type == "pill":
            text = bind(el.get("text"), row)
            fill = parse_color(bind(el.get("fill"), row), default=(40, 40, 40)) or (40, 40, 40)
            color_raw = bind(el.get("color"), row)
            color = parse_color(color_raw) if color_raw else contrast_text_color(fill)
            font_name = el.get("font", fonts.DEFAULT_BOLD_FONT)
            pt = float(el.get("size", 16)) * s
            pad = float(el.get("padding", 10)) * s
            tw = pdfmetrics.stringWidth(text, fonts.pdf_font(font_name, base_dir), pt)
            pill_w = min(x1 - x0, tw + 2 * pad)
            align = el.get("align", "left")
            px0 = x0 if align == "left" else (x1 - pill_w if align == "right" else x0 + (x1 - x0 - pill_w) / 2)
            r = radius if el.get("radius") is not None else (y1 - y0) / 2
            c.setFillColorRGB(*_rgb(fill))
            c.roundRect(px0, H - y1, pill_w, y1 - y0, r, stroke=0, fill=1)
            _draw_text_block(
                c, text, (px0 + pad, y0, px0 + pill_w - pad, y1),
                Element("text", el.box, {"align": "center", "valign": "middle", "max_lines": 1}),
                s, base_dir, H, color=color, font_name=font_name, size=pt,
            )

    c.showPage()
    c.save()

"""Render one CSV row through a template into a Pillow image."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping

from PIL import Image, ImageChops, ImageDraw

from . import fonts
from .layout import contrast_text_color, fit_image, fit_text, parse_color
from .template import Element, Template, bind

_SUPERSAMPLE = 2  # draw at 2x and downsample for smooth rounded corners


def _resolve_image(src: str, base_dir: Path) -> Image.Image | None:
    if not src:
        return None
    p = Path(src)
    if not p.is_absolute():
        p = base_dir / p
    if not p.is_file():
        raise FileNotFoundError(f"image not found: {p}")
    return Image.open(p).convert("RGBA")


def _rounded_mask(size: tuple[int, int], radius: int) -> Image.Image:
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), radius=radius, fill=255)
    return mask


def _paste_image(canvas: Image.Image, img: Image.Image, box: tuple[int, int, int, int], fit: str, radius: int) -> None:
    x0, y0, x1, y1 = box
    bw, bh = x1 - x0, y1 - y0
    if bw <= 0 or bh <= 0:
        return
    w, h, ox, oy = fit_image(img.width, img.height, bw, bh, fit)
    resized = img.resize((max(1, int(round(w))), max(1, int(round(h)))), Image.LANCZOS)
    if fit == "cover":
        # Crop the overflow so the image exactly fills the box.
        cx, cy = int(round(-ox)), int(round(-oy))
        resized = resized.crop((cx, cy, cx + bw, cy + bh))
        ox = oy = 0
    layer = Image.new("RGBA", (bw, bh), (0, 0, 0, 0))
    layer.paste(resized, (int(round(ox)), int(round(oy))))
    mask = _rounded_mask((bw, bh), radius) if radius > 0 else None
    if mask is not None:
        alpha = layer.getchannel("A")
        layer.putalpha(ImageChops.multiply(alpha, mask))
    canvas.alpha_composite(layer, (x0, y0))


def _draw_text_block(
    draw: ImageDraw.ImageDraw,
    text: str,
    box: tuple[int, int, int, int],
    el: Element,
    scale: float,
    base_dir: Path,
    *,
    color,
    font_name: str | None,
    size: float,
) -> None:
    x0, y0, x1, y1 = box
    max_w, max_h = x1 - x0, y1 - y0

    def measure(s: str, px: float) -> float:
        f = fonts.pil_font(font_name, px, base_dir)
        return draw.textlength(s, font=f)

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
    font = fonts.pil_font(font_name, fitted.size, base_dir)
    align = el.get("align", "left")
    valign = el.get("valign", "top")

    total_h = fitted.height
    if valign == "middle":
        y = y0 + (max_h - total_h) / 2
    elif valign == "bottom":
        y = y1 - total_h
    else:
        y = y0

    # Pillow positions text by its ascender box; shift so the first line sits
    # inside the leading like a typesetter would expect.
    ascent, _descent = font.getmetrics()
    baseline_pad = (fitted.line_height - ascent) / 2

    for line in fitted.lines:
        w = draw.textlength(line, font=font)
        if align == "center":
            x = x0 + (max_w - w) / 2
        elif align == "right":
            x = x1 - w
        else:
            x = x0
        draw.text((x, y + baseline_pad), line, font=font, fill=color)
        y += fitted.line_height


def render_png(
    template: Template,
    row: Mapping[str, str],
    *,
    size: tuple[int, int] | None = None,
    base_dir: Path | None = None,
) -> Image.Image:
    """Render ``row`` with ``template`` and return an RGB image.

    ``size`` is the output size in pixels; the template is scaled uniformly to
    fit. ``base_dir`` is the directory that image paths in the CSV are
    relative to (normally the CSV's own directory).
    """
    base_dir = Path(base_dir or ".")
    base_scale = template.scale_for(size)
    final = (int(round(template.width * base_scale)), int(round(template.height * base_scale)))
    s = base_scale * _SUPERSAMPLE
    W, H = final[0] * _SUPERSAMPLE, final[1] * _SUPERSAMPLE

    bg = template.background
    bg_color = parse_color(bind(bg.get("color"), row), default=(255, 255, 255)) or (255, 255, 255)
    canvas = Image.new("RGBA", (W, H), bg_color + (255,))

    bg_image_src = bind(bg.get("image", ""), row)
    if bg_image_src:
        img = _resolve_image(bg_image_src, base_dir)
        if img is not None:
            _paste_image(canvas, img, (0, 0, W, H), bg.get("fit", "cover"), 0)

    draw = ImageDraw.Draw(canvas, "RGBA")

    for el in template.elements:
        x0, y0, x1, y1 = (int(round(v * s)) for v in el.box)
        box = (x0, y0, x1, y1)
        radius = int(round(float(el.get("radius", 0)) * s))

        if el.type == "rect":
            fill = parse_color(bind(el.get("fill"), row), default=(0, 0, 0))
            opacity = int(round(255 * float(el.get("opacity", 1.0))))
            outline = parse_color(bind(el.get("outline"), row), default=None) if el.get("outline") else None
            width = int(round(float(el.get("outline_width", 0)) * s))
            if fill is not None or outline is not None:
                kwargs = dict(
                    radius=radius,
                    fill=(fill + (opacity,)) if fill else None,
                    outline=(outline + (255,)) if outline else None,
                    width=width if outline else 0,
                )
                if opacity < 255:
                    # ImageDraw writes pixels rather than blending them, so a
                    # translucent shape must go through its own layer.
                    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
                    ImageDraw.Draw(layer).rounded_rectangle((x0, y0, x1 - 1, y1 - 1), **kwargs)
                    canvas.alpha_composite(layer)
                    draw = ImageDraw.Draw(canvas, "RGBA")
                else:
                    draw.rounded_rectangle((x0, y0, x1 - 1, y1 - 1), **kwargs)

        elif el.type == "image":
            img = _resolve_image(bind(el.get("src"), row), base_dir)
            if img is not None:
                _paste_image(canvas, img, box, el.get("fit", "contain"), radius)
                draw = ImageDraw.Draw(canvas, "RGBA")

        elif el.type == "text":
            text = bind(el.get("text"), row)
            color = parse_color(bind(el.get("color"), row), default=(20, 20, 20)) or (20, 20, 20)
            _draw_text_block(
                draw, text, box, el, s, base_dir,
                color=color, font_name=el.get("font"), size=float(el.get("size", 24)) * s,
            )

        elif el.type == "pill":
            text = bind(el.get("text"), row)
            fill = parse_color(bind(el.get("fill"), row), default=(40, 40, 40)) or (40, 40, 40)
            color_raw = bind(el.get("color"), row)
            color = parse_color(color_raw) if color_raw else contrast_text_color(fill)
            font_name = el.get("font", fonts.DEFAULT_BOLD_FONT)
            px = float(el.get("size", 16)) * s
            pad = float(el.get("padding", 10)) * s
            font = fonts.pil_font(font_name, px, base_dir)
            tw = draw.textlength(text, font=font)
            pill_w = min(x1 - x0, int(round(tw + 2 * pad)))
            align = el.get("align", "left")
            px0 = x0 if align == "left" else (x1 - pill_w if align == "right" else x0 + (x1 - x0 - pill_w) // 2)
            r = radius if el.get("radius") is not None else (y1 - y0) // 2
            draw.rounded_rectangle((px0, y0, px0 + pill_w - 1, y1 - 1), radius=r, fill=fill + (255,))
            inner = (int(px0 + pad), y0, int(px0 + pill_w - pad), y1)
            _draw_text_block(
                draw, text, inner, Element("text", el.box, {"align": "center", "valign": "middle", "max_lines": 1}),
                s, base_dir, color=color, font_name=font_name, size=px,
            )

    out = canvas.convert("RGB")
    if _SUPERSAMPLE != 1:
        out = out.resize(final, Image.LANCZOS)
    return out

"""Template loading, validation and field binding.

A template is a small JSON document describing a fixed-size canvas and an
ordered list of elements drawn onto it. Any string value may reference a CSV
column with ``{column}`` syntax; the reference is resolved per row at render
time. See ``templates/`` for two complete examples and the README for the
full format description.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

ELEMENT_TYPES = {"rect", "image", "text", "pill"}
FIT_MODES = {"cover", "contain", "stretch"}
ALIGNMENTS = {"left", "center", "right"}

_FIELD_RE = re.compile(r"\{([A-Za-z0-9_\- ]+)\}")


class TemplateError(ValueError):
    """Raised when a template file is malformed."""


@dataclass(frozen=True)
class Element:
    """One drawable item. ``box`` is ``[x0, y0, x1, y1]`` in template units."""

    type: str
    box: tuple[float, float, float, float]
    props: Mapping[str, Any] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        return self.props.get(key, default)


@dataclass(frozen=True)
class Template:
    name: str
    width: int
    height: int
    background: Mapping[str, Any]
    elements: tuple[Element, ...]
    source: Path | None = None

    @property
    def size(self) -> tuple[int, int]:
        return self.width, self.height

    def scale_for(self, target: tuple[int, int] | None) -> float:
        """Uniform scale factor to render at ``target`` pixels (fit inside)."""
        if target is None:
            return 1.0
        tw, th = target
        return min(tw / self.width, th / self.height)

    def required_columns(self) -> set[str]:
        """All CSV columns referenced anywhere in the template."""
        found: set[str] = set()
        _collect_fields(self.background, found)
        for el in self.elements:
            _collect_fields(el.props, found)
        return found


def _collect_fields(value: Any, acc: set[str]) -> None:
    if isinstance(value, str):
        acc.update(_FIELD_RE.findall(value))
    elif isinstance(value, Mapping):
        for v in value.values():
            _collect_fields(v, acc)
    elif isinstance(value, (list, tuple)):
        for v in value:
            _collect_fields(v, acc)


def bind(value: Any, row: Mapping[str, str]) -> Any:
    """Substitute ``{column}`` references in ``value`` using ``row``.

    Non-string values pass through untouched. A reference to a missing column
    raises ``KeyError`` with the list of available columns so the failure is
    actionable from the command line.
    """
    if not isinstance(value, str):
        return value

    def repl(m: re.Match[str]) -> str:
        key = m.group(1)
        if key not in row:
            raise KeyError(
                f"template references column {key!r} which is not in the CSV "
                f"(available: {', '.join(sorted(row))})"
            )
        return row[key]

    return _FIELD_RE.sub(repl, value)


def _require(obj: Mapping[str, Any], key: str, where: str) -> Any:
    if key not in obj:
        raise TemplateError(f"{where}: missing required key {key!r}")
    return obj[key]


def _parse_box(raw: Any, where: str) -> tuple[float, float, float, float]:
    if not (isinstance(raw, (list, tuple)) and len(raw) == 4):
        raise TemplateError(f"{where}: 'box' must be [x0, y0, x1, y1]")
    try:
        x0, y0, x1, y1 = (float(v) for v in raw)
    except (TypeError, ValueError) as exc:
        raise TemplateError(f"{where}: 'box' values must be numbers") from exc
    if x1 <= x0 or y1 <= y0:
        raise TemplateError(f"{where}: 'box' must have positive width and height")
    return x0, y0, x1, y1


def parse_template(data: Mapping[str, Any], source: Path | None = None) -> Template:
    """Validate a decoded JSON object and return a ``Template``."""
    where = f"template {source}" if source else "template"
    name = str(data.get("name") or (source.stem if source else "untitled"))

    size = _require(data, "size", where)
    if not (isinstance(size, (list, tuple)) and len(size) == 2):
        raise TemplateError(f"{where}: 'size' must be [width, height]")
    width, height = int(size[0]), int(size[1])
    if width <= 0 or height <= 0:
        raise TemplateError(f"{where}: 'size' must be positive")

    background = data.get("background") or {}
    if not isinstance(background, Mapping):
        raise TemplateError(f"{where}: 'background' must be an object")
    if "fit" in background and background["fit"] not in FIT_MODES:
        raise TemplateError(f"{where}: background 'fit' must be one of {sorted(FIT_MODES)}")

    raw_elements = data.get("elements") or []
    if not isinstance(raw_elements, list):
        raise TemplateError(f"{where}: 'elements' must be a list")

    elements: list[Element] = []
    for i, raw in enumerate(raw_elements):
        ew = f"{where}, element #{i}"
        if not isinstance(raw, Mapping):
            raise TemplateError(f"{ew}: must be an object")
        etype = _require(raw, "type", ew)
        if etype not in ELEMENT_TYPES:
            raise TemplateError(f"{ew}: unknown type {etype!r} (expected one of {sorted(ELEMENT_TYPES)})")
        box = _parse_box(_require(raw, "box", ew), ew)
        props = {k: v for k, v in raw.items() if k not in ("type", "box")}

        if etype in ("text", "pill") and "text" not in props:
            raise TemplateError(f"{ew}: {etype} element needs a 'text' value")
        if etype == "image" and "src" not in props:
            raise TemplateError(f"{ew}: image element needs a 'src' value")
        if "fit" in props and props["fit"] not in FIT_MODES:
            raise TemplateError(f"{ew}: 'fit' must be one of {sorted(FIT_MODES)}")
        if "align" in props and props["align"] not in ALIGNMENTS:
            raise TemplateError(f"{ew}: 'align' must be one of {sorted(ALIGNMENTS)}")

        elements.append(Element(type=etype, box=box, props=props))

    return Template(
        name=name,
        width=width,
        height=height,
        background=dict(background),
        elements=tuple(elements),
        source=source,
    )


def load_template(path: str | Path) -> Template:
    """Read and validate a template JSON file."""
    p = Path(path)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise TemplateError(f"template not found: {p}") from None
    except json.JSONDecodeError as exc:
        raise TemplateError(f"template {p} is not valid JSON: {exc}") from exc
    if not isinstance(data, Mapping):
        raise TemplateError(f"template {p}: top level must be an object")
    return parse_template(data, source=p)

"""Batch orchestration: CSV in, a folder of PNGs and PDFs out.

Each CSV row becomes one job. Jobs are independent, so they are fanned out
across a ``multiprocessing`` pool; the template is loaded once per worker
(via the pool initializer) rather than pickled with every job.
"""

from __future__ import annotations

import csv
import os
import re
import sys
import time
import unicodedata
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Mapping, Sequence

from .render_pdf import render_pdf
from .render_png import render_png
from .template import Template, load_template

FORMATS = ("png", "pdf")


class PipelineError(RuntimeError):
    """Raised for configuration problems detected before any rendering."""


@dataclass(frozen=True)
class GenerateOptions:
    csv_path: Path
    template_path: Path
    out_dir: Path
    formats: tuple[str, ...] = FORMATS
    size: tuple[int, int] | None = None
    workers: int = 0  # 0 = os.cpu_count()
    filename_column: str | None = None  # defaults to "id", else "title", else row index
    limit: int | None = None
    quiet: bool = False


@dataclass
class JobResult:
    index: int
    stem: str
    outputs: tuple[Path, ...] = ()
    error: str | None = None
    seconds: float = 0.0


@dataclass
class Summary:
    rows: int
    png: int
    pdf: int
    failed: int
    seconds: float
    workers: int
    out_dir: Path
    errors: list[tuple[str, str]] = field(default_factory=list)

    def format(self) -> str:
        lines = [
            f"Done: {self.rows} rows -> {self.png} PNG, {self.pdf} PDF "
            f"in {self.seconds:.1f}s using {self.workers} worker(s)",
            f"Output: {self.out_dir}",
        ]
        if self.failed:
            lines.append(f"Failed: {self.failed} row(s)")
            for stem, err in self.errors[:10]:
                lines.append(f"  - {stem}: {err}")
            if len(self.errors) > 10:
                lines.append(f"  ... and {len(self.errors) - 10} more")
        return "\n".join(lines)


def slugify(value: str, fallback: str = "item") -> str:
    """Filesystem-safe, lowercase, ASCII-only stem."""
    norm = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", norm.lower()).strip("-")
    return slug[:80] or fallback


def read_rows(csv_path: Path) -> list[dict[str, str]]:
    with csv_path.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        if not reader.fieldnames:
            raise PipelineError(f"{csv_path}: CSV has no header row")
        rows = []
        for raw in reader:
            rows.append({(k or "").strip(): (v or "").strip() for k, v in raw.items()})
    if not rows:
        raise PipelineError(f"{csv_path}: CSV has a header but no data rows")
    return rows


def parse_size(text: str | None) -> tuple[int, int] | None:
    if not text:
        return None
    m = re.fullmatch(r"\s*(\d+)\s*[xX]\s*(\d+)\s*", text)
    if not m:
        raise PipelineError(f"--size must look like 600x800, got {text!r}")
    return int(m.group(1)), int(m.group(2))


def parse_formats(text: str | Sequence[str]) -> tuple[str, ...]:
    parts = text.split(",") if isinstance(text, str) else list(text)
    fmts = tuple(dict.fromkeys(p.strip().lower() for p in parts if p.strip()))
    bad = [f for f in fmts if f not in FORMATS]
    if bad:
        raise PipelineError(f"unknown format(s) {bad}; choose from {', '.join(FORMATS)}")
    if not fmts:
        raise PipelineError("at least one output format is required")
    return fmts


def _stems(rows: Iterable[Mapping[str, str]], column: str | None) -> list[str]:
    seen: dict[str, int] = {}
    stems = []
    for i, row in enumerate(rows, start=1):
        key = column or ("id" if "id" in row else "title" if "title" in row else None)
        base = slugify(row.get(key, "") if key else "", fallback=f"row-{i:04d}") if key else f"row-{i:04d}"
        n = seen.get(base, 0)
        seen[base] = n + 1
        stems.append(base if n == 0 else f"{base}-{n + 1}")
    return stems


# --- worker side -----------------------------------------------------------

_worker_template: Template | None = None
_worker_opts: GenerateOptions | None = None


def _init_worker(template_path: str, opts: GenerateOptions) -> None:
    global _worker_template, _worker_opts
    _worker_template = load_template(template_path)
    _worker_opts = opts


def _run_job(index: int, stem: str, row: dict[str, str]) -> JobResult:
    assert _worker_template is not None and _worker_opts is not None
    t0 = time.perf_counter()
    try:
        outputs = render_row(_worker_template, row, stem, _worker_opts)
        return JobResult(index, stem, tuple(outputs), seconds=time.perf_counter() - t0)
    except Exception as exc:  # report, don't crash the pool
        return JobResult(index, stem, error=f"{type(exc).__name__}: {exc}", seconds=time.perf_counter() - t0)


def render_row(template: Template, row: Mapping[str, str], stem: str, opts: GenerateOptions) -> list[Path]:
    """Render a single row to every requested format. Returns written paths."""
    base_dir = opts.csv_path.parent
    written: list[Path] = []
    if "png" in opts.formats:
        png_dir = opts.out_dir / "png"
        png_dir.mkdir(parents=True, exist_ok=True)
        img = render_png(template, row, size=opts.size, base_dir=base_dir)
        target = png_dir / f"{stem}.png"
        img.save(target, optimize=True)
        written.append(target)
    if "pdf" in opts.formats:
        pdf_dir = opts.out_dir / "pdf"
        pdf_dir.mkdir(parents=True, exist_ok=True)
        target = pdf_dir / f"{stem}.pdf"
        render_pdf(template, row, target, size=opts.size, base_dir=base_dir)
        written.append(target)
    return written


# --- driver side -----------------------------------------------------------

def _progress(done: int, total: int, stem: str, failed: int, stream) -> None:
    width = 28
    filled = int(width * done / total) if total else width
    bar = "#" * filled + "-" * (width - filled)
    tail = f"  failed={failed}" if failed else ""
    stream.write(f"\r[{bar}] {done:>4}/{total}  {stem[:36]:<36}{tail}")
    stream.flush()


def generate(
    opts: GenerateOptions,
    *,
    on_result: Callable[[JobResult], None] | None = None,
    stream=None,
) -> Summary:
    """Run the whole batch and return a ``Summary``."""
    stream = stream or sys.stderr
    template = load_template(opts.template_path)
    rows = read_rows(opts.csv_path)
    if opts.limit:
        rows = rows[: opts.limit]

    missing = template.required_columns() - set(rows[0])
    if missing:
        raise PipelineError(
            f"template {template.name!r} needs column(s) {sorted(missing)} "
            f"not present in {opts.csv_path.name} (has: {sorted(rows[0])})"
        )

    opts.out_dir.mkdir(parents=True, exist_ok=True)
    stems = _stems(rows, opts.filename_column)
    workers = opts.workers or os.cpu_count() or 1
    workers = max(1, min(workers, len(rows)))

    if not opts.quiet:
        stream.write(
            f"csv-to-assets: {len(rows)} rows x {', '.join(opts.formats)} "
            f"| template {template.name} ({template.width}x{template.height}"
            f"{' -> %dx%d' % opts.size if opts.size else ''}) | {workers} worker(s)\n"
        )

    t0 = time.perf_counter()
    results: list[JobResult] = []
    done = failed = 0

    def handle(res: JobResult) -> None:
        nonlocal done, failed
        done += 1
        if res.error:
            failed += 1
        results.append(res)
        if on_result:
            on_result(res)
        if not opts.quiet:
            _progress(done, len(rows), res.stem, failed, stream)

    if workers == 1:
        _init_worker(str(opts.template_path), opts)
        for i, (stem, row) in enumerate(zip(stems, rows)):
            handle(_run_job(i, stem, row))
    else:
        with ProcessPoolExecutor(
            max_workers=workers,
            initializer=_init_worker,
            initargs=(str(opts.template_path), opts),
        ) as pool:
            futures = [pool.submit(_run_job, i, stem, row) for i, (stem, row) in enumerate(zip(stems, rows))]
            for fut in as_completed(futures):
                handle(fut.result())

    elapsed = time.perf_counter() - t0
    if not opts.quiet:
        stream.write("\n")

    results.sort(key=lambda r: r.index)
    png = sum(1 for r in results for p in r.outputs if p.suffix == ".png")
    pdf = sum(1 for r in results for p in r.outputs if p.suffix == ".pdf")
    return Summary(
        rows=len(rows),
        png=png,
        pdf=pdf,
        failed=failed,
        seconds=elapsed,
        workers=workers,
        out_dir=opts.out_dir,
        errors=[(r.stem, r.error or "") for r in results if r.error],
    )

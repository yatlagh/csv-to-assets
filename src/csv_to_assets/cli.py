"""Command-line entry point: ``csv-to-assets generate|validate``."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .pipeline import GenerateOptions, PipelineError, generate, parse_formats, parse_size, read_rows
from .template import TemplateError, load_template


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="csv-to-assets",
        description="Generate PNG thumbnails and PDFs for every row of a CSV using a JSON layout template.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    gen = sub.add_parser("generate", help="render every CSV row to the requested formats")
    gen.add_argument("--csv", required=True, type=Path, help="input CSV with a header row")
    gen.add_argument("--template", required=True, type=Path, help="JSON layout template")
    gen.add_argument("--out", required=True, type=Path, help="output directory (png/ and pdf/ are created inside)")
    gen.add_argument("--formats", default="png,pdf", help="comma-separated: png, pdf (default: png,pdf)")
    gen.add_argument("--size", default=None, help="output size in pixels, e.g. 600x800 (default: template size)")
    gen.add_argument("--workers", type=int, default=0, help="parallel workers (default: CPU count)")
    gen.add_argument("--name-column", default=None, help="CSV column used for output file names (default: id, then title)")
    gen.add_argument("--limit", type=int, default=None, help="only render the first N rows")
    gen.add_argument("-q", "--quiet", action="store_true", help="suppress progress output")

    val = sub.add_parser("validate", help="check a template, and optionally a CSV, without rendering")
    val.add_argument("--template", required=True, type=Path)
    val.add_argument("--csv", type=Path, default=None)
    return parser


def cmd_generate(args: argparse.Namespace) -> int:
    opts = GenerateOptions(
        csv_path=args.csv,
        template_path=args.template,
        out_dir=args.out,
        formats=parse_formats(args.formats),
        size=parse_size(args.size),
        workers=args.workers,
        filename_column=args.name_column,
        limit=args.limit,
        quiet=args.quiet,
    )
    summary = generate(opts)
    print(summary.format())
    return 1 if summary.failed else 0


def cmd_validate(args: argparse.Namespace) -> int:
    template = load_template(args.template)
    cols = sorted(template.required_columns())
    print(f"template {template.name!r}: {template.width}x{template.height}, {len(template.elements)} element(s)")
    print(f"bound columns: {', '.join(cols) if cols else '(none)'}")
    if args.csv:
        rows = read_rows(args.csv)
        missing = set(cols) - set(rows[0])
        if missing:
            print(f"CSV {args.csv.name}: {len(rows)} row(s), MISSING column(s): {sorted(missing)}")
            return 1
        print(f"CSV {args.csv.name}: {len(rows)} row(s), all bound columns present")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "generate":
            return cmd_generate(args)
        return cmd_validate(args)
    except (PipelineError, TemplateError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())

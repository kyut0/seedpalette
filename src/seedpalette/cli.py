"""Command line: `seedpalette check | css | json | preview THEMES.yaml`."""

import argparse
from pathlib import Path
import sys

from pydantic import ValidationError
import yaml

from seedpalette.palette import ThemeSet, load
from seedpalette.render import preview_html, report, to_css, to_json


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="seedpalette",
        description="Grow a few seed colors into full, readable light and dark themes.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    check = sub.add_parser("check", help="report every derived or adjusted color")
    check.add_argument("themes", type=Path, help="theme file (YAML)")

    css = sub.add_parser("css", help="write CSS custom properties for every theme")
    css.add_argument("themes", type=Path)
    css.add_argument("-o", "--out", type=Path, help="output file (default: stdout)")
    css.add_argument("--mode-attr", default="data-theme", help="root attribute for light/dark")
    css.add_argument("--theme-attr", default="data-palette", help="root attribute for theme")
    css.add_argument(
        "--default-mode", choices=["light", "dark"], default="dark",
        help="mode used on bare :root when no attribute is set",
    )  # fmt: skip

    js = sub.add_parser("json", help="write resolved palettes and notes as JSON")
    js.add_argument("themes", type=Path)
    js.add_argument("-o", "--out", type=Path, help="output file (default: stdout)")

    preview = sub.add_parser("preview", help="write an HTML page previewing every theme")
    preview.add_argument("themes", type=Path)
    preview.add_argument("-o", "--out", type=Path, default=Path("seedpalette-preview.html"))
    preview.add_argument("--title", default="Theme preview")
    return parser


def _load(path: Path) -> ThemeSet | None:
    try:
        return load(path)
    except (OSError, yaml.YAMLError, ValidationError) as exc:
        print(f"seedpalette: {path}: {exc}", file=sys.stderr)
        return None


def _emit(text: str, out: Path | None) -> None:
    if out is None:
        sys.stdout.write(text)
    else:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print(f"wrote {out}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    theme_set = _load(args.themes)
    if theme_set is None:
        return 1

    if args.command == "check":
        print(report(theme_set))
    elif args.command == "css":
        _emit(
            to_css(
                theme_set,
                mode_attr=args.mode_attr,
                theme_attr=args.theme_attr,
                default_mode=args.default_mode,
            ),
            args.out,
        )
    elif args.command == "json":
        _emit(to_json(theme_set), args.out)
    elif args.command == "preview":
        _emit(preview_html(theme_set, args.title), args.out)

    if not theme_set.ok:
        if args.command != "check":
            print(report(theme_set), file=sys.stderr)
        print("seedpalette: some colors fail contrast even after adjusting", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

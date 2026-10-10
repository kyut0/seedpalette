"""Command line: `seedpalette check | css | json | preview THEMES.yaml`, plus
`import-omarchy` and `export-omarchy` to convert to and from Omarchy desktop themes."""

import argparse
from pathlib import Path
import sys

from pydantic import ValidationError
import yaml

from seedpalette.omarchy import CREDIT, OmarchyError, export, import_themes, read, to_toml
from seedpalette.palette import ThemeSet, load, parse
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

    omarchy = sub.add_parser(
        "import-omarchy",
        help="turn one Omarchy theme (or a light/dark pair) into a theme file",
        description="Give one Omarchy theme directory or colors.toml to derive its other "
        "mode, or a light and a dark one to pair them.",
    )
    omarchy.add_argument("sources", type=Path, nargs="+", metavar="THEME")
    omarchy.add_argument("--name", help="theme name (default: the dark theme's directory)")
    omarchy.add_argument("--label", help="display name (default: from the name)")
    omarchy.add_argument(
        "--map", action="append", default=[], metavar="TOKEN=KEY",
        help="use an Omarchy color for a token, e.g. heading=yellow (repeatable)",
    )  # fmt: skip
    omarchy.add_argument("-o", "--out", type=Path, help="output file (default: stdout)")

    exporter = sub.add_parser(
        "export-omarchy",
        help="write one mode of a theme as an Omarchy theme (colors.toml)",
        description="Omarchy themes are one mode each, so export the dark and light modes "
        "separately. Terminal colors are taken from the theme's own colors where the hue "
        "fits, and made to match otherwise.",
    )
    exporter.add_argument("themes", type=Path)
    exporter.add_argument("--theme", help="theme name in the file (default: the first)")
    exporter.add_argument("--mode", choices=["dark", "light"], default="dark")
    exporter.add_argument(
        "-o", "--out", type=Path,
        help="theme directory to write colors.toml into "
        "(default: omarchy-NAME-theme, or omarchy-NAME-light-theme)",
    )  # fmt: skip
    return parser


def _export_omarchy(args: argparse.Namespace, theme_set: ThemeSet) -> int:
    names = [t.name for t in theme_set.themes]
    name = args.theme or names[0]
    if name not in names:
        print(f"seedpalette: no theme {name!r}; choose from {names}", file=sys.stderr)
        return 1
    theme = theme_set.themes[names.index(name)]
    exported = export(theme, args.mode)
    suffix = "-light" if args.mode == "light" else ""
    out_dir = args.out or Path(f"omarchy-{name}{suffix}-theme")
    header = (
        f"{theme.label} ({args.mode}), exported by seedpalette from {args.themes.name}.\n"
        "Terminal colors are matched to the theme's own colors where the hue fits."
    )
    _emit(to_toml(exported, header), out_dir / "colors.toml")
    print("\n".join(exported.notes), file=sys.stderr)
    return 0


def _import_omarchy(args: argparse.Namespace) -> int:
    try:
        mapping = dict(item.split("=", 1) for item in args.map)
    except ValueError:
        print("seedpalette: --map takes TOKEN=KEY, e.g. heading=yellow", file=sys.stderr)
        return 1
    try:
        sources = [read(path) for path in args.sources]
        name, spec = import_themes(sources, name=args.name, label=args.label, mapping=mapping)
        theme_set = parse({"themes": {name: spec}})
    except (OmarchyError, ValidationError) as exc:
        print(f"seedpalette: {exc}", file=sys.stderr)
        return 1
    header = (
        f"# Imported by `seedpalette import-omarchy` from {CREDIT}.\n"
        "# Run `seedpalette check` on this file to see the readability fixes.\n"
    )
    body = yaml.safe_dump({"themes": {name: spec}}, sort_keys=False, allow_unicode=True)
    _emit(header + body, args.out)
    print(report(theme_set), file=sys.stderr)
    return 0 if theme_set.ok else 1


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
    if args.command == "import-omarchy":
        return _import_omarchy(args)
    theme_set = _load(args.themes)
    if theme_set is None:
        return 1

    if args.command == "export-omarchy":
        if not theme_set.ok:
            print(report(theme_set), file=sys.stderr)
            return 1
        return _export_omarchy(args, theme_set)
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

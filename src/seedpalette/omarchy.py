"""Import Omarchy desktop themes (https://github.com/omacom/omarchy) as web themes.

An Omarchy theme is one mode, light or dark, described by a `colors.toml`. Its light
and dark variants are separate themes (e.g. `catppuccin-latte` and `catppuccin`), while
a seedpalette theme holds both. So the importer takes one or two Omarchy themes: given
both modes it pairs them, and given one it derives the other by flipping the neutrals'
lightness and keeping the accents, which seedpalette then makes readable as usual.
"""

from dataclasses import dataclass
from pathlib import Path
import tomllib
from typing import Any

from seedpalette.color import Oklch, from_oklch, parse_hex, to_oklch
from seedpalette.palette import CORE_TOKENS, Mode

# seedpalette token -> Omarchy colors.toml key. Override any with mapping=...
DEFAULT_MAPPING = {
    "bg": "background",
    "surface": "lighter_background",
    "border": "selection",
    "text": "foreground",
    "muted": "dark_foreground",  # the dim-text color in both light and dark themes
    "heading": "magenta",
    "link": "accent",
    "accent": "accent",
    "accent-2": "yellow",
}

# Neutrals for a derived mode: target OKLCH lightness, light then dark. Chroma is capped
# so the derived background stays calm while keeping a hint of the source's hue.
_NEUTRAL_LIGHTNESS = {
    "bg": (0.97, 0.20),
    "surface": (0.99, 0.25),
    "border": (0.88, 0.33),
    "text": (0.25, 0.92),
    "muted": (0.45, 0.72),
}
_NEUTRAL_MAX_CHROMA = 0.03

CREDIT = "Omarchy (MIT license), https://github.com/omacom/omarchy"


class OmarchyError(ValueError):
    """A colors.toml that can't be imported."""


@dataclass(frozen=True)
class OmarchyTheme:
    name: str  # the theme's directory name, e.g. "catppuccin-latte"
    mode: Mode
    colors: dict[str, str]  # Omarchy key -> lowercase #rrggbb


def read(path: Path) -> OmarchyTheme:
    """Read an Omarchy theme from its directory or its colors.toml."""
    file = path / "colors.toml" if path.is_dir() else path
    theme_dir = file.parent
    try:
        data = tomllib.loads(file.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise OmarchyError(f"{file}: {exc}") from exc

    # `mode = "light"`, or the older convention of an empty light.mode file.
    raw_mode = data.get("mode")
    if raw_mode is None:
        raw_mode = "light" if (theme_dir / "light.mode").exists() else "dark"
    if raw_mode not in ("light", "dark"):
        raise OmarchyError(f"{file}: mode must be light or dark, got {raw_mode!r}")
    mode: Mode = "light" if raw_mode == "light" else "dark"

    colors = {}
    for key, value in data.items():
        if isinstance(value, str) and value.startswith("#"):
            try:
                parse_hex(value)
            except ValueError as exc:
                raise OmarchyError(f"{file}: {key}: {exc}") from exc
            colors[key] = value.lower()
    name = theme_dir.name.removeprefix("omarchy-").removesuffix("-theme")
    return OmarchyTheme(name=name, mode=mode, colors=colors)


def seeds(theme: OmarchyTheme, mapping: dict[str, str] | None = None) -> dict[str, str]:
    """seedpalette seed colors for the theme's own mode."""
    mapping = {**DEFAULT_MAPPING, **(mapping or {})}
    unknown = sorted(set(mapping) - set(CORE_TOKENS))
    if unknown:
        raise OmarchyError(f"can't map to unknown token(s) {unknown}")
    out = {}
    for token, key in mapping.items():
        if key in theme.colors:
            out[token] = theme.colors[key]
        elif token in ("bg", "heading", "link", "accent"):
            raise OmarchyError(
                f"{theme.name}: no {key!r} color for required token {token!r}; "
                f"map it to another key, e.g. --map {token}=blue"
            )
    return out


def flip(seed_colors: dict[str, str], to: Mode) -> dict[str, str]:
    """Derive the other mode: neutrals move to the target mode's lightness (keeping a
    hint of their hue), accents are kept as they are. seedpalette then derives anything
    missing and fixes contrast."""
    out = {}
    for token, color in seed_colors.items():
        if token in _NEUTRAL_LIGHTNESS:
            light, dark = _NEUTRAL_LIGHTNESS[token]
            source = to_oklch(color)
            lightness = light if to == "light" else dark
            out[token] = from_oklch(Oklch(lightness, min(source.c, _NEUTRAL_MAX_CHROMA), source.h))
        else:
            out[token] = color
    return out


def import_themes(
    themes: list[OmarchyTheme],
    *,
    name: str | None = None,
    label: str | None = None,
    mapping: dict[str, str] | None = None,
) -> tuple[str, dict[str, Any]]:
    """Combine one or two Omarchy themes into a seedpalette theme spec.

    Returns (name, spec), where spec is a dict for the `themes:` section of a theme file.
    """
    if not 1 <= len(themes) <= 2:
        raise OmarchyError("give one Omarchy theme, or a light and a dark one to pair")
    by_mode = {t.mode: t for t in themes}
    if len(by_mode) != len(themes):
        raise OmarchyError(f"both themes are {themes[0].mode}; pair a light with a dark")

    modes: dict[Mode, dict[str, str]] = {}
    sources = []
    for mode, theme in by_mode.items():
        modes[mode] = seeds(theme, mapping)
        sources.append(f"{theme.name} ({mode})")
    pairs: tuple[tuple[Mode, Mode], ...] = (("light", "dark"), ("dark", "light"))
    for mode, other in pairs:
        if mode not in modes:
            modes[mode] = flip(modes[other], to=mode)
            sources.append(f"{mode} mode derived")

    name = name or by_mode.get("dark", themes[0]).name
    label = label or name.replace("-", " ").title()
    spec = {
        "label": label,
        "description": f"Imported from Omarchy: {', '.join(sources)}.",
        "light": modes["light"],
        "dark": modes["dark"],
    }
    return name, spec

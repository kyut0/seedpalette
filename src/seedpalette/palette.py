"""Theme files and palette derivation.

A theme file names one or more themes, each with a light and a dark mode. A mode needs
only four seed colors (bg, heading, link, accent); the rest are derived from them. Every
text color is then checked against WCAG contrast on both the page background and the
surface (card) color, and any that fail are shifted darker (light mode) or lighter (dark
mode) in OKLCH, keeping their hue, until they pass. Each change is recorded as a Note.

Projects can declare extra tokens of their own in `extra_tokens`, with a default (another
token's name or a hex color) and whether they are text that must pass contrast.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel, StringConstraints, model_validator
import yaml

from seedpalette.color import (
    TEXT_MIN,
    WHITE,
    Oklch,
    chroma,
    contrast_ratio,
    ensure_contrast,
    from_oklch,
    mix,
    to_oklch,
    worst_contrast,
)

HexColor = Annotated[str, StringConstraints(pattern=r"^#[0-9a-fA-F]{6}$")]
Name = Annotated[str, StringConstraints(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")]
Mode = Literal["light", "dark"]
MODES: tuple[Mode, Mode] = ("light", "dark")

# The tokens every palette defines, in output order.
CORE_TOKENS = (
    "bg",  # page background
    "surface",  # cards and raised panels
    "border",
    "text",  # body text
    "muted",  # secondary text
    "heading",
    "link",
    "accent",  # buttons, highlights, selection
    "accent-2",  # second accent; decorative, not contrast-checked
    "on-accent",  # text on accent-filled buttons
)
REQUIRED = ("bg", "heading", "link", "accent")
CORE_TEXT = ("text", "muted", "heading", "link")

# Maximum chroma (0 = gray, 1 = pure color) for large surfaces and running text, so vivid
# color is saved for headings, links, and accents. Exceeding these is a warning, not an
# error: a deliberately colorful background is a design choice.
CHROMA_MAX = {"bg": 0.15, "surface": 0.15, "text": 0.20, "muted": 0.25}


# ---- file format -------------------------------------------------------------------


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ExtraToken(_Model):
    """A project-specific token, e.g. `card-link: {text: true, default: link}`."""

    default: str  # another token's name, or a #rrggbb color
    text: bool = False  # used as text: must pass contrast on bg and surface

    @model_validator(mode="after")
    def _default_is_token_or_hex(self) -> "ExtraToken":
        is_hex = len(self.default) == 7 and self.default.startswith("#")
        if not is_hex and self.default not in CORE_TOKENS:
            raise ValueError(f"default {self.default!r} is neither #rrggbb nor a core token")
        return self


class ModeSpec(RootModel[dict[str, HexColor]]):
    """Seed colors for one mode: token name -> #rrggbb."""


class ThemeSpec(_Model):
    label: str
    description: str = ""
    light: ModeSpec
    dark: ModeSpec


class ThemeFile(_Model):
    extra_tokens: dict[Name, ExtraToken] = Field(default_factory=dict)
    themes: dict[Name, ThemeSpec]

    @model_validator(mode="after")
    def _check(self) -> "ThemeFile":
        if not self.themes:
            raise ValueError("defines no themes")
        clash = sorted(set(self.extra_tokens) & set(CORE_TOKENS))
        if clash:
            raise ValueError(f"extra_tokens {clash} reuse core token names")
        known = set(CORE_TOKENS) | set(self.extra_tokens)
        for name, theme in self.themes.items():
            for mode in MODES:
                given = getattr(theme, mode).root
                unknown = sorted(set(given) - known)
                if unknown:
                    raise ValueError(
                        f"{name} {mode}: unknown token(s) {unknown}; declare custom tokens "
                        "under extra_tokens"
                    )
                missing = [t for t in REQUIRED if t not in given]
                if missing:
                    raise ValueError(f"{name} {mode}: missing required token(s) {missing}")
        return self


# ---- resolved palettes -------------------------------------------------------------


@dataclass(frozen=True)
class Note:
    """One change made while deriving a palette, or a warning about it."""

    mode: Mode
    token: str
    message: str
    warning: bool = False


@dataclass(frozen=True)
class Check:
    mode: Mode
    token: str
    against: str
    ratio: float
    minimum: float

    @property
    def ok(self) -> bool:
        return self.ratio >= self.minimum


@dataclass(frozen=True)
class Theme:
    name: str
    label: str
    description: str
    light: dict[str, str]
    dark: dict[str, str]
    notes: list[Note] = field(default_factory=list)
    checks: list[Check] = field(default_factory=list)

    def palette(self, mode: Mode) -> dict[str, str]:
        return self.light if mode == "light" else self.dark

    @property
    def ok(self) -> bool:
        return all(c.ok for c in self.checks)


@dataclass(frozen=True)
class ThemeSet:
    themes: list[Theme]  # the first is the default
    tokens: tuple[str, ...]  # every token, core then extra, in output order

    @property
    def ok(self) -> bool:
        return all(t.ok for t in self.themes)


def _neutral(bg: str, lightness: float) -> str:
    """A near-gray at the given OKLCH lightness, tinted toward the background's hue."""
    base = to_oklch(bg)
    return from_oklch(Oklch(lightness, min(base.c, 0.025), base.h))


def _derive(
    spec: dict[str, str], mode: Mode, extras: dict[str, ExtraToken]
) -> tuple[dict[str, str], list[Note]]:
    dark = mode == "dark"
    bg = spec["bg"]
    defaults = {
        "surface": mix(bg, WHITE, 0.06 if dark else 0.45),
        "border": _neutral(bg, min(to_oklch(bg).l + 0.12, 1.0) if dark else to_oklch(bg).l - 0.1),
        "text": _neutral(bg, 0.93 if dark else 0.24),
        "muted": _neutral(bg, 0.74 if dark else 0.45),
        "accent-2": spec["accent"],
    }
    palette = {t: spec.get(t) or defaults.get(t, "") for t in CORE_TOKENS if t != "on-accent"}
    for name, extra in extras.items():
        default = extra.default if extra.default.startswith("#") else palette[extra.default]
        palette[name] = spec.get(name, default)

    notes: list[Note] = []
    surfaces = [palette["bg"], palette["surface"]]
    text_tokens = [*CORE_TEXT, *(n for n, e in extras.items() if e.text)]
    for token in text_tokens:
        given = palette[token]
        fixed = ensure_contrast(given, surfaces, TEXT_MIN, darker=not dark)
        if fixed != given:
            before, after = worst_contrast(given, surfaces), worst_contrast(fixed, surfaces)
            verb = "lightened" if dark else "darkened"
            source = "given" if token in spec else "derived"
            notes.append(
                Note(
                    mode,
                    token,
                    f"{source} {given} reads at {before:.2f}:1; {verb} to {fixed} ({after:.2f}:1)",
                )
            )
            palette[token] = fixed

    if "on-accent" in spec:
        palette["on-accent"] = spec["on-accent"]
    else:
        # Button text: whichever of white or the darkest page color reads better.
        darkest = palette["bg"] if dark else palette["text"]
        palette["on-accent"] = max(
            (WHITE, darkest), key=lambda c: contrast_ratio(c, palette["accent"])
        )

    for token, limit in CHROMA_MAX.items():
        value = chroma(palette[token])
        if value > limit:
            notes.append(
                Note(
                    mode,
                    token,
                    f"{palette[token]} is vivid for a {token} color "
                    f"(chroma {value:.2f}, calm limit {limit})",
                    warning=True,
                )
            )
    return palette, notes


def _checks(palette: dict[str, str], mode: Mode, text_tokens: list[str]) -> list[Check]:
    pairs = [(t, s, TEXT_MIN) for t in text_tokens for s in ("bg", "surface")]
    pairs.append(("on-accent", "accent", TEXT_MIN))
    return [
        Check(mode, fg, bg, contrast_ratio(palette[fg], palette[bg]), minimum)
        for fg, bg, minimum in pairs
    ]


def resolve(name: str, spec: ThemeSpec, extras: dict[str, ExtraToken] | None = None) -> Theme:
    """Derive a theme's full light and dark palettes from its seed colors."""
    extras = extras or {}
    text_tokens = [*CORE_TEXT, *(n for n, e in extras.items() if e.text)]
    light, light_notes = _derive(spec.light.root, "light", extras)
    dark, dark_notes = _derive(spec.dark.root, "dark", extras)
    return Theme(
        name=name,
        label=spec.label,
        description=spec.description,
        light=light,
        dark=dark,
        notes=light_notes + dark_notes,
        checks=_checks(light, "light", text_tokens) + _checks(dark, "dark", text_tokens),
    )


def parse(data: object) -> ThemeSet:
    """Validate and resolve an already-loaded theme file (e.g. a dict from YAML/JSON)."""
    spec = ThemeFile.model_validate(data)
    return ThemeSet(
        themes=[resolve(n, t, spec.extra_tokens) for n, t in spec.themes.items()],
        tokens=(*CORE_TOKENS, *spec.extra_tokens),
    )


def load(path: Path) -> ThemeSet:
    """Read, validate, and resolve a YAML theme file. The first theme is the default."""
    return parse(yaml.safe_load(path.read_text(encoding="utf-8")))

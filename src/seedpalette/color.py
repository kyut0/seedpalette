"""Color math: WCAG 2 contrast, and lightness changes in OKLCH that keep a color's hue.

Darkening a color by blending it with black (in sRGB) also dulls and shifts it: a teal
drifts toward gray-green. Instead, colors here are adjusted in OKLCH (Björn Ottosson's
perceptual color space), changing only lightness so the teal stays the same teal. When
a lightness has no in-gamut color at the original chroma, chroma is reduced just enough
to fit.
"""

from dataclasses import dataclass
import math
import re

_HEX = re.compile(r"^#([0-9a-fA-F]{6})$")

# WCAG 2 AA minimums.
TEXT_MIN = 4.5  # normal-size text
UI_MIN = 3.0  # large text, focus rings, borders that carry meaning

WHITE = "#ffffff"
BLACK = "#000000"


def parse_hex(color: str) -> tuple[int, int, int]:
    match = _HEX.match(color)
    if match is None:
        raise ValueError(f"expected a #rrggbb color, got {color!r}")
    digits = match.group(1)
    return int(digits[0:2], 16), int(digits[2:4], 16), int(digits[4:6], 16)


def to_hex(rgb: tuple[float, float, float]) -> str:
    """0-1 sRGB channels to #rrggbb, clamping anything slightly out of range."""
    return "#" + "".join(f"{round(min(max(c, 0.0), 1.0) * 255):02x}" for c in rgb)


def _to_linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _from_linear(c: float) -> float:
    return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055


def relative_luminance(color: str) -> float:
    r, g, b = (_to_linear(c / 255) for c in parse_hex(color))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(a: str, b: str) -> float:
    """WCAG contrast ratio between two colors, from 1 (identical) to 21 (black on white)."""
    hi, lo = sorted((relative_luminance(a), relative_luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def chroma(color: str) -> float:
    """How far a color is from gray: max channel minus min channel, 0 (gray) to 1.

    Unlike HSL saturation, this stays low for very dark colors such as navy, which read
    as calm even though HSL calls them highly saturated.
    """
    channels = [c / 255 for c in parse_hex(color)]
    return max(channels) - min(channels)


def mix(a: str, b: str, t: float) -> str:
    """Blend a toward b in sRGB: t=0 is a, t=1 is b."""
    (r1, g1, b1), (r2, g2, b2) = parse_hex(a), parse_hex(b)
    return to_hex(
        ((r1 + (r2 - r1) * t) / 255, (g1 + (g2 - g1) * t) / 255, (b1 + (b2 - b1) * t) / 255)
    )


# ---- OKLCH -------------------------------------------------------------------------


@dataclass(frozen=True)
class Oklch:
    l: float  # lightness, 0-1  # noqa: E741
    c: float  # chroma, 0 to about 0.4
    h: float  # hue in degrees


def to_oklch(color: str) -> Oklch:
    r, g, b = (_to_linear(c / 255) for c in parse_hex(color))
    l_ = math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b)
    m_ = math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b)
    s_ = math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b)
    lightness = 0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_
    a = 1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_
    bb = 0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_
    return Oklch(lightness, math.hypot(a, bb), math.degrees(math.atan2(bb, a)) % 360)


def _oklch_to_linear(color: Oklch) -> tuple[float, float, float]:
    a = color.c * math.cos(math.radians(color.h))
    b = color.c * math.sin(math.radians(color.h))
    l_ = (color.l + 0.3963377774 * a + 0.2158037573 * b) ** 3
    m_ = (color.l - 0.1055613458 * a - 0.0638541728 * b) ** 3
    s_ = (color.l - 0.0894841775 * a - 1.2914855480 * b) ** 3
    return (
        4.0767416621 * l_ - 3.3077115913 * m_ + 0.2309699292 * s_,
        -1.2684380046 * l_ + 2.6097574011 * m_ - 0.3413193965 * s_,
        -0.0041960863 * l_ - 0.7034186147 * m_ + 1.7076147010 * s_,
    )


def _in_gamut(rgb: tuple[float, float, float]) -> bool:
    return all(-1e-6 <= c <= 1 + 1e-6 for c in rgb)


def from_oklch(color: Oklch) -> str:
    """OKLCH to #rrggbb, lowering chroma (keeping lightness and hue) to fit in sRGB."""
    lo, hi = 0.0, color.c
    if not _in_gamut(_oklch_to_linear(color)):
        for _ in range(30):  # bisect on chroma
            mid = (lo + hi) / 2
            if _in_gamut(_oklch_to_linear(Oklch(color.l, mid, color.h))):
                lo = mid
            else:
                hi = mid
        color = Oklch(color.l, lo, color.h)
    r, g, b = (_from_linear(min(max(c, 0.0), 1.0)) for c in _oklch_to_linear(color))
    return to_hex((r, g, b))


def with_lightness(color: str, lightness: float) -> str:
    """The same hue and chroma at a new OKLCH lightness (chroma reduced if needed)."""
    base = to_oklch(color)
    return from_oklch(Oklch(min(max(lightness, 0.0), 1.0), base.c, base.h))


def worst_contrast(color: str, backgrounds: list[str]) -> float:
    return min(contrast_ratio(color, bg) for bg in backgrounds)


def ensure_contrast(color: str, backgrounds: list[str], minimum: float, darker: bool) -> str:
    """Shift color's OKLCH lightness (darker or lighter) in small steps until it reaches
    minimum contrast against every background. Hue is kept; returns the first passing
    color, or pure black/white if even that is not enough."""
    if worst_contrast(color, backgrounds) >= minimum:
        return color
    start = to_oklch(color).l
    for step in range(1, 201):
        target = start - step * 0.005 if darker else start + step * 0.005
        candidate = with_lightness(color, target)
        if worst_contrast(candidate, backgrounds) >= minimum:
            return candidate
        if not 0.0 <= target <= 1.0:
            break
    return BLACK if darker else WHITE

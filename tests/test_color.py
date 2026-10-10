import pytest

from seedpalette.color import (
    TEXT_MIN,
    chroma,
    contrast_ratio,
    ensure_contrast,
    from_oklch,
    mix,
    parse_hex,
    to_oklch,
    with_lightness,
)


def test_contrast_ratio_known_values() -> None:
    assert contrast_ratio("#000000", "#ffffff") == pytest.approx(21.0)
    assert contrast_ratio("#777777", "#777777") == pytest.approx(1.0)


def test_bad_hex_is_rejected() -> None:
    with pytest.raises(ValueError, match="#rrggbb"):
        parse_hex("teal")


def test_chroma_known_values() -> None:
    assert chroma("#808080") == 0
    assert chroma("#ff0000") == 1


def test_mix_endpoints() -> None:
    assert mix("#000000", "#ffffff", 0) == "#000000"
    assert mix("#000000", "#ffffff", 1) == "#ffffff"
    assert mix("#000000", "#ffffff", 0.5) == "#808080"


@pytest.mark.parametrize("color", ["#000000", "#ffffff", "#059ea1", "#d80aad", "#ff8800"])
def test_oklch_round_trips(color: str) -> None:
    assert from_oklch(to_oklch(color)) == color


def test_oklch_white_is_full_lightness() -> None:
    white = to_oklch("#ffffff")
    assert white.l == pytest.approx(1.0, abs=1e-6)
    assert white.c == pytest.approx(0.0, abs=1e-6)


def test_with_lightness_keeps_hue() -> None:
    teal = to_oklch("#059ea1")
    darker = to_oklch(with_lightness("#059ea1", teal.l - 0.15))
    assert darker.l < teal.l
    assert darker.h == pytest.approx(teal.h, abs=2.0)


def test_out_of_gamut_lightness_lowers_chroma_instead_of_clipping() -> None:
    # Pure cyan is near the edge of sRGB; at high lightness it can't keep its chroma.
    result = with_lightness("#00f7ff", 0.98)
    assert to_oklch(result).l == pytest.approx(0.98, abs=0.01)


def test_ensure_contrast_keeps_passing_colors() -> None:
    assert ensure_contrast("#000000", ["#ffffff"], TEXT_MIN, darker=True) == "#000000"


@pytest.mark.parametrize(
    ("color", "bg", "darker"),
    [("#059ea1", "#e3eddc", True), ("#700808", "#001c07", False)],
)
def test_ensure_contrast_reaches_minimum(color: str, bg: str, darker: bool) -> None:
    fixed = ensure_contrast(color, [bg], TEXT_MIN, darker=darker)
    assert contrast_ratio(fixed, bg) >= TEXT_MIN


def test_ensure_contrast_falls_back_to_black_or_white() -> None:
    # Nothing at this hue reaches 21:1 on mid-gray, so it ends at pure black.
    assert ensure_contrast("#808080", ["#808080"], 21.0, darker=True) == "#000000"

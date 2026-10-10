from pathlib import Path
from typing import Any

from pydantic import ValidationError
import pytest

from seedpalette.color import TEXT_MIN, contrast_ratio, to_oklch
from seedpalette.palette import CORE_TOKENS, load, parse

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "themes.yaml"
SEEDS = {"heading": "#700808", "link": "#059ea1", "accent": "#d80aad"}


def _file(light: dict[str, str], dark: dict[str, str], **extra: Any) -> dict[str, Any]:
    return {"themes": {"t": {"label": "T", "light": light, "dark": dark}}, **extra}


def _theme(
    light_bg: str = "#e3eddc", dark_bg: str = "#001c07", extra: dict[str, Any] | None = None
) -> Any:
    data = _file({"bg": light_bg, **SEEDS}, {"bg": dark_bg, **SEEDS}, **(extra or {}))
    return parse(data).themes[0]


def test_example_file_passes() -> None:
    theme_set = load(EXAMPLE)
    assert theme_set.ok
    assert [t.name for t in theme_set.themes] == ["ember", "sage"]


def test_every_token_is_defined_in_both_modes() -> None:
    theme = _theme()
    for mode in ("light", "dark"):
        assert set(theme.palette(mode)) == set(CORE_TOKENS)


def test_derived_palette_passes_contrast() -> None:
    assert _theme().ok


def test_faint_text_is_darkened_in_light_mode_with_a_note() -> None:
    theme = _theme()
    assert theme.light["link"] != SEEDS["link"]
    note = next(n for n in theme.notes if n.mode == "light" and n.token == "link")
    assert "darkened" in note.message
    assert not note.warning


def test_adjustment_keeps_the_hue() -> None:
    theme = _theme()
    assert to_oklch(theme.light["link"]).h == pytest.approx(to_oklch(SEEDS["link"]).h, abs=3)


def test_dark_mode_lightens_instead() -> None:
    theme = _theme(light_bg="#f8f1e3")
    note = next(n for n in theme.notes if n.mode == "dark" and n.token == "heading")
    assert "lightened" in note.message


def test_vivid_background_is_a_warning_not_a_failure() -> None:
    theme = _theme(light_bg="#9dcca8")
    assert theme.ok
    assert any(n.warning and n.token == "bg" for n in theme.notes)


def test_on_accent_picks_the_readable_option() -> None:
    theme = _theme()
    for mode in ("light", "dark"):
        p = theme.palette(mode)
        assert contrast_ratio(p["on-accent"], p["accent"]) >= TEXT_MIN


def test_given_colors_that_pass_are_kept() -> None:
    theme = _theme()
    assert theme.dark["accent"] == SEEDS["accent"]
    assert theme.dark["bg"] == "#001c07"


def test_extra_tokens_default_and_get_checked() -> None:
    extras = {
        "extra_tokens": {
            "card-link": {"default": "link", "text": True},
            "logo": {"default": "#ffffff"},
        }
    }
    theme = _theme(extra=extras)
    assert theme.dark["logo"] == "#ffffff"
    assert theme.light["card-link"] == theme.light["link"]  # default, then adjusted
    assert any(c.token == "card-link" for c in theme.checks)


def test_unknown_token_is_rejected() -> None:
    with pytest.raises(ValidationError, match="unknown token"):
        parse(_file({"bg": "#ffffff", "sparkle": "#ff00ff", **SEEDS}, {"bg": "#000000", **SEEDS}))


def test_missing_required_token_is_rejected() -> None:
    with pytest.raises(ValidationError, match="missing required"):
        parse(_file({"bg": "#ffffff"}, {"bg": "#000000", **SEEDS}))


def test_bad_hex_is_rejected() -> None:
    with pytest.raises(ValidationError):
        parse(_file({"bg": "white", **SEEDS}, {"bg": "#000000", **SEEDS}))


def test_extra_token_cannot_shadow_a_core_token() -> None:
    with pytest.raises(ValidationError, match="reuse core token"):
        _theme(extra={"extra_tokens": {"link": {"default": "#000000"}}})


def test_extra_token_default_must_be_hex_or_core() -> None:
    with pytest.raises(ValidationError, match="neither"):
        _theme(extra={"extra_tokens": {"x": {"default": "nope"}}})


def test_empty_file_is_rejected() -> None:
    with pytest.raises(ValidationError, match="no themes"):
        parse({"themes": {}})


def test_on_accent_falls_back_to_black_for_mid_tone_accents() -> None:
    light = {"bg": "#e1e2e7", "text": "#3760bf", **SEEDS, "accent": "#2e7de9"}
    theme = parse(_file(light, {"bg": "#001c07", **SEEDS})).themes[0]
    assert theme.light["on-accent"] == "#000000"
    assert theme.ok

from pathlib import Path

import pytest
import yaml

from seedpalette.cli import main
from seedpalette.color import TEXT_MIN, contrast_ratio, to_oklch
from seedpalette.omarchy import (
    ANSI_HUES,
    OmarchyError,
    export,
    flip,
    import_themes,
    read,
    seeds,
    to_toml,
)
from seedpalette.palette import Mode, Theme, load, parse

# Small made-up themes in Omarchy's colors.toml format (not copies of real ones).
DARK = """\
mode = "dark"
accent = "#7aa2f7"
selection = "#283457"
muted = "#414868"
background = "#1a1b26"
lighter_background = "#24283b"
foreground = "#c0caf5"
dark_foreground = "#565f89"
magenta = "#bb9af7"
yellow = "#e0af68"
blue = "#7aa2f7"
"""

LIGHT = """\
mode = "light"
accent = "#2E7DE9"
selection = "#c4c8da"
background = "#E1E2E7"
lighter_background = "#d0d5e3"
foreground = "#3760BF"
dark_foreground = "#8990b3"
magenta = "#9854f1"
yellow = "#8c6c3e"
"""


def _theme(tmp_path: Path, name: str, body: str) -> Path:
    path = tmp_path / name
    path.mkdir()
    (path / "colors.toml").write_text(body)
    return path


def test_read_takes_a_directory_or_file(tmp_path: Path) -> None:
    path = _theme(tmp_path, "omarchy-night-theme", DARK)
    from_dir, from_file = read(path), read(path / "colors.toml")
    assert from_dir == from_file
    assert from_dir.name == "night"  # omarchy-/-theme stripped like Omarchy's installer
    assert from_dir.mode == "dark"


def test_read_lowercases_hex(tmp_path: Path) -> None:
    theme = read(_theme(tmp_path, "day", LIGHT))
    assert theme.colors["accent"] == "#2e7de9"


def test_light_mode_file_marks_light(tmp_path: Path) -> None:
    path = _theme(tmp_path, "old", DARK.replace('mode = "dark"\n', ""))
    (path / "light.mode").touch()
    assert read(path).mode == "light"


def test_mode_defaults_to_dark(tmp_path: Path) -> None:
    assert read(_theme(tmp_path, "x", DARK.replace('mode = "dark"\n', ""))).mode == "dark"


def test_bad_mode_and_bad_hex_are_rejected(tmp_path: Path) -> None:
    with pytest.raises(OmarchyError, match="mode must be"):
        read(_theme(tmp_path, "a", DARK.replace('"dark"', '"dusk"')))
    with pytest.raises(OmarchyError, match="#rrggbb"):
        read(_theme(tmp_path, "b", DARK + 'red = "#12"\n'))


def test_seeds_map_omarchy_keys(tmp_path: Path) -> None:
    out = seeds(read(_theme(tmp_path, "n", DARK)))
    assert out["bg"] == "#1a1b26"
    assert out["text"] == "#c0caf5"
    assert out["muted"] == "#565f89"
    assert out["heading"] == "#bb9af7"
    assert out["link"] == out["accent"] == "#7aa2f7"


def test_mapping_overrides_and_missing_required_key(tmp_path: Path) -> None:
    theme = read(_theme(tmp_path, "n", DARK))
    assert seeds(theme, {"heading": "yellow"})["heading"] == "#e0af68"
    with pytest.raises(OmarchyError, match="--map heading="):
        seeds(theme, {"heading": "orange"})
    with pytest.raises(OmarchyError, match="unknown token"):
        seeds(theme, {"sparkle": "blue"})


def test_flip_moves_neutrals_and_keeps_accents() -> None:
    dark = {"bg": "#1a1b26", "text": "#c0caf5", "link": "#7aa2f7"}
    light = flip(dark, to="light")
    assert to_oklch(light["bg"]).l > 0.9
    assert to_oklch(light["text"]).l < 0.4
    assert light["link"] == dark["link"]


def test_pairing_light_and_dark(tmp_path: Path) -> None:
    pair = [read(_theme(tmp_path, "night", DARK)), read(_theme(tmp_path, "day", LIGHT))]
    name, spec = import_themes(pair)
    assert name == "night"  # named after the dark theme
    assert spec["light"]["bg"] == "#e1e2e7"
    assert spec["dark"]["bg"] == "#1a1b26"
    assert "derived" not in spec["description"]
    assert parse({"themes": {name: spec}}).ok


def test_single_theme_derives_the_other_mode(tmp_path: Path) -> None:
    name, spec = import_themes([read(_theme(tmp_path, "night", DARK))], label="Night Owl")
    assert spec["label"] == "Night Owl"
    assert "light mode derived" in spec["description"]
    assert parse({"themes": {name: spec}}).ok


def test_two_of_the_same_mode_is_rejected(tmp_path: Path) -> None:
    two = [read(_theme(tmp_path, "a", DARK)), read(_theme(tmp_path, "b", DARK))]
    with pytest.raises(OmarchyError, match="both themes are dark"):
        import_themes(two)


def test_cli_writes_a_valid_theme_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    night, out = _theme(tmp_path, "night", DARK), tmp_path / "themes.yaml"
    assert main(["import-omarchy", str(night), "--map", "heading=yellow", "-o", str(out)]) == 0
    text = out.read_text()
    assert text.startswith("# Imported by `seedpalette import-omarchy` from Omarchy (MIT")
    assert yaml.safe_load(text)["themes"]["night"]["dark"]["heading"] == "#e0af68"
    assert "night (default): Night [ok]" in capsys.readouterr().err
    assert main(["check", str(out)]) == 0


def test_cli_rejects_bad_map(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    night = _theme(tmp_path, "night", DARK)
    assert main(["import-omarchy", str(night), "--map", "heading"]) == 1
    assert "TOKEN=KEY" in capsys.readouterr().err


# ---- export ------------------------------------------------------------------------

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "themes.yaml"


def _sage() -> Theme:
    return next(t for t in load(EXAMPLE).themes if t.name == "sage")


@pytest.mark.parametrize("mode", ["dark", "light"])
def test_export_terminal_colors_are_readable(mode: Mode) -> None:
    exported = export(_sage(), mode)
    bg = exported.colors["background"]
    for slot in [*ANSI_HUES, *(f"bright_{s}" for s in ("red", "green", "blue"))]:
        assert contrast_ratio(exported.colors[slot], bg) >= TEXT_MIN, slot


def test_export_reuses_theme_colors_that_fit_a_hue() -> None:
    exported = export(_sage(), "dark")
    sage = _sage().dark
    assert exported.colors["cyan"] == sage["link"]  # #00f7ff
    assert exported.colors["orange"] == sage["accent-2"]
    assert any("made at this hue" in n for n in exported.notes)


def test_made_colors_land_near_their_hue() -> None:
    exported = export(_sage(), "dark")
    for slot, hue in ANSI_HUES.items():
        h = to_oklch(exported.colors[slot]).h
        assert min(abs(h - hue) % 360, 360 - abs(h - hue) % 360) <= 30, slot


def test_export_round_trips_through_import(tmp_path: Path) -> None:
    exported = export(_sage(), "dark")
    theme_dir = tmp_path / "omarchy-sage-theme"
    theme_dir.mkdir()
    (theme_dir / "colors.toml").write_text(to_toml(exported, "header"))
    back = read(theme_dir)
    assert back.name == "sage"
    assert back.mode == "dark"
    assert back.colors["background"] == _sage().dark["bg"]
    assert back.colors["foreground"] == _sage().dark["text"]


def test_cli_exports_both_modes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    dark, light = tmp_path / "dark", tmp_path / "light"
    args = ["export-omarchy", str(EXAMPLE), "--theme", "sage"]
    assert main([*args, "-o", str(dark)]) == 0
    assert main([*args, "--mode", "light", "-o", str(light)]) == 0
    assert read(dark).mode == "dark"
    assert read(light).mode == "light"
    assert (dark / "colors.toml").read_text().startswith("# Sage (dark), exported by seedpalette")
    assert "made at this hue" in capsys.readouterr().err


def test_cli_rejects_unknown_theme(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["export-omarchy", str(EXAMPLE), "--theme", "nope"]) == 1
    assert "choose from" in capsys.readouterr().err

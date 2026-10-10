import json
from pathlib import Path

import pytest

from seedpalette.cli import main
from seedpalette.palette import ThemeSet, load
from seedpalette.render import preview_html, report, to_css, to_json

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "themes.yaml"


@pytest.fixture(scope="module")
def theme_set() -> ThemeSet:
    return load(EXAMPLE)


def test_css_default_on_root_others_behind_attribute(theme_set: ThemeSet) -> None:
    css = to_css(theme_set)
    assert css.count(":root {") == 1
    assert ':root[data-theme="light"] {' in css
    assert ':root[data-palette="sage"] {' in css
    assert ':root[data-palette="sage"][data-theme="light"] {' in css
    assert f"--bg: {theme_set.themes[0].dark['bg']};" in css
    assert "--card-link:" in css  # extra tokens are emitted too


def test_css_attributes_and_default_mode_are_configurable(theme_set: ThemeSet) -> None:
    css = to_css(theme_set, mode_attr="data-mode", theme_attr="data-scheme", default_mode="light")
    assert f"--bg: {theme_set.themes[0].light['bg']};" in css.split("}")[0]
    assert ':root[data-mode="dark"] {' in css
    assert ':root[data-scheme="sage"] {' in css


def test_json_lists_palettes_and_notes(theme_set: ThemeSet) -> None:
    data = json.loads(to_json(theme_set))
    assert data["default"] == "ember"
    sage = data["themes"]["sage"]
    assert sage["light"]["bg"] == "#e3eddc"
    assert any(n["token"] == "link" for n in sage["notes"])


def test_report_explains_adjustments(theme_set: ThemeSet) -> None:
    text = report(theme_set)
    assert "ember (default): Ember [ok]" in text
    assert "darkened to" in text


def test_preview_shows_every_theme(theme_set: ThemeSet) -> None:
    html = preview_html(theme_set, title="My themes")
    assert "<title>My themes</title>" in html
    assert "Ember" in html and "Sage" in html


def test_cli_check_and_outputs(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["check", str(EXAMPLE)]) == 0
    assert "sage: Sage [ok]" in capsys.readouterr().out
    css, preview = tmp_path / "themes.css", tmp_path / "preview.html"
    assert main(["css", str(EXAMPLE), "-o", str(css)]) == 0
    assert main(["preview", str(EXAMPLE), "-o", str(preview)]) == 0
    assert ":root {" in css.read_text()
    assert "Sage" in preview.read_text()


def test_cli_reports_invalid_files(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("themes: {}\n")
    assert main(["check", str(bad)]) == 1
    assert "no themes" in capsys.readouterr().err

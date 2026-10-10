"""seedpalette: grow a few seed colors into full, readable light and dark themes.

from pathlib import Path
import seedpalette

themes = seedpalette.load(Path("themes.yaml"))
print(seedpalette.report(themes))
Path("themes.css").write_text(seedpalette.to_css(themes))
"""

from seedpalette.palette import (
    CORE_TOKENS,
    Check,
    Note,
    Theme,
    ThemeSet,
    load,
    parse,
    resolve,
)
from seedpalette.render import preview_html, report, to_css, to_json

__all__ = [
    "CORE_TOKENS",
    "Check",
    "Note",
    "Theme",
    "ThemeSet",
    "load",
    "parse",
    "preview_html",
    "report",
    "resolve",
    "to_css",
    "to_json",
]
__version__ = "0.1.0"

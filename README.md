# seedpalette

Grow a few seed colors into full, readable light and dark website themes, with a report
of every color it had to fix.

You pick the colors you care about (a background, a heading color, a link color, an
accent). seedpalette fills in the rest (surfaces, borders, body and muted text, button
text), checks every text color against WCAG AA contrast on both the page and card
backgrounds, and nudges any that fail darker or lighter until they pass. It keeps their
hue while doing it, then tells you exactly what it changed.

```console
$ seedpalette check examples/themes.yaml
ember (default): Ember [ok]
  every color passes as given
sage: Sage [ok]
  light adjusted --link: given #059ea1 reads at 2.72:1; darkened to #007679 (4.50:1)
  light adjusted --card-link: given #d80aad reads at 3.81:1; darkened to #c3009c (4.58:1)
```

That teal looked great on its own, but on a pale sage background it reads at 2.7:1,
well under the 4.5:1 that body-size text needs. seedpalette deepened it just enough
and left everything else alone.

## Why

Picking a palette is easy. Keeping it readable is the hard part: a color that works on
dark backgrounds often fails on light ones, and every new theme is a dozen more pairs to
check by hand. seedpalette treats a theme like data. The input is validated, the
derivation is deterministic, the output is generated, and there's an audit trail of
every adjustment.

## Install

Requires Python 3.13+.

```bash
pipx install git+https://github.com/kyut0/seedpalette
```

## Usage

Write a theme file. Each theme has a light and a dark mode; only `bg`, `heading`,
`link`, and `accent` are required:

```yaml
themes:
  sage:
    label: Sage
    light:
      bg: "#e3eddc"
      heading: "#700808"
      link: "#059ea1"
      accent: "#d80aad"
    dark:
      bg: "#001c07"
      heading: "#ff8800"
      link: "#00f7ff"
      accent: "#d80aad"
```

Then:

```bash
seedpalette check themes.yaml              # report adjustments and warnings
seedpalette css themes.yaml -o themes.css  # CSS custom properties
seedpalette json themes.yaml -o themes.json
seedpalette preview themes.yaml            # seedpalette-preview.html: every theme, both modes
```

Every command exits non-zero if a theme can't be made readable, so `seedpalette check`
works as a CI gate.

### Tokens

| Token | Role | Checked as text |
| --- | --- | --- |
| `bg` | page background (required) | |
| `surface` | cards, raised panels | |
| `border` | borders and dividers | |
| `text` | body text | yes |
| `muted` | secondary text | yes |
| `heading` | headings (required) | yes |
| `link` | links (required) | yes |
| `accent` | buttons, highlights (required) | |
| `accent-2` | second accent, decorative | |
| `on-accent` | text on accent-filled buttons | yes, on `accent` |

Text tokens must reach 4.5:1 on both `bg` and `surface`. Large surfaces and body text
that are very saturated produce a warning (not a failure), since a vivid background is
sometimes the point.

Add your own tokens under `extra_tokens`, with a default (a core token or a hex color)
and whether they're text:

```yaml
extra_tokens:
  card-link: {default: link, text: true}
  logo-bg: {default: "#ffffff"}
```

### Using the CSS

The first theme's dark palette sits on bare `:root`, so a page with no attributes still
gets colors. Set attributes on `<html>` to switch:

```html
<html data-theme="light" data-palette="sage">
```

```css
body { background: var(--bg); color: var(--text); }
a { color: var(--link); }
```

Both attribute names and the default mode are configurable
(`--mode-attr`, `--theme-attr`, `--default-mode light`).

### From Python

```python
from pathlib import Path
import seedpalette

themes = seedpalette.load(Path("themes.yaml"))
print(seedpalette.report(themes))
Path("themes.css").write_text(seedpalette.to_css(themes))
```

## Import Omarchy themes

[Omarchy](https://github.com/omacom/omarchy) themes are desktop color schemes, one mode
each, in a `colors.toml` (built-ins live in `/usr/share/omarchy/themes`, your own in
`~/.config/omarchy/themes`). `import-omarchy` turns them into web themes: give it a light
and a dark theme to pair them, or one theme to derive its other mode.

```bash
# pair Catppuccin (dark) with Catppuccin Latte (light)
seedpalette import-omarchy /usr/share/omarchy/themes/catppuccin \
  /usr/share/omarchy/themes/catppuccin-latte -o catppuccin.yaml

# one theme: the light mode is derived
seedpalette import-omarchy /usr/share/omarchy/themes/everforest -o everforest.yaml
```

Terminal palettes are tuned for big, bright text, so their dim colors often fail on a
web page. The report shows what was fixed:

```console
everforest (default): Everforest [ok]
  light adjusted --heading: given #d699b6 reads at 2.12:1; darkened to #975f7a (4.56:1)
  light adjusted --link: given #7fbbb3 reads at 2.00:1; darkened to #3f7a73 (4.55:1)
  dark  adjusted --muted: given #4f585e reads at 1.49:1; lightened to #9fa9b0 (4.52:1)
```

Colors map as `background` → `bg`, `lighter_background` → `surface`, `selection` →
`border`, `foreground` → `text`, `dark_foreground` → `muted`, `magenta` → `heading`,
`accent` → `link` and `accent`, `yellow` → `accent-2`. Change any with
`--map heading=yellow`. Omarchy's themes are MIT-licensed; the generated file credits
them in its header.

## Export to Omarchy

Going the other way, `export-omarchy` writes one mode of a theme as an Omarchy theme, so
your website's colors can be your desktop's too. Omarchy themes are one mode each, so
export dark and light separately:

```bash
seedpalette export-omarchy themes.yaml --theme sage                # omarchy-sage-theme/
seedpalette export-omarchy themes.yaml --theme sage --mode light   # omarchy-sage-light-theme/
```

A desktop theme also needs a terminal palette (red, green, yellow, ...), which web
themes don't have. Each slot reuses one of the theme's own colors when its hue is
close, and is otherwise made at that hue with the lightness and saturation of the
theme's accents. Every terminal color is checked for contrast on the background, and the
output says where each came from:

```console
red      #ff7367  made at this hue
orange   #ff8800  from --accent-2
cyan     #00f7ff  from --link
magenta  #e525b8  from --accent, lightened from #d80aad for contrast
```

To share it, push the folder to its own repo named `omarchy-NAME-theme`; anyone can
then install it with `omarchy theme install <git-url>`.

## How adjustments work

Colors are adjusted in [OKLCH](https://bottosson.github.io/posts/oklab/), a perceptual
color space, by changing only lightness, so a darkened teal stays teal instead of
drifting toward gray-green as it would when mixed with black. If a lightness has no
in-gamut color at the original chroma, chroma is lowered just enough to fit. Missing
neutrals (text, muted, border) are near-grays tinted toward the background's hue.

## Development

```bash
make install   # poetry install + pre-commit hooks
make check     # lint, type-check, test (same as CI)
```

## License

MIT

# Themes: style tokens (step 1)

A theme changes the surface only: never a panel's place, never what anything does.

**Colours** are roles (`SbTheme.PALETTES`: BG, PANEL, BORDER, MINT, WARM, TEXT…); each built-in theme
(Morning, Focus, Evening, Forest) swaps them, with its music and sounds.

**Style tokens** (`SbTheme.STYLE`, defaults in `SbTheme.STYLE_DEFAULTS`) are everything visual that is not a
colour. The defaults are the app's own look, so leaving them alone changes nothing.

| Token | Default | What it changes |
|---|---|---|
| `font_sans` | Segoe UI Variable Text, Segoe UI, Inter… | the interface font (a list: the first one installed wins) |
| `font_mono` | Cascadia Mono, Consolas, JetBrains Mono… | code and logs |
| `font_scale` | 1.0 | every text size |
| `radius_scale` | 1.0 | every corner (0 = square) |
| `border_scale` | 1.0 | every border (0 = none) |
| `shadow` | 1.0 | the floating panels' shadow (0 = flat) |
| `density` | 1.0 | inner padding of boxes and buttons |
| `graph_shape` | `circle` | nodes and places: `circle` or `square` |
| `graph_links` | `solid` | links between items: `solid` or `dashed` |
| `graph_glow` | 1.0 | halos, rings and the breathing glow (0 = none) |
| `graph_background` | `stars` | `stars`, `plain` or `grid` |

Everything goes through them: `SbTheme.box()` (corners, borders, padding), `SbTheme.build()` (text sizes, fonts),
`SbTheme.fs()` for a text size set in a screen, `SbTheme.r()` / `SbTheme.bw()` for a corner or a border drawn by
hand, and the graph's `_disc()` / `_ring()` for its shapes. A new screen uses these, never a raw number.

`SbTheme.set_style(tokens)` starts from the defaults and applies the given tokens; unknown keys and wrong types are
ignored, numbers are clamped to 0–4.

**Preview (development).** `SBGD_STYLE=<a JSON file of tokens>` applies a style at start, e.g.
`tools/style-preview/terminal.json` (monospace, square, a grid, little glow). With the captures:
`SBGD_STYLE=$PWD/tools/style-preview/terminal.json SBGD_SHOT_THEME=forest tools/showcase.sh terminal`.

**Next (step 2).** A theme as a folder of data: `theme.json` (palette + tokens), an OFL font file, optional
sounds; the built-in ones plus the user's `themes/` folder; data only, never code; a check that text stays
readable. Then a "Make a theme" page for the community.

# Arabic Poem for Noctalia

Rotating Arabic poems on the Noctalia desktop, with the Arabic weekday and
Hijri date as separate tiles. This is the Noctalia v5 version of the old
GNOME/azclock “Arabic Poem” setup, keeping the same 36-poem corpus, themes,
tashkeel, equal-width verse columns, font rotation, and 8-hour/online
rotation.

![Arabic Poem desktop widgets](docs/preview.png)

## What it does

- Shows one poem at a time from `arabic-poem/data/poems.json` (36 entries).
- Shows the Arabic weekday and Hijri date in two separate desktop tiles.
- Renders every tile as a transparent PNG with Python, Pango, and Cairo, so
  Arabic shaping, tatweel justification, and equal-width hemistichs are exact.
- Rotates to the next poem only after 8 hours **and** only when the machine is
  online. If offline, the current poem stays and the service retries later.
- Rotates the verse font with the poem. The bundled Amiri Quran + Amiri fonts
  give two usable fonts out of the box; PanoramaNaskh, Shafigh, and Thmanyah
  are optional and fall back to Amiri if absent.
- Redraws the weekday/date at local midnight (checked every 5 minutes).
- Provides a bar button and an IPC command for manual rotation.
- Does **not** use Rubik for Arabic. Rubik never touches the poem, weekday, or
  date text.

There is no eww layer, no systemd timer, and no GNOME/azclock dependency. The
Noctalia service runs the renderer, and the three desktop widgets display the
PNGs it writes.

## Requirements

- Noctalia v5 with plugin API 3 or newer.
- niri (any Wayland compositor should work; this was built for niri).
- Python 3.10+ with:
  - PyGObject and the Pango/PangoCairo GI typelibs
  - pycairo
  - `hijridate` (the old `hijri_converter` import name also works)
- fontconfig
- Amiri and Amiri Quran fonts (bundled; install them with `./install.sh --fonts`)

Distro package names vary. Typical packages:

```sh
# Arch
sudo pacman -S python python-gobject pango cairo fontconfig

# Fedora
sudo dnf install python3 python3-gobject pango cairo fontconfig

# Debian / Ubuntu
sudo apt install python3 python3-gi gir1.2-pango-1.0 gir1.2-cairo-1.0 libcairo2 fontconfig
```

Install the Python-only dependency as your user:

```sh
python3 -m pip install --user hijridate
```

If your distro puts `python3` somewhere unusual, set the plugin's **Python
command** setting to that interpreter (or set `PYTHON=/path/to/python3` for
`install.sh`).

## Install manually

These are the commands to run **on the machine that has Noctalia**. The helper
does not use sudo and does not install distro packages.

```sh
git clone https://github.com/amr/arabic-poem-noctalia.git
cd arabic-poem-noctalia

# 1. See what is missing. Fix the fail lines before continuing.
./install.sh --check

# 2. Install the bundled OFL Amiri / Amiri Quran fonts for your user.
./install.sh --fonts

# 3. Render a standalone preview so you can inspect the PNGs immediately.
./install.sh --preview

# 4. Add this repository as a Noctalia source and enable the plugin.
./install.sh --source
./install.sh --enable
```

Equivalent manual commands:

```sh
noctalia msg plugins source add arabic-poem path "$PWD"
noctalia msg plugins enable amr/arabic-poem
noctalia msg plugins list
```

The source name (`arabic-poem`) is only a local label. The plugin id is
`amr/arabic-poem`.

### Add the three desktop widgets

Open the desktop-widget editor:

```sh
noctalia msg desktop-widgets-edit
```

Add these three widget types:

| Widget | Type | Canvas |
| --- | --- | --- |
| Poem | `amr/arabic-poem:poem` | 880 × 380 |
| Weekday | `amr/arabic-poem:weekday` | 700 × 140 |
| Hijri date | `amr/arabic-poem:date` | 700 × 120 |

For all three tiles:

- Set **Background off** so the transparent PNG is the only visible layer.
- Keep the tile scale at 1.0 unless you deliberately want larger text.
- Do not rotate the tiles.
- Suggested placement on a single monitor:
  - Poem: top-right.
  - Weekday: bottom-left, above the date.
  - Date: bottom-left, under the weekday.

The PNGs are rendered at 2× and displayed at their logical size, so they stay
sharp on HiDPI outputs. Noctalia applies the output scale on top.

### Optional bar button

Add the **Arabic Poem Refresh** bar widget (`amr/arabic-poem:refresh`) from
Noctalia's bar settings. Clicking it rotates the poem immediately and shows a
notification (unless you turn notifications off in the plugin settings).

### niri keybind

Add a keybind to `~/.config/niri/config.kdl`:

```kdl
binds {
    Mod+Shift+P { spawn "noctalia" "msg" "plugin" "amr/arabic-poem:service" "all" "force"; }
}
```

Then reload niri (`niri msg action reload-config` or your usual reload). The
same command works from a terminal:

```sh
noctalia msg plugin amr/arabic-poem:service all force
```

## Commands

```sh
# Rotate now, even if 8 hours have not passed and even if offline.
noctalia msg plugin amr/arabic-poem:service all force

# Re-render the current poem and the date tiles without rotating.
noctalia msg plugin amr/arabic-poem:service all refresh

# Ask the service for a notification containing its data directory,
# current poem, font, and date metadata.
noctalia msg plugin amr/arabic-poem:service all status
```

Direct renderer commands are useful for debugging. `--test` writes nothing:

```sh
PLUGIN="$PWD/arabic-poem"
DATA="$HOME/.local/share/arabic-poem"

python3 "$PLUGIN/renderer/update.py" \
  --plugin-dir "$PLUGIN" --data-dir "$DATA" --test --force

python3 "$PLUGIN/renderer/update.py" \
  --plugin-dir "$PLUGIN" --data-dir "$DATA" --status

python3 "$PLUGIN/renderer/update.py" \
  --plugin-dir "$PLUGIN" --data-dir "$DATA" --force

python3 "$PLUGIN/renderer/update.py" \
  --plugin-dir "$PLUGIN" --data-dir "$DATA" --refresh

python3 "$PLUGIN/renderer/update.py" \
  --plugin-dir "$PLUGIN" --data-dir "$DATA" --date-only
```

The plugin uses its own Noctalia data directory, not the `$DATA` path above.
The service's `status` notification prints the real path. If you run the
renderer manually against the plugin's data directory, use that path instead.

## How it works

The plugin has five entries:

- `service` — a headless service that checks every 5 minutes. It runs the
  renderer with `--if-due`; the renderer decides whether the poem is due and
  whether the local date changed.
- `poem`, `weekday`, `date` — three desktop widgets. They read
  `render/render.json` and display the PNG path, logical width, and logical
  height with `ui.image`. They only re-render when the metadata file's mtime
  changes.
- `refresh` — an optional bar widget that runs the renderer with `--force`.

The renderer stores state in its Noctalia data directory:

```text
<plugin data dir>/
  config.json        # editable layout/font/color config
  state.json         # current poem, font, queue, last_change
  render/
    poem-*.png
    weekday-*.png
    date-*.png
    render.json      # metadata the widgets poll
  render.log
  render.lock
```

It keeps the last three PNG versions of each tile and writes `render.json`
atomically. If a render is already running, the second process exits cleanly;
the lock prevents overlapping rotations.

Rotation logic:

1. If there is no current poem, choose the first enabled poem.
2. If 8 hours have passed and `is_online()` is true, choose the next poem from
   the shuffled queue and choose the next available verse font.
3. If 8 hours have passed but the machine is offline, keep the current poem.
4. If the local Gregorian date changed, redraw the weekday and Hijri date even
   when the poem is not due.

`--force` skips the interval and connectivity checks. `--refresh` keeps the
current poem and font and redraws. `--date-only` only redraws the date tiles.

## Configuration

The renderer copies the bundled defaults to `config.json` in the plugin data
directory on first use. Edit that file (the service's status notification
prints the directory), then run:

```sh
noctalia msg plugin amr/arabic-poem:service all refresh
```

The most useful keys:

| Key | Default | Meaning |
| --- | --- | --- |
| `interval_hours` | `8` | Poem rotation interval. |
| `verse_fonts` | `Amiri Quran`, `Amiri`, optional fonts | Available verse fonts, in preference order. Missing fonts are skipped. |
| `font_size_pt` | `31.25` | Poem font size. This matches the old GNOME 25pt at 1.25 text scaling. |
| `max_width_px` | `820` | Maximum poem text width; the renderer shrinks long poems. |
| `tashkeel` | `light` | `light`, `full`, or `none`. |
| `layout` | `columns` | `columns` for equal-width hemistichs, or `lines`. |
| `poem_width` / `poem_height` | `880` / `380` | Logical poem canvas. |
| `weekday_width` / `weekday_height` | `700` / `140` | Logical weekday canvas. |
| `date_width` / `date_height` | `700` / `120` | Logical Hijri date canvas. |
| `weekday_font` / `weekday_size_pt` | Thmanyah Serif Display / `60` | Falls back to Amiri if Thmanyah is absent. |
| `date_font` / `date_size_pt` | Thmanyah Serif Text / `35` | Falls back to Amiri if Thmanyah is absent. |
| `eastern_numerals` | `true` | Use ٠١٢٣٤٥٦٧٨٩ for the Hijri day. |
| `shadow_enabled` / `shadow_opacity` / `shadow_blur` | `true` / `0.55` / `3.0` | Text shadow over the wallpaper. |
| `online_timeout_sec` | `2.0` | Connectivity check timeout. |

Noctalia plugin settings (Settings → Plugins → Arabic Poem) expose only:

- **Python command** — default `python3`.
- **Check interval (minutes)** — default `5`, range 1–60.
- **Notify on manual refresh** — default on.

The poem/date typography lives in `config.json` because it is renderer config,
not a shell setting. The plugin UI, notifications, and helper output stay in
English. Arabic appears in the rendered PNGs; optional `--test`/`--status`
debug output may include it.

## Fonts

Bundled in `arabic-poem/fonts/`:

- Amiri Regular/Bold/Italic/BoldItalic
- Amiri Quran

Both are under the SIL Open Font License; see `arabic-poem/fonts/OFL.txt`.
`./install.sh --fonts` copies them to `~/.local/share/fonts/Amiri` and runs
`fc-cache`.

Optional fonts are **not** bundled:

- PanoramaNaskh
- Shafigh Bakh Thin MOB V2
- Thmanyah Serif Display / Thmanyah Serif Text

If installed, the renderer picks them up. If not, it falls back to Amiri. The
default `verse_fonts` list already includes Amiri, so rotation still has two
fonts with only the bundled files.

Do not add Rubik to `verse_fonts` or to the weekday/date font keys. The old
Rubik breakage is exactly what this renderer avoids.

## Troubleshooting

**`./install.sh --check` fails**

Install the missing distro packages and `hijridate`, then re-run. The check
prints the exact Python import error.

**Poem widget is blank**

Run the renderer directly with `--test` first. If that works, run `--force` and
check the plugin data directory. The service status notification prints the
path. Look at `render.log` for the last render.

**Arabic shows as boxes or disconnected letters**

Check fonts:

```sh
fc-match 'Amiri Quran'
fc-match 'Amiri'
```

Install the bundled fonts with `./install.sh --fonts` and run `fc-cache -f`.
The renderer falls back to Amiri, then Noto Naskh Arabic, then DejaVu Sans; if
none has Arabic glyphs you will see boxes.

**It never rotates**

The default is 8 hours **and** online. Check:

```sh
noctalia msg plugin amr/arabic-poem:service all status
```

`Due now: False` is normal until 8 hours have passed. Use `force` to rotate
immediately. If `Due now: True` but it stays, the connectivity check is failing;
`--force` bypasses it.

**The date is a day off**

`hijridate` uses the Umm al-Qura calendar. The renderer uses the local
Gregorian date. Verify with `--test` and `--date-only`; if your system clock or
timezone is wrong, fix that first.

**Widgets do not update after a manual render**

The desktop widgets poll `render/render.json` once per second. If you rendered
into a different `--data-dir`, they will not see it. Use the service command
(`force`/`refresh`) so it writes to the plugin data directory. A Noctalia
restart also re-reads the file.

**The bar button says “Another render is already running”**

That is the renderer lock. Wait a moment and click again; the first render is
still finishing.

## Testing

See [TESTING.md](TESTING.md) for the friend-run checklist. It covers the
dependency check, fonts, standalone PNGs, plugin enablement, the three desktop
widgets, bar/keybind refresh, status output, and logs.

## Repository layout

```text
arabic-poem-noctalia/
  catalog.toml                 # Noctalia source catalog
  install.sh                   # manual helper (check/fonts/preview/source/enable)
  docs/preview.png             # README preview
  TESTING.md                   # friend-run test checklist
  arabic-poem/
    plugin.toml                # Noctalia manifest (plugin API 3)
    entries/                   # service + 3 desktop widgets + bar button
    renderer/                  # Python/Pango renderer
    data/poems.json            # 36-poem corpus
    data/config.default.json   # renderer defaults
    fonts/                     # bundled OFL Amiri / Amiri Quran
    translations/en.json       # settings labels
    README.md                  # plugin-store README
    thumbnail.webp             # plugin-store thumbnail
```

## License

Code: MIT (see `LICENSE`). Fonts: SIL OFL 1.1 (see
`arabic-poem/fonts/OFL.txt`). Poem texts are attributed to their poets in
`arabic-poem/data/poems.json` and are included for personal display.

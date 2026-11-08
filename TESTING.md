# Friend-run test checklist

This checklist is for testing the plugin on the machine that runs Noctalia.
Nothing here should be run by the repository author on your machine. Copy the
commands into your own terminal and fix any `fail` line before moving on.

Record the result of each step. The pass criteria are at the end.

## 0. Environment

```sh
noctalia --version
niri --version
python3 --version
echo "XDG_DATA_HOME=${XDG_DATA_HOME:-$HOME/.local/share}"
```

Expected: Noctalia v5 or newer, niri, and Python 3.10+. If `noctalia` or
`niri` is not on `PATH`, use the absolute path in the commands below.

## 1. Dependencies and fonts

From the repository root:

```sh
./install.sh --check
```

Expected:

- `PyGObject + Pango + PangoCairo`, `pycairo`, and `hijridate` are `ok`.
- `Amiri Quran` and `Amiri` are `ok`.
- `PanoramaNaskh`, `Shafigh`, and `Thmanyah` may be `warn`; they are optional.
- `noctalia`, `niri`, and `magick` may be `warn` only if you are not using
  them; `noctalia` is required for the next steps.

If a required line is `fail`, install the package and re-run. For the Python
package:

```sh
python3 -m pip install --user hijridate
```

Install the bundled fonts:

```sh
./install.sh --fonts
fc-match 'Amiri Quran'
fc-match 'Amiri'
```

Expected: both `fc-match` commands return Amiri/Amiri Quran, not DejaVu Sans.

## 2. Renderer smoke test

Render a standalone preview:

```sh
./install.sh --preview
```

Expected output includes `Poem rotated: ...` and `Date updated: ...`. Inspect
the PNGs under `~/.local/share/arabic-poem/render/`:

```sh
ls -l ~/.local/share/arabic-poem/render/
magick identify ~/.local/share/arabic-poem/render/*.png
python3 -m json.tool ~/.local/share/arabic-poem/render/render.json | head -60
```

Expected:

- The poem PNG is `1760x760` (2× of 880×380).
- The weekday PNG is `1400x280` (2× of 700×140).
- The date PNG is `1400x240` (2× of 700×120).
- `render.json` has `poem`, `weekday`, and `date` objects with `png`,
  `width`, and `height`.
- Open the PNGs on a dark background. Arabic letters are connected, the two
  poem columns end at the same separator position, and the text is light with
  a subtle shadow. There are no boxes or disconnected letters.

Check the selection without writing:

```sh
PLUGIN="$PWD/arabic-poem"
DATA="$HOME/.local/share/arabic-poem"
python3 "$PLUGIN/renderer/update.py" \
  --plugin-dir "$PLUGIN" --data-dir "$DATA" --test --force
```

Expected: `Entry`, `Poet`, `Font`, `Scale`, `Weekday`, and `Hijri date` are
printed; no files are written.

## 3. Enable the plugin

```sh
./install.sh --source
./install.sh --enable
noctalia msg plugins list
```

Expected: the list contains `amr/arabic-poem` and it is enabled. If the source
name `arabic-poem` already exists, remove the old source from Noctalia's plugin
settings first, or add this path manually with a different source name:

```sh
noctalia msg plugins source add arabic-poem-2 path "$PWD"
```

Check that the service started:

```sh
noctalia msg plugin amr/arabic-poem:service all status
```

Expected: a Noctalia notification with a `Data:` path, a poem id, a font, a
date, and a weekday index. **Write down the `Data:` path**; it is the plugin
data directory used by the widgets. It is different from the preview directory
in step 2.

## 4. Add the three desktop widgets

```sh
noctalia msg desktop-widgets-edit
```

Add these three widget types:

| Widget | Type | Size | Background |
| --- | --- | --- | --- |
| Poem | `amr/arabic-poem:poem` | 880 × 380 | Off |
| Weekday | `amr/arabic-poem:weekday` | 700 × 140 | Off |
| Date | `amr/arabic-poem:date` | 700 × 120 | Off |

Place them on the single monitor:

- Poem: top-right.
- Weekday: bottom-left, above the date.
- Date: bottom-left, under the weekday.

Expected:

- All three tiles are visible and have no rectangular background.
- The poem is the same text/font as the current `render.json` in the plugin
  data directory.
- The weekday and Hijri date match the local day.
- No Arabic text is rendered by Rubik; the glyphs come from the PNGs.

If a tile is blank, go to step 8 and check the plugin data directory and
`render.log`.

## 5. Manual rotation

### Bar button (optional)

Add `amr/arabic-poem:refresh` to a bar from Noctalia's bar settings, then click
it.

Expected:

- A notification says `Poem rotated: ...`.
- The poem changes to the next entry.
- The font may change to the next available font.
- The weekday/date stay the same unless the local date changed.

### niri keybinds

Add to `~/.config/niri/config.kdl`:

```kdl
binds {
    Mod+Shift+P { spawn "noctalia" "msg" "plugin" "amr/arabic-poem:service" "all" "force"; }
    Mod+Shift+R { spawn "noctalia" "msg" "plugin" "amr/arabic-poem:service" "all" "refresh"; }
}
```

Reload niri, then press `Mod+Shift+P` to rotate and `Mod+Shift+R` to refresh the
current poem without rotating.

Expected:

- `Mod+Shift+P`: the same rotation as the bar button. The notification may
  appear if **Notify on manual refresh** is on.
- `Mod+Shift+R`: the same poem id and font are re-rendered; the PNG mtimes and
  `render.json` mtime change; the poem does not advance.

### IPC directly

```sh
noctalia msg plugin amr/arabic-poem:service all force
noctalia msg plugin amr/arabic-poem:service all refresh
```

Expected: `force` rotates and `refresh` re-renders the current poem. Run `force`
twice; the second call should rotate again, not show the render lock error. If it
does show `Another render is already running`, wait a moment and retry.

## 6. Refresh and date-only

Refresh the current poem without rotating:

```sh
noctalia msg plugin amr/arabic-poem:service all refresh
```

Expected:

- The notification says `Poem refreshed: ...` (same poem id and font).
- The PNG mtimes and `render.json` mtime change.
- The poem does not advance in the corpus.

Re-render only the date tiles:

```sh
PLUGIN="$PWD/arabic-poem"
DATA="<the Data: path from step 3>"
python3 "$PLUGIN/renderer/update.py" \
  --plugin-dir "$PLUGIN" --data-dir "$DATA" --date-only --notify
```

Expected: `Date updated: ...`; the weekday/date PNG mtimes change; the poem
PNG is untouched. The desktop widgets update within about a second.

## 7. Rotation interval and offline behavior

The default is 4 hours **and** online. `force` bypasses both; this step tests
the real due/online path. Existing configs that still use the old 8-hour default
are migrated to 4 hours on first load; a custom interval is preserved.

1. Get the plugin data directory from `status`.
2. Back up `state.json` in that directory.
3. Set `last_change` in `state.json` to an old ISO timestamp, for example
   `2020-01-01T00:00:00+00:00`. Keep the rest of the JSON valid.
4. Run the renderer's due path against the plugin data directory:

```sh
PLUGIN="$PWD/arabic-poem"
DATA="<the Data: path from step 3>"
python3 "$PLUGIN/renderer/update.py" \
  --plugin-dir "$PLUGIN" --data-dir "$DATA" --if-due --notify
```

Expected while online: `Poem rotated: ...` and a new poem id. Expected while
offline: `Offline: keeping the current poem.` and the poem id stays. The service
will retry on its next 5-minute tick after connectivity returns.

5. Restore the original `state.json` if you want to keep the old schedule.

## 8. Logs and recovery

The renderer writes `render.log` in the plugin data directory. Check it after a
failed render:

```sh
tail -n 50 "<the Data: path from step 3>/render.log"
```

Also check Noctalia's own log output (the terminal or journal where you launch
Noctalia). Common causes:

- `python3` not found → set **Python command** in plugin settings to the
  absolute interpreter path.
- `No module named gi` / `cairo` / `hijridate` → install the dependency from
  step 1.
- Arabic boxes → fonts missing; run `./install.sh --fonts` and `fc-cache -f`.
- Widgets blank but PNGs exist → the widgets are reading a different data
  directory; use the service `force`/`refresh` commands so it writes to the
  plugin data directory.

## 9. Uninstall

Use Noctalia's plugin settings to disable `amr/arabic-poem`, remove the three
desktop widgets, and remove the `arabic-poem` source if you no longer want it.
The bundled fonts can stay in `~/.local/share/fonts/Amiri`; they are ordinary
user fonts. The plugin data directory can be deleted after disabling the
plugin.

## Pass criteria

The test passes when all of these are true:

- [ ] `./install.sh --check` has no required `fail` lines.
- [ ] `./install.sh --fonts` installs Amiri and Amiri Quran; `fc-match` finds
      both.
- [ ] `./install.sh --preview` writes three transparent PNGs and valid
      `render.json`.
- [ ] The three desktop widgets display the poem, weekday, and Hijri date with
      **Background off** and no boxes/disconnected Arabic.
- [ ] Bar button and `Mod+Shift+P` both rotate the poem and produce a
      notification when enabled.
- [ ] `Mod+Shift+R` and `refresh` re-render the same poem/font without rotating.
- [ ] `--date-only` re-renders only the date tiles.
- [ ] With `last_change` set to an old time and the machine online, `--if-due`
      rotates; with the machine offline, it keeps the current poem.
- [ ] `status` reports the plugin data directory, poem, font, date, and
      weekday index.
- [ ] `render.log` has no unexpected traceback.

## Report back

Please send:

- Noctalia/niri/Python versions.
- The `--check` output (or just the fail/warn lines).
- The three PNGs or a screenshot of the desktop.
- The `status` notification text (redact anything private).
- Any `render.log` tail or Noctalia error.

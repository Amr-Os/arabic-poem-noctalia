# Friend-run test checklist

This checklist is for the machine that runs Noctalia. The recommended path is
to add the repository as a **source** in Noctalia's settings and install the
plugin from the Plugins page. You do **not** need to clone the repository or run
`install.sh`.

Record the result of each step. The pass criteria are at the end.

## 1. Add the source from Noctalia's UI

1. Open **Settings → Plugins → Sources**.
2. Click **Add Source**.
3. Name it `arabic-poem` (the name is only local).
4. Choose **Git**.
5. Enter:

   ```text
   https://github.com/Amr-Os/arabic-poem-noctalia.git
   ```

6. Save the source.
7. Go back to **Settings → Plugins**, find **Arabic Poem**, and enable it.
   If it is not listed yet, press **Update** on the source or reopen the plugin
   page.

Expected: the plugin row shows **Arabic Poem** and is enabled, with no
“incompatible plugin API” badge. Noctalia v5 with plugin API 3+ is required.

CLI equivalent:

```sh
noctalia msg plugins source add arabic-poem git https://github.com/Amr-Os/arabic-poem-noctalia.git
noctalia msg plugins enable amr/arabic-poem
noctalia msg plugins list
```

If the source name already exists, remove the old source first or use another
name.

## 2. First render and fonts

Wait a few seconds after enabling the plugin, then request the service status:

```sh
noctalia msg plugin amr/arabic-poem:service all status
```

Expected: a Noctalia notification with:

- a `Data:` path (the plugin data directory),
- a poem id,
- a font name,
- a Hijri date,
- a weekday index.

**Write down the `Data:` path**; the desktop widgets use that directory.

The first render also copies the bundled Amiri/Amiri Quran fonts into
`~/.local/share/fonts/Amiri` and refreshes fontconfig. Verify:

```sh
fc-match 'Amiri Quran'
fc-match 'Amiri'
```

Expected: both return Amiri/Amiri Quran, not DejaVu Sans. If they do not, run the
optional fallback from a clone of the repository:

```sh
./install.sh --fonts
fc-cache -f
```

`hijridate` is optional; the plugin ships an Umm al-Qura fallback, so a UI-only
install does not need `pip install`.

## 3. Add the three desktop widgets

Open the desktop-widget editor from **Settings → Desktop → Widgets**, or run:

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
- The poem matches the current `render.json` in the plugin data directory.
- The weekday and Hijri date match the local day.
- Arabic letters are connected and there are no boxes or disconnected glyphs.

If a tile is blank, check the plugin data directory and `render.log` (step 6).

## 4. Manual rotation and refresh

### Bar button (optional)

Add `amr/arabic-poem:refresh` to a bar from Noctalia's bar settings, then click
it.

Expected: a notification says `Poem rotated: ...`; the poem changes; the font
may change; the weekday/date stay the same unless the local date changed.

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

- `Mod+Shift+P`: the poem advances to the next entry.
- `Mod+Shift+R`: the same poem id and font are re-rendered; the PNG mtimes and
  `render.json` mtime change; the poem does not advance.

### IPC directly

```sh
noctalia msg plugin amr/arabic-poem:service all force
noctalia msg plugin amr/arabic-poem:service all refresh
```

`force` rotates; `refresh` re-renders the current poem. If a second `force`
immediately reports `Another render is already running`, wait a moment and
retry; the lock prevents overlapping renders.

## 5. Rotation interval and offline behavior

The default is 4 hours **and** online. `force` bypasses both. To test the real
due/online path:

1. Get the `Data:` path from the status notification.
2. Back up `state.json` in that directory.
3. Set `last_change` in `state.json` to an old ISO timestamp, for example
   `2020-01-01T00:00:00+00:00`. Keep the JSON valid.
4. Run the service check:

   ```sh
   noctalia msg plugin amr/arabic-poem:service all refresh
   ```

   This refreshes without rotating, so use the renderer directly if you have a
   clone, or wait for the next 5-minute service tick:

   ```sh
   PLUGIN="$PWD/arabic-poem"
   DATA="<the Data: path from step 2>"
   python3 "$PLUGIN/renderer/update.py" \
     --plugin-dir "$PLUGIN" --data-dir "$DATA" --if-due --notify
   ```

Expected while online: the poem rotates. Expected while offline:
`Offline: keeping the current poem.` and the poem id stays. The service retries
on its next tick.

5. Restore the original `state.json` if you want to keep the old schedule.

## 6. Logs and recovery

The renderer writes `render.log` in the plugin data directory:

```sh
tail -n 50 "<the Data: path from step 2>/render.log"
```

Also check Noctalia's own log output. Common causes:

- `python3` not found → set **Python command** in the plugin settings to the
  absolute interpreter path.
- `No module named gi` / `cairo` → install PyGObject and pycairo for your
  distro, then re-enable the plugin.
- `Namespace Pango not available` / `Typelib file for namespace 'Pango' not
  found` on NixOS → use `nix/arabic-poem-python.nix` and set **Python command**
  to `/run/current-system/sw/bin/arabic-poem-python`. Verify with:

  ```sh
  arabic-poem-python -c 'import gi; gi.require_version("Pango", "1.0"); gi.require_version("PangoCairo", "1.0"); from gi.repository import Pango, PangoCairo; print("Pango ok")'
  ```

  Full steps: `NIXOS.md`.
- Arabic boxes → fonts missing; wait for the automatic font copy, or run
  `./install.sh --fonts` from a clone and `fc-cache -f`.
- Widgets blank but PNGs exist → the widgets are reading a different data
  directory; use the service commands so the renderer writes to the plugin data
  directory.

## 7. Uninstall

Use Noctalia's plugin settings to disable `amr/arabic-poem`, remove the three
desktop widgets, and remove the `arabic-poem` source if you no longer want it.
The bundled fonts can stay in `~/.local/share/fonts/Amiri`; they are ordinary
user fonts. The plugin data directory can be deleted after disabling the
plugin.

## Pass criteria

The test passes when all of these are true:

- [ ] The `arabic-poem` git source is added from the UI and `Arabic Poem` is
      enabled from the Plugins page.
- [ ] `status` reports the plugin data directory, poem, font, date, and weekday.
- [ ] `fc-match` finds Amiri and Amiri Quran; no font step was required.
- [ ] The three desktop widgets display the poem, weekday, and Hijri date with
      **Background off** and no boxes/disconnected Arabic.
- [ ] The bar button and `Mod+Shift+P` rotate the poem.
- [ ] `Mod+Shift+R` and `refresh` re-render the same poem/font without rotating.
- [ ] With `last_change` set to an old time and the machine online, the due path
      rotates; with the machine offline, it keeps the current poem.
- [ ] `render.log` has no unexpected traceback.
- [ ] On NixOS, the wrapper check prints `Pango ok` and the plugin's **Python
      command** points at the wrapper, not a bare `python3`.

## Report back

Please send:

- Noctalia/niri/Python versions.
- Whether the source appeared after **Add Source**, and whether the plugin could
  be enabled from the UI.
- The `status` notification text (redact anything private).
- A screenshot of the three desktop widgets.
- Any `render.log` tail or Noctalia error.

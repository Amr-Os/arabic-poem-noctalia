# Arabic Poem

Rotating Arabic poems with the Arabic weekday and Hijri date as three desktop
widgets. This is a Noctalia v5 plugin; it replaces the old GNOME/azclock setup
without putting Arabic text through Rubik or a shell widget.

![Arabic Poem desktop widgets](thumbnail.webp)

## Entries

- **Poem** (`amr/arabic-poem:poem`) — the rotating poem tile.
- **Weekday** (`amr/arabic-poem:weekday`) — the Arabic weekday tile.
- **Date** (`amr/arabic-poem:date`) — the Hijri date tile.
- **Refresh** (`amr/arabic-poem:refresh`) — optional bar button that rotates
  immediately.
- **Service** (`amr/arabic-poem:service`) — checks every 5 minutes, rotates
  after 4 hours when online, and redraws the date at local midnight.

## How it renders

Every tile is a transparent PNG rendered by Python, Pango, and Cairo. Arabic
shaping, tashkeel, tatweel justification, equal-width hemistichs, and font
selection all happen in the renderer. The widgets only display the resulting
image with `ui.image`, so they never shape Arabic themselves.

The 36-poem corpus, themes, and tashkeel settings are in
`data/poems.json`. The default fonts are Amiri Quran and Amiri; PanoramaNaskh,
Shafigh, and Thmanyah are optional and fall back to Amiri.

## Install from Noctalia's UI

This is the recommended install path. You do not need to clone the repository or
run `install.sh`.

1. Open **Settings → Plugins → Sources**.
2. Click **Add Source**.
3. Name it `arabic-poem` (the name is only local).
4. Choose **Git**.
5. Use this URL:

   ```text
   https://github.com/Amr-Os/arabic-poem-noctalia.git
   ```

6. Save the source.
7. Go back to **Settings → Plugins**, find **Arabic Poem**, and enable it.
   If it is not listed yet, press **Update** on the source or reopen the plugin
   page.
8. Add the three desktop widget types from **Settings → Desktop → Widgets**
   (or run `noctalia msg desktop-widgets-edit`).

Add the three desktop widget types and turn **Background off** on each tile:

- `amr/arabic-poem:poem` — 880 × 380
- `amr/arabic-poem:weekday` — 700 × 140
- `amr/arabic-poem:date` — 700 × 120

Suggested placement on one monitor: poem top-right; weekday bottom-left above
the date; date bottom-left.

The service copies the bundled Amiri fonts into your user font directory on its
first render, so the UI install does not require a separate font step.

### CLI alternative

```sh
noctalia msg plugins source add arabic-poem git https://github.com/Amr-Os/arabic-poem-noctalia.git
noctalia msg plugins enable amr/arabic-poem
```

Manual rotation:

```sh
noctalia msg plugin amr/arabic-poem:service all force
```

Refresh the current poem without rotating:

```sh
noctalia msg plugin amr/arabic-poem:service all refresh
```

niri keybinds:

```kdl
binds {
    Mod+Shift+P { spawn "noctalia" "msg" "plugin" "amr/arabic-poem:service" "all" "force"; }
    Mod+Shift+R { spawn "noctalia" "msg" "plugin" "amr/arabic-poem:service" "all" "refresh"; }
}
```

`Mod+Shift+P` rotates to the next poem; `Mod+Shift+R` refreshes the current
poem image without rotating.

Status:

```sh
noctalia msg plugin amr/arabic-poem:service all status
```

## Requirements

Noctalia v5 with plugin API 3+, Python 3 with PyGObject/Pango/Cairo, and
fontconfig. The bundled Amiri/Amiri Quran fonts are installed automatically on
first run. `hijridate` is optional; the plugin includes a Umm al-Qura fallback,
so no `pip install` is required for a UI-only install.

The repository root also has an optional `install.sh` helper for dependency
checks, font installation, and preview rendering. It does not use sudo or install
distro packages.

### NixOS

A plain `python3` on NixOS does not expose the Pango/PangoCairo GObject
Introspection typelibs, which causes `Namespace Pango not available`. Use the
wrapper in the repository root at `nix/arabic-poem-python.nix`; it provides
PyGObject, pycairo, the Pango/PangoCairo/HarfBuzz/cairo/GLib typelibs, and fontconfig.

Add the wrapper to your configuration and set the plugin's **Python command** to
the absolute path:

```text
/run/current-system/sw/bin/arabic-poem-python
```

Noctalia's NixOS systemd module clears the service `PATH`, so do not use a bare
`python3` there. Full NixOS module, Home Manager, and verification examples are
in `NIXOS.md` in the repository root.

## Settings

- **Python command** — interpreter used for the renderer.
- **Check interval (minutes)** — default 5.
- **Notify on manual refresh** — default on.

Layout, colors, canvas sizes, and fonts live in the renderer's `config.json` in
the plugin data directory. The status notification prints that directory.
Existing configs that still use the old 8-hour default are migrated to 4 hours
on first load; custom intervals are preserved.

## License

MIT for the code; bundled Amiri/Amiri Quran fonts are SIL OFL 1.1. Poem texts
are attributed in `data/poems.json`.

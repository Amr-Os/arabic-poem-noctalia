# NixOS

The plugin is installed through Noctalia, but its renderer is a Python process.
On NixOS, a normal `python3` does not expose the Pango/PangoCairo GObject
Introspection typelibs. That is the cause of:

```text
Namespace Pango not available
Typelib file for namespace 'Pango' not found
```

The wrapper in [`nix/arabic-poem-python.nix`](nix/arabic-poem-python.nix) fixes
that by adding `Pango`, `PangoCairo`, `HarfBuzz`, `cairo`, `GLib`, and
`GObject` typelibs to `GI_TYPELIB_PATH`, and by putting `fontconfig` on `PATH`
so the automatic font copy can run `fc-cache`.

## 1. Add the wrapper to your NixOS configuration

The examples assume Noctalia is available as a flake input:

```nix
inputs.noctalia.url = "github:noctalia-dev/noctalia";
```

Put the wrapper in the same flake/repository as your NixOS configuration, or
copy `nix/arabic-poem-python.nix` there.

### NixOS module (imperative plugin setup)

```nix
# configuration.nix or flake module
{ inputs, pkgs, ... }:
let
  poemPython = pkgs.callPackage ./nix/arabic-poem-python.nix { };
in
{
  imports = [
    inputs.noctalia.nixosModules.default
  ];

  programs.noctalia = {
    enable = true;
    package = inputs.noctalia.packages.${pkgs.stdenv.hostPlatform.system}.default;
    recommendedServices.enable = true;
    systemd.enable = true;
  };

  environment.systemPackages = [
    poemPython
    pkgs.fontconfig
  ];

  # Optional: the plugin bundles Amiri Quran and installs it on first run.
  fonts.packages = [ pkgs.amiri ];
}
```

Then rebuild and switch:

```sh
sudo nixos-rebuild switch --flake .#your-host
```

The wrapper is available as `/run/current-system/sw/bin/arabic-poem-python`.
Check it:

```sh
arabic-poem-python -c 'import gi; gi.require_version("Pango", "1.0"); gi.require_version("PangoCairo", "1.0"); from gi.repository import Pango, PangoCairo; print("Pango ok")'
```

Expected: `Pango ok`.

### Home Manager (declarative plugin setup)

```nix
{ inputs, pkgs, ... }:
let
  poemPython = pkgs.callPackage ./nix/arabic-poem-python.nix { };
in
{
  imports = [
    inputs.noctalia.homeModules.default
  ];

  fonts.fontconfig.enable = true;

  home.packages = [
    poemPython
    pkgs.fontconfig
    pkgs.amiri
  ];

  programs.noctalia = {
    enable = true;
    package = inputs.noctalia.packages.${pkgs.stdenv.hostPlatform.system}.default;
    systemd.enable = true;

    settings = {
      plugins = {
        enabled = [ "amr/arabic-poem" ];
        source = [
          {
            name = "arabic-poem";
            kind = "git";
            location = "https://github.com/Amr-Os/arabic-poem-noctalia.git";
            enabled = true;
          }
        ];
      };

      plugin_settings."amr/arabic-poem" = {
        python = "${poemPython}/bin/arabic-poem-python";
        interval_minutes = 5;
        notify = true;
      };
    };
  };
}
```

If your nixpkgs already provides Noctalia, you can omit `package = ...` and use
the default package.

## 2. Add the source and enable the plugin

If you used the Home Manager snippet above, the source and `plugins.enabled`
are already declared. Otherwise use the UI:

1. **Settings → Plugins → Sources → Add Source**.
2. Name: `arabic-poem`; kind: **Git**.
3. URL: `https://github.com/Amr-Os/arabic-poem-noctalia.git`.
4. Save, then enable **Arabic Poem** in **Settings → Plugins**.

CLI equivalent:

```sh
noctalia msg plugins source add arabic-poem git https://github.com/Amr-Os/arabic-poem-noctalia.git
noctalia msg plugins enable amr/arabic-poem
```

## 3. Point the plugin at the wrapper

If you did **not** set `plugin_settings` declaratively, set it in the UI:

**Settings → Plugins → Arabic Poem → gear → Python command**:

```text
/run/current-system/sw/bin/arabic-poem-python
```

Then toggle the plugin off/on, or run:

```sh
noctalia msg plugins disable amr/arabic-poem
noctalia msg plugins enable amr/arabic-poem
```

Noctalia's NixOS systemd module clears the service `PATH`, so using the absolute
wrapper path is important. The wrapper itself puts `fontconfig` on `PATH`.

## 4. Verify

```sh
arabic-poem-python -c 'import gi; gi.require_version("Pango", "1.0"); gi.require_version("PangoCairo", "1.0"); from gi.repository import Pango, PangoCairo; import cairo; print("renderer deps ok")'
fc-match 'Amiri Quran'
fc-match 'Amiri'
noctalia msg plugin amr/arabic-poem:service all status
```

Expected: `renderer deps ok`; both `fc-match` commands return Amiri fonts; the
status notification contains a `Data:` path, poem, font, and Hijri date.

## Troubleshooting

### `Namespace Pango not available`

The Python command is not using the wrapper, or `GI_TYPELIB_PATH` is missing
Pango **or one of Pango's own GI dependencies** (`HarfBuzz-0.0`, `GObject-2.0`,
`Gio-2.0`, or `cairo-1.0`). Set the plugin's **Python command** to the absolute
wrapper path and restart the plugin. Verify with the `Pango ok` command above.

To inspect the path the wrapper sees:

```sh
echo "$GI_TYPELIB_PATH" | tr ':' '\n'
find /nix/store -maxdepth 5 \
  \( -name 'Pango-1.0.typelib' -o -name 'PangoCairo-1.0.typelib' \
     -o -name 'HarfBuzz-0.0.typelib' \) 2>/dev/null
```

If the wrapper is old and lacks `harfbuzz`/`freetype`, replace
`nix/arabic-poem-python.nix` with the current version and rebuild. If
`HarfBuzz-0.0.typelib` is genuinely absent from your nixpkgs, override HarfBuzz
with introspection enabled:

```nix
harfbuzz = pkgs.harfbuzz.override { withIntrospection = true; };
```

### `No module named gi`

The interpreter is not the wrapper's interpreter. Use
`/run/current-system/sw/bin/arabic-poem-python`, or add
`(pkgs.python3.withPackages (ps: [ ps.pygobject3 ps.pycairo ]))` to your
packages.

### `No module named cairo`

Add `pycairo` to the Python environment; the wrapper already includes it.

### Fonts are boxes

The plugin copies its bundled Amiri fonts to `~/.local/share/fonts/Amiri` on
first render and runs `fc-cache`. The wrapper puts `fontconfig` on `PATH`. If
needed, add `fonts.packages = [ pkgs.amiri ];` and rebuild.

### `fc-cache: command not found`

Add `pkgs.fontconfig` to `environment.systemPackages` (the NixOS example does
this) or use the wrapper, which adds it to `PATH`.

### The plugin is listed but cannot be enabled

Check the Noctalia plugin API badge. This plugin requires plugin API 3+, which
current Noctalia v5 supports. If the source was added before a repo update, press
**Update** on the source.

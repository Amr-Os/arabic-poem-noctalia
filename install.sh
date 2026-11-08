#!/usr/bin/env bash
# Optional installation/diagnostic helper for the Arabic Poem Noctalia plugin.
#
# The recommended install is Noctalia's UI:
#   Settings -> Plugins -> Sources -> Add Source
# then enable Arabic Poem from Settings -> Plugins.
#
# This script never uses sudo and never installs packages for you.  It can check
# dependencies, copy the bundled OFL fonts, render a preview, and add the source
# from the CLI as a fallback.
set -u

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PLUGIN="$ROOT/arabic-poem"
PYTHON=${PYTHON:-python3}
DATA_HOME=${XDG_DATA_HOME:-$HOME/.local/share}
FONT_DIR="$DATA_HOME/fonts/Amiri"
PREVIEW_DIR="$DATA_HOME/arabic-poem"
FAILED=0

usage() {
  cat <<EOF
Arabic Poem for Noctalia — optional helper

Recommended install:
  Settings -> Plugins -> Sources -> Add Source
  Name: arabic-poem, kind: Git
  URL: https://github.com/Amr-Os/arabic-poem-noctalia.git
  Then enable Arabic Poem in Settings -> Plugins.

Usage:
  ./install.sh --check        Check Python/Pango/Cairo, fontconfig, fonts
  ./install.sh --fonts        Copy bundled Amiri / Amiri Quran fonts to ~/.local/share/fonts/Amiri
  ./install.sh --preview      Render one poem/weekday/date into ~/.local/share/arabic-poem
  ./install.sh --source       Add this repository as a Noctalia git source
  ./install.sh --source-path  Add this checkout as a path source (development)
  ./install.sh --enable       Enable amr/arabic-poem in Noctalia
  ./install.sh --status       Ask the running service for its status notification
  ./install.sh --all          check + fonts + preview + source + enable

Environment:
  PYTHON=/path/to/python3              Interpreter to use (default: python3)
  ARABIC_POEM_SOURCE_URL=...           Override the git source URL
  XDG_DATA_HOME=...                    Base for the user font and preview directories

This helper does not install system packages.  See README.md for distro package
names and NIXOS.md for the NixOS wrapper (Pango GI typelibs).
EOF
}

need() {
  command -v "$1" >/dev/null 2>&1
}

ok() {
  printf '  ok    %s\n' "$*"
}

warn() {
  printf '  warn  %s\n' "$*"
}

bad() {
  printf '  fail  %s\n' "$*"
  FAILED=1
}

font_state() {
  family=$1
  required=$2
  hint=${3:-optional; the renderer falls back to Amiri}
  found=$(fc-match -f '%{family}' "$family" 2>/dev/null | head -n 1)
  lower=$(printf '%s' "$found" | tr '[:upper:]' '[:lower:]')
  want=$(printf '%s' "$family" | tr '[:upper:]' '[:lower:]')
  case "$lower" in
    *"$want"*)
      ok "$family -> $found"
      ;;
    *)
      if [ "$required" = "yes" ]; then
        bad "$family not found (fontconfig returned: ${found:-nothing})"
      else
        warn "$family not installed ($hint)"
      fi
      ;;
  esac
}

check() {
  FAILED=0
  echo "Arabic Poem dependency check"
  echo
  echo "Repository : $ROOT"
  echo "Plugin     : $PLUGIN"
  echo
  echo "Commands:"
  if need "$PYTHON"; then
    ok "Python: $($PYTHON --version 2>&1)"
  else
    bad "Python command not found: $PYTHON"
  fi
  if need fc-match; then
    ok "fontconfig: $(command -v fc-match)"
  else
    bad "fontconfig (fc-match) not found"
  fi
  if need fc-cache; then
    ok "fc-cache: $(command -v fc-cache)"
  else
    warn "fc-cache not found; install fontconfig"
  fi
  if need noctalia; then
    ok "Noctalia: $(command -v noctalia)"
  else
    warn "noctalia not on PATH; needed for --source/--enable/--status"
  fi
  if need niri; then
    ok "niri: $(command -v niri)"
  else
    warn "niri not on PATH (any Wayland compositor should work)"
  fi
  if need magick; then
    ok "ImageMagick: $(command -v magick)"
  else
    warn "magick not found (only needed to regenerate previews)"
  fi

  echo
  echo "Python modules:"
  if "$PYTHON" - <<'PY'
import sys
failed = False

try:
    import gi
    gi.require_version("Pango", "1.0")
    gi.require_version("PangoCairo", "1.0")
    from gi.repository import Pango, PangoCairo  # noqa: F401
    print("  ok    PyGObject + Pango + PangoCairo")
except Exception as exc:
    print(f"  fail  PyGObject/Pango: {exc}")
    failed = True

try:
    import cairo  # noqa: F401
    print("  ok    pycairo")
except Exception as exc:
    print(f"  fail  pycairo: {exc}")
    failed = True

try:
    import hijridate  # noqa: F401
    print("  ok    hijridate")
except ImportError:
    try:
        import hijri_converter  # noqa: F401
        print("  ok    hijri_converter (legacy name)")
    except ImportError:
        print("  ok    hijridate not installed; bundled Umm al-Qura fallback will be used")

sys.exit(1 if failed else 0)
PY
  then
    :
  else
    FAILED=1
  fi

  echo
  echo "Fonts:"
  font_state "Amiri Quran" no "bundled; will be installed on first render"
  font_state "Amiri" no "bundled; will be installed on first render"
  font_state "PanoramaNaskh" no
  font_state "Shafigh Bakh Thin MOB V2" no
  font_state "thmanyah serif display" no
  font_state "thmanyah serif text" no

  echo
  if [ "$FAILED" -ne 0 ]; then
    echo "Result: required pieces are missing. Fix the fail lines above, then re-run --check."
    return 1
  fi
  echo "Result: required pieces look good."
  return 0
}

install_fonts() {
  echo "Installing bundled OFL fonts into $FONT_DIR"
  install -d "$FONT_DIR"
  install -m 0644 "$PLUGIN/fonts/Amiri/"*.ttf "$FONT_DIR/"
  install -m 0644 "$PLUGIN/fonts/amiri-quran.ttf" "$FONT_DIR/"
  if need fc-cache; then
    fc-cache -f "$DATA_HOME/fonts" >/dev/null 2>&1 || true
  fi
  echo "Installed:"
  find "$FONT_DIR" -maxdepth 1 -name '*.ttf' -printf '  %f\n' | sort
  echo
  echo "Verify with: fc-match 'Amiri Quran' && fc-match 'Amiri'"
}

preview() {
  echo "Rendering a preview into $PREVIEW_DIR"
  mkdir -p "$PREVIEW_DIR"
  "$PYTHON" "$PLUGIN/renderer/update.py" \
    --plugin-dir "$PLUGIN" \
    --data-dir "$PREVIEW_DIR" \
    --force --notify
  echo
  echo "Preview files:"
  find "$PREVIEW_DIR/render" -maxdepth 1 -name '*.png' -printf '  %p\n' 2>/dev/null | sort
  echo "Metadata: $PREVIEW_DIR/render/render.json"
}

add_source() {
  if ! need noctalia; then
    echo "noctalia is not on PATH; add it first." >&2
    return 1
  fi
  url=${ARABIC_POEM_SOURCE_URL:-https://github.com/Amr-Os/arabic-poem-noctalia.git}
  echo "Adding git source 'arabic-poem' -> $url"
  noctalia msg plugins source add arabic-poem git "$url"
}

add_source_path() {
  if ! need noctalia; then
    echo "noctalia is not on PATH; add it first." >&2
    return 1
  fi
  echo "Adding development path source 'arabic-poem' -> $ROOT"
  noctalia msg plugins source add arabic-poem path "$ROOT"
}

enable_plugin() {
  if ! need noctalia; then
    echo "noctalia is not on PATH; add it first." >&2
    return 1
  fi
  echo "Enabling amr/arabic-poem"
  noctalia msg plugins enable amr/arabic-poem
  echo "Check: noctalia msg plugins list"
}

status() {
  if ! need noctalia; then
    echo "noctalia is not on PATH; add it first." >&2
    return 1
  fi
  echo "Requesting a status notification from the service..."
  noctalia msg plugin amr/arabic-poem:service all status
  echo "If Noctalia notifications are hidden, use the renderer directly with the data directory shown there."
}

all_steps() {
  if ! check; then
    echo
    echo "Stopping before install steps because required pieces are missing." >&2
    return 1
  fi
  install_fonts || return 1
  preview || return 1
  add_source || return 1
  enable_plugin || return 1
  echo
  echo "Done. Add the three desktop widgets with: noctalia msg desktop-widgets-edit"
  echo "See TESTING.md for the friend-run checklist."
}

case "${1:---help}" in
  --check)
    check
    exit $?
    ;;
  --fonts)
    install_fonts
    ;;
  --preview)
    preview
    ;;
  --source)
    add_source
    ;;
  --source-path)
    add_source_path
    ;;
  --enable)
    enable_plugin
    ;;
  --status)
    status
    ;;
  --all)
    all_steps
    ;;
  -h|--help|help)
    usage
    ;;
  *)
    echo "Unknown option: $1" >&2
    usage
    exit 2
    ;;
esac

# Python wrapper for the Arabic Poem renderer on NixOS.
#
# Noctalia launches the renderer as an external process.  On NixOS the plain
# `python3` package does not expose Pango/PangoCairo's GObject Introspection
# typelibs, so `gi.require_version("Pango", "1.0")` fails with "Namespace Pango
# not available".  This wrapper provides both the Python packages and the
# typelib search path.
{ pkgs ? import <nixpkgs> { } }:
let
  python = pkgs.python3.withPackages (ps: with ps; [
    pygobject3
    pycairo
  ]);

  giTypelibPath = pkgs.lib.makeSearchPath "lib/girepository-1.0" [
    pkgs.pango
    pkgs.cairo
    pkgs.gobject-introspection
    pkgs.glib
  ];

  runtimeLibs = [
    pkgs.pango
    pkgs.cairo
    pkgs.glib
    pkgs.harfbuzz
    pkgs.freetype
    pkgs.fontconfig
    pkgs.gobject-introspection
  ];
in
pkgs.writeShellScriptBin "arabic-poem-python" ''
  export PATH=${pkgs.lib.makeBinPath [ pkgs.fontconfig ]}:$PATH
  export GI_TYPELIB_PATH=${giTypelibPath}''${GI_TYPELIB_PATH:+:$GI_TYPELIB_PATH}
  export LD_LIBRARY_PATH=${pkgs.lib.makeLibraryPath runtimeLibs}''${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}
  exec ${python}/bin/python3 "$@"
''

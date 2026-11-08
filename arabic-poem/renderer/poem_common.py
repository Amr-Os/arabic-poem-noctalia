#!/usr/bin/env python3
"""Shared helpers for the Noctalia Arabic Poem plugin.

This module deliberately has no GNOME/azclock dependency.  It only knows about
JSON files, the poem corpus, font discovery, connectivity, and rotation state.
"""
from __future__ import annotations

import json
import os
import random
import re
import shutil
import subprocess
import unicodedata
import urllib.request
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

HOME = Path.home()
DEFAULT_DATA_DIR = HOME / ".local/share/arabic-poem"
DEFAULT_FONT = "Amiri Quran"
FALLBACK_FONT = "Amiri"

DEFAULT_CONFIG: dict[str, Any] = {
    "config_version": 2,
    # Rotation
    "interval_hours": 4,
    # Poem typography
    "font_size_pt": 31.25,
    "max_width_px": 820,
    "tashkeel": "light",
    "layout": "columns",
    "column_gap_px": 12,
    "separator_size_pct": 85,
    "attribution_size_pct": 60,
    "separator": "۞",
    "separator_color": "#c9a96a",
    "attribution_color": "#cfc3a8",
    "verse_color": "#f5efe2",
    "three_verse_scale": 0.92,
    "min_scale": 0.54,
    "max_scale": 1.0,
    "verse_fonts": [
        "Amiri Quran",
        "Amiri",
        "PanoramaNaskh",
        "Shafigh Bakh Thin MOB V2",
    ],
    "attribution_font": "thmanyah serif display",
    "show_attribution": True,
    "attribution_format": "— {poet} · {source}",
    # Canvas / image output
    "render_scale": 2.0,
    "poem_width": 880,
    "poem_height": 380,
    "poem_padding": 24,
    "poem_align": "right",
    "poem_valign": "top",
    "weekday_width": 700,
    "weekday_height": 140,
    "weekday_padding": 24,
    "weekday_align": "left",
    "weekday_valign": "bottom",
    "weekday_font": "thmanyah serif display",
    "weekday_size_pt": 60,
    "weekday_color": "#f5e5d8",
    "date_width": 700,
    "date_height": 120,
    "date_padding": 24,
    "date_align": "left",
    "date_valign": "bottom",
    "date_font": "thmanyah serif text",
    "date_size_pt": 35,
    "date_color": "#f5e5d8",
    "eastern_numerals": True,
    # Shared text shadow
    "shadow_enabled": True,
    "shadow_color": "#000000",
    "shadow_opacity": 0.55,
    "shadow_blur": 3.0,
    "shadow_offset_x": 1.0,
    "shadow_offset_y": 1.0,
    # Connectivity
    "online_timeout_sec": 2.0,
    "online_urls": [
        "https://nmcheck.gnome.org/check_network_status.txt",
        "http://connectivity-check.ubuntu.com/",
    ],
    "fallback_font": FALLBACK_FONT,
    "log_max_bytes": 200_000,
}


def fail(message: str) -> "NoReturn":
    print(f"Error: {message}", flush=True)
    raise SystemExit(1)


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def load_json(path: Path, default: Any) -> Any:
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return default
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Warning: could not read {path}: {exc}", flush=True)
        return default


def save_json(path: Path, data: Any) -> None:
    """Atomically replace a JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp.{os.getpid()}")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    os.replace(tmp, path)


def _default_config_from_plugin(plugin_dir: Path | None) -> dict[str, Any]:
    config = dict(DEFAULT_CONFIG)
    if plugin_dir is not None:
        loaded = load_json(plugin_dir / "data" / "config.default.json", None)
        if isinstance(loaded, dict):
            config.update(loaded)
    return config


def load_config(
    plugin_dir: Path | None,
    data_dir: Path,
    *,
    create: bool = True,
) -> dict[str, Any]:
    """Load the user's config, falling back to the bundled defaults.

    The first run copies the merged defaults to ``data_dir/config.json`` so the
    user has one editable file that survives plugin updates.
    """
    config = _default_config_from_plugin(plugin_dir)
    loaded = load_json(data_dir / "config.json", {})
    if isinstance(loaded, dict):
        config.update(loaded)
        # v1 used an 8-hour default.  Move only the untouched old default to
        # the new 4-hour default; a deliberately custom interval is preserved.
        try:
            loaded_version = int(loaded.get("config_version", 1))
        except (TypeError, ValueError):
            loaded_version = 1
        if loaded_version < 2:
            if config.get("interval_hours") == 8:
                config["interval_hours"] = 4
            config["config_version"] = 2
    if create:
        ensure_dir(data_dir)
        save_json(data_dir / "config.json", config)
    return config


def load_corpus(plugin_dir: Path) -> dict[str, Any]:
    path = plugin_dir / "data" / "poems.json"
    corpus = load_json(path, None)
    if not isinstance(corpus, dict) or not isinstance(corpus.get("entries"), list):
        fail(f"corpus not found or invalid: {path}")
    return corpus


def load_state(data_dir: Path) -> dict[str, Any]:
    state = load_json(data_dir / "state.json", {})
    return state if isinstance(state, dict) else {}


def save_state(data_dir: Path, state: dict[str, Any]) -> None:
    save_json(data_dir / "state.json", state)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def enabled_entries(corpus: dict[str, Any]) -> list[dict[str, Any]]:
    return [entry for entry in corpus["entries"] if entry.get("enabled", True)]


def entry_by_id(entries: list[dict[str, Any]], entry_id: str | None) -> dict[str, Any] | None:
    for entry in entries:
        if entry.get("id") == entry_id:
            return entry
    return None


def initial_queue(entries: list[dict[str, Any]], current: str) -> list[str]:
    queue = [entry["id"] for entry in entries if entry["id"] != current]
    random.shuffle(queue)
    return queue


def choose_initial(entries: list[dict[str, Any]], state: dict[str, Any]) -> dict[str, Any]:
    entry = entries[0]
    state["current"] = entry["id"]
    state["queue"] = initial_queue(entries, entry["id"])
    state["last_change"] = now_iso()
    return entry


def choose_next(entries: list[dict[str, Any]], state: dict[str, Any]) -> dict[str, Any]:
    by_id = {entry["id"]: entry for entry in entries}
    ids = list(by_id)
    current = state.get("current")
    queue = [
        item
        for item in state.get("queue", [])
        if isinstance(item, str) and item in by_id and item != current
    ]
    if not queue:
        queue = ids[:]
        random.shuffle(queue)
        if len(queue) > 1 and queue[0] == current:
            queue.append(queue.pop(0))
    nxt = queue.pop(0)
    if nxt == current and len(ids) > 1:
        queue.append(nxt)
        nxt = queue.pop(0)
    state["queue"] = queue
    state["current"] = nxt
    state["last_change"] = now_iso()
    return by_id[nxt]


def due(state: dict[str, Any], interval_hours: float) -> bool:
    last = parse_iso(state.get("last_change"))
    if last is None:
        return True
    return (datetime.now(timezone.utc) - last).total_seconds() >= interval_hours * 3600


def next_due(state: dict[str, Any], interval_hours: float) -> datetime | None:
    last = parse_iso(state.get("last_change"))
    if last is None:
        return None
    return last + timedelta(hours=interval_hours)


# --------------------------------------------------------------------------- #
# Fonts
# --------------------------------------------------------------------------- #
@lru_cache(maxsize=128)
def font_available(family: str) -> bool:
    """Return True when fontconfig resolves ``family`` to itself.

    ``fc-match`` always returns *some* font, so comparing the returned family
    name is the important part.  If fontconfig is unavailable we return False
    and let the caller fall back.
    """
    family = (family or "").strip()
    if not family:
        return False
    try:
        result = subprocess.run(
            ["fc-match", "-f", "%{family}", family],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception:
        return False
    if result.returncode != 0:
        return False
    found = result.stdout.strip().lower()
    wanted = family.lower()
    # Generic names such as "sans" are intentionally treated as available.
    return wanted in found or wanted in {"sans", "serif", "monospace"}


def ensure_bundled_fonts(plugin_dir: Path) -> list[str]:
    """Install the bundled OFL fonts when fontconfig cannot find them.

    A Noctalia UI install only exports the plugin directory; it does not run
    ``install.sh``.  Copying the fonts into the user font directory on first
    render keeps the UI-only installation path self-contained.
    """
    required = ("Amiri Quran", "Amiri")
    if all(font_available(name) for name in required):
        return []

    source_dir = plugin_dir / "fonts"
    sources = [source_dir / "amiri-quran.ttf"]
    sources.extend(sorted((source_dir / "Amiri").glob("*.ttf")))
    sources = [path for path in sources if path.is_file()]
    if not sources:
        return []

    data_home = Path(os.environ.get("XDG_DATA_HOME", str(HOME / ".local/share")))
    font_dir = data_home / "fonts" / "Amiri"
    try:
        ensure_dir(font_dir)
        for source in sources:
            destination = font_dir / source.name
            try:
                if (
                    not destination.exists()
                    or destination.stat().st_size != source.stat().st_size
                ):
                    shutil.copy2(source, destination)
            except OSError:
                pass
        try:
            subprocess.run(
                ["fc-cache", "-f", str(font_dir.parent)],
                check=False,
                capture_output=True,
                timeout=20,
            )
        except Exception:
            pass
        getattr(font_available, "cache_clear", lambda: None)()
        return [name for name in required if font_available(name)]
    except OSError:
        return []


def resolve_font(family: str, fallback: str | None = None) -> str:
    """Return ``family`` if installed, otherwise the best Arabic fallback."""
    family = (family or "").strip()
    if family and font_available(family):
        return family
    fallback = (fallback or FALLBACK_FONT).strip()
    if fallback and font_available(fallback):
        return fallback
    for candidate in (
        "Amiri",
        "Noto Naskh Arabic",
        "Noto Sans Arabic",
        "DejaVu Sans",
        "sans",
    ):
        if font_available(candidate):
            return candidate
    return family or "sans"


def font_pool(config: dict[str, Any]) -> list[str]:
    """Configured verse fonts that are actually installed, de-duplicated."""
    fonts = config.get("verse_fonts")
    if not isinstance(fonts, list):
        fonts = [DEFAULT_FONT]
    pool: list[str] = []
    for font in fonts:
        if not isinstance(font, str):
            continue
        name = font.strip()
        if name and name not in pool and font_available(name):
            pool.append(name)
    if not pool:
        pool.append(resolve_font(str(config.get("fallback_font", FALLBACK_FONT))))
    return pool


def choose_initial_font(config: dict[str, Any], state: dict[str, Any]) -> str:
    fonts = font_pool(config)
    current = state.get("font")
    if current not in fonts:
        current = fonts[0]
    state["font"] = current
    rest = [font for font in fonts if font != current]
    random.shuffle(rest)
    state["font_queue"] = rest
    return current


def choose_next_font(config: dict[str, Any], state: dict[str, Any]) -> str:
    fonts = font_pool(config)
    current = state.get("font")
    if current not in fonts:
        return choose_initial_font(config, state)
    queue = [
        font
        for font in state.get("font_queue", [])
        if isinstance(font, str) and font in fonts and font != current
    ]
    if not queue:
        queue = [font for font in fonts if font != current]
        random.shuffle(queue)
        if not queue:
            queue = [current]
    nxt = queue.pop(0)
    state["font"] = nxt
    state["font_queue"] = queue
    return nxt


# --------------------------------------------------------------------------- #
# Text / connectivity / files
# --------------------------------------------------------------------------- #
_TASHKEEL_RE = re.compile(
    r"[\u0610-\u061a\u064b-\u065f\u0670\u06d6-\u06ed\u08d3-\u08e1\u08e3-\u08ff]"
)


def strip_tashkeel(text: str) -> str:
    return unicodedata.normalize("NFC", _TASHKEEL_RE.sub("", text))


def is_online(config: dict[str, Any]) -> bool:
    timeout = float(config.get("online_timeout_sec", 2.0))
    try:
        result = subprocess.run(
            ["nmcli", "-t", "-f", "CONNECTIVITY", "general"],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode == 0 and result.stdout.strip().lower() == "full":
            return True
    except Exception:
        pass

    urls = config.get("online_urls")
    if not isinstance(urls, list):
        urls = DEFAULT_CONFIG["online_urls"]
    for url in urls:
        if not isinstance(url, str) or not url:
            continue
        try:
            request = urllib.request.Request(
                url,
                headers={"User-Agent": "arabic-poem-noctalia/1.0"},
            )
            with urllib.request.urlopen(request, timeout=timeout) as response:
                if 200 <= getattr(response, "status", 200) < 400:
                    return True
        except Exception:
            continue
    return False


def log(data_dir: Path, message: str, config: dict[str, Any] | None = None) -> None:
    """Append one line to render.log, rotating the file when it gets large."""
    try:
        ensure_dir(data_dir)
        path = data_dir / "render.log"
        max_bytes = int((config or {}).get("log_max_bytes", 200_000))
        if path.exists() and path.stat().st_size > max_bytes:
            path.replace(path.with_suffix(".log.old"))
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(f"{stamp} {message}\n")
    except Exception:
        # Logging must never break rendering.
        pass


def cleanup_versions(directory: Path, prefix: str, keep: int = 3) -> None:
    """Keep the newest ``keep`` PNGs for one widget."""
    try:
        files = sorted(
            directory.glob(f"{prefix}-*.png"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        for old in files[keep:]:
            old.unlink(missing_ok=True)
    except Exception:
        pass


def write_surface(surface: Any, path: Path) -> None:
    """Write a cairo surface atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp.{os.getpid()}")
    surface.write_to_png(str(tmp))
    os.replace(tmp, path)

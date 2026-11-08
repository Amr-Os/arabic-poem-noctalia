#!/usr/bin/env python3
"""Render the Noctalia Arabic Poem, weekday, and Hijri date widgets.

The renderer writes transparent PNGs plus a small ``render.json`` metadata
file.  Noctalia's Luau entries only display those images, so all Arabic
shaping, justification, and font selection happens here in Pango.

Default mode (used by the Noctalia service):
  * If no poem has been shown yet, show the first one.
  * If 4 hours have passed AND the machine is online, show the next poem.
  * If offline, keep the current poem and retry on the next service tick.
  * Each new poem also gets a new font from ``verse_fonts``.

Options:
  --if-due     rotate only when due and online (default)
  --force      rotate now, ignoring interval and connectivity
  --refresh    re-render the current poem and date (do not rotate)
  --date-only  re-render only the weekday/date tiles
  --test       print the selection and scale without writing
  --status     print rotation state and render metadata
  --dump       with --test, print the raw Pango markup
"""
from __future__ import annotations

import argparse
import copy
import fcntl
import math
import re
import sys
import unicodedata
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

import cairo
import gi

gi.require_version("Pango", "1.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Pango, PangoCairo  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import poem_common as pc  # noqa: E402

try:
    import date_strings as ds  # noqa: E402
except ImportError as exc:  # friendly dependency error
    print(f"Error: {exc}", flush=True)
    raise SystemExit(1)


# --------------------------------------------------------------------------- #
# Cairo / Pango helpers
# --------------------------------------------------------------------------- #
def _hex_to_rgb(value: str) -> tuple[float, float, float]:
    value = str(value or "#000000").strip()
    if value.startswith("#"):
        value = value[1:]
    if len(value) == 3:
        value = "".join(ch * 2 for ch in value)
    if len(value) != 6:
        value = "000000"
    try:
        return tuple(int(value[i : i + 2], 16) / 255.0 for i in (0, 2, 4))  # type: ignore[return-value]
    except ValueError:
        return (0.0, 0.0, 0.0)


def _new_surface(width: float, height: float, render_scale: float):
    pixel_w = max(1, int(round(width * render_scale)))
    pixel_h = max(1, int(round(height * render_scale)))
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, pixel_w, pixel_h)
    cr = cairo.Context(surface)
    cr.set_operator(cairo.OPERATOR_CLEAR)
    cr.paint()
    cr.set_operator(cairo.OPERATOR_OVER)
    cr.scale(render_scale, render_scale)
    return surface, cr


def _markup_layout(cr: cairo.Context, markup: str, family: str, size: float):
    layout = PangoCairo.create_layout(cr)
    desc = Pango.FontDescription()
    desc.set_family(family)
    desc.set_size(int(round(size * Pango.SCALE)))
    layout.set_font_description(desc)
    layout.set_markup(markup, -1)
    layout.set_width(-1)
    layout.set_auto_dir(True)
    return layout


def _plain_layout(cr: cairo.Context, text: str, family: str, size: float):
    layout = PangoCairo.create_layout(cr)
    desc = Pango.FontDescription()
    desc.set_family(family)
    desc.set_size(int(round(size * Pango.SCALE)))
    layout.set_font_description(desc)
    layout.set_text(text, -1)
    layout.set_width(-1)
    layout.set_auto_dir(True)
    return layout


def measure(markup: str, family: str, size: float) -> tuple[int, int]:
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 8, 8)
    cr = cairo.Context(surface)
    layout = _markup_layout(cr, markup, family, size)
    return layout.get_pixel_size()


# --------------------------------------------------------------------------- #
# Poem markup / justification (ported from the GNOME renderer)
# --------------------------------------------------------------------------- #
def verse_pair(verse: dict, mode: str) -> list[str]:
    if mode == "full":
        return verse["full"]
    if mode == "light":
        return verse.get("light") or verse["full"]
    return [pc.strip_tashkeel(text) for text in verse["full"]]


NBSP = "\u00a0"
ZWSP = "\u200b"
TATWEEL = "\u0640"

# Letters that can connect to the following letter.  Tatweel may only be
# inserted after one of these and before a letter that accepts a right join.
DUAL_JOIN = set("بتثجحخسشصضطظعغفقكلمنهيئ")
NON_JOIN = set("ء")


def _sep_markup(config: dict, verse_pct: int) -> str:
    sep = escape(str(config.get("separator", "۞")))
    sep_color = quoteattr(str(config.get("separator_color", "#c9a96a")))
    sep_pct = max(
        1,
        int(round(verse_pct * float(config.get("separator_size_pct", 85)) / 100)),
    )
    return f'<span foreground={sep_color} size="{sep_pct}%">{sep}</span>'


def _space_width(ch: str, family: str, size: float) -> int:
    base = measure("||", family, size)[0]
    spaced = measure("|" + ch + "|", family, size)[0]
    return max(1, spaced - base)


def _text_width(text: str, family: str, size: float) -> int:
    return measure(escape(text), family, size)[0]


def _text_width_at(text: str, family: str, size: float, pct: int) -> int:
    return measure(f'<span size="{pct}%">{escape(text)}</span>', family, size)[0]


def _markup_width_at(markup: str, family: str, size: float, pct: int) -> int:
    return measure(f'<span size="{pct}%">{markup}</span>', family, size)[0]


def _gap_markup(
    config: dict,
    family: str,
    size: float,
    verse_pct: int,
    nbsp_w: int,
) -> str:
    gap_n = max(
        1,
        int(round(float(config.get("column_gap_px", 12)) / max(1, nbsp_w))),
    )
    return NBSP * gap_n + _sep_markup(config, verse_pct) + NBSP * gap_n


def _column_geometry(
    entry: dict,
    config: dict,
    family: str,
    size: float,
) -> tuple[int, int]:
    mode = config.get("tashkeel", "light")
    if mode not in ("light", "full", "none"):
        mode = "light"
    widths: list[int] = []
    for verse in entry["verses"]:
        sadr, ajuz = verse_pair(verse, mode)
        widths.append(_text_width(sadr, family, size))
        widths.append(_text_width(ajuz, family, size))
    return max(widths) if widths else 0, _space_width(NBSP, family, size)


def _is_mark(ch: str) -> bool:
    return unicodedata.combining(ch) != 0


def _clusters(text: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for ch in text:
        if _is_mark(ch) and out:
            out[-1] = (out[-1][0] + ch, out[-1][1])
        else:
            out.append((ch, ch))
    return out


def _tatweel_boundaries(text: str) -> tuple[list[tuple[str, str]], list[int]]:
    clusters = _clusters(text)
    boundaries: list[int] = []
    for i in range(len(clusters) - 1):
        prev = clusters[i][1]
        nxt = clusters[i + 1][1]
        if (
            prev in DUAL_JOIN
            and nxt not in NON_JOIN
            and "\u0600" <= nxt <= "\u06ff"
            and not _is_mark(nxt)
        ):
            boundaries.append(i)
    return clusters, boundaries


def _even_positions(count: int, size: int) -> list[int]:
    if count <= 0 or size <= 0:
        return []
    if count >= size:
        return list(range(size))
    if count == 1:
        return [size // 2]
    chosen = sorted({int(round(i * (size - 1) / (count - 1))) for i in range(count)})
    i = 0
    while len(chosen) < count:
        if i not in chosen:
            chosen.append(i)
        i += 1
    return sorted(chosen)


def _tatweel_counts(boundaries: int, total: int) -> list[int]:
    if boundaries <= 0 or total <= 0:
        return [0] * max(0, boundaries)
    base, extra = divmod(total, boundaries)
    counts = [base] * boundaries
    for i in _even_positions(extra, boundaries):
        counts[i] += 1
    return counts


def _insert_tatweels(
    clusters: list[tuple[str, str]],
    boundaries: list[int],
    counts: list[int],
) -> str:
    by_boundary = dict(zip(boundaries, counts))
    pieces: list[str] = []
    for i, (piece, _base) in enumerate(clusters):
        pieces.append(piece)
        count = by_boundary.get(i, 0)
        if count:
            pieces.append(TATWEEL * count)
    return "".join(pieces)


def _justify(
    text: str,
    target: int,
    family: str,
    size: float,
    pct: int,
    base_width: int | None = None,
) -> tuple[str, int]:
    """Stretch one hemistich to ``target`` px with tatweel and word spacing."""
    width = (
        base_width
        if base_width is not None
        else _text_width_at(text, family, size, pct)
    )
    if target <= width:
        return escape(text), width

    clusters, boundaries = _tatweel_boundaries(text)
    stretched = text
    if boundaries:
        lo, hi = 0, max(8, len(boundaries) * 12)
        best_k, best_w = 0, width
        while lo <= hi:
            mid = (lo + hi) // 2
            candidate = _insert_tatweels(
                clusters, boundaries, _tatweel_counts(len(boundaries), mid)
            )
            candidate_w = _text_width_at(candidate, family, size, pct)
            if candidate_w <= target:
                best_k, best_w = mid, candidate_w
                lo = mid + 1
            else:
                hi = mid - 1
        if best_k:
            stretched = _insert_tatweels(
                clusters,
                boundaries,
                _tatweel_counts(len(boundaries), best_k),
            )
            width = best_w

    parts = stretched.split(" ")
    gaps = len(parts) - 1
    if width < target and gaps > 0:
        units = int(round((target - width) / gaps * Pango.SCALE))
        space = f'<span letter_spacing="{units}"> </span>'
        markup = space.join(escape(part) for part in parts)
        markup_w = _markup_width_at(markup, family, size, pct)
        for _ in range(3):
            delta = int(round((target - markup_w) / gaps * Pango.SCALE))
            if delta == 0:
                break
            units += delta
            space = f'<span letter_spacing="{units}"> </span>'
            markup = space.join(escape(part) for part in parts)
            markup_w = _markup_width_at(markup, family, size, pct)
    else:
        markup = escape(stretched)
        markup_w = width

    if markup_w < target:
        residual = int(round((target - markup_w) * Pango.SCALE))
        markup += f'<span letter_spacing="{residual}">{ZWSP}</span>'
        markup_w = _markup_width_at(markup, family, size, pct)
    return markup, markup_w


def make_markup(
    entry: dict,
    config: dict,
    family: str,
    size: float,
    scale: float,
) -> str:
    mode = config.get("tashkeel", "light")
    if mode not in ("light", "full", "none"):
        mode = "light"
    verse_pct = max(1, int(round(scale * 100)))
    layout = str(config.get("layout", "columns"))
    lines: list[str] = []
    if layout == "columns":
        column_w, nbsp_w = _column_geometry(entry, config, family, size)
        gap = _gap_markup(config, family, size, verse_pct, nbsp_w)
        rows = []
        for verse in entry["verses"]:
            sadr, ajuz = verse_pair(verse, mode)
            rows.append(
                (
                    sadr,
                    ajuz,
                    _text_width_at(sadr, family, size, verse_pct),
                    _text_width_at(ajuz, family, size, verse_pct),
                )
            )
        target = max(
            [int(round(column_w * scale))]
            + [sw for _s, _a, sw, _aw in rows]
            + [aw for _s, _a, _sw, aw in rows]
        )
        for sadr, ajuz, sw, aw in rows:
            sadr_markup, _sadr_w = _justify(
                sadr, target, family, size, verse_pct, sw
            )
            ajuz_markup, _ajuz_w = _justify(
                ajuz, target, family, size, verse_pct, aw
            )
            lines.append(
                f'<span size="{verse_pct}%">'
                f"{sadr_markup}{gap}{ajuz_markup}"
                f"</span>"
            )
    else:
        sep = escape(str(config.get("separator", "۞")))
        sep_color = quoteattr(str(config.get("separator_color", "#c9a96a")))
        sep_pct = max(
            1,
            int(round(verse_pct * float(config.get("separator_size_pct", 85)) / 100)),
        )
        for verse in entry["verses"]:
            sadr, ajuz = verse_pair(verse, mode)
            lines.append(
                f'<span size="{verse_pct}%">'
                f"{escape(sadr)} "
                f'<span foreground={sep_color} size="{sep_pct}%">{sep}</span> '
                f"{escape(ajuz)}"
                f"</span>"
            )
    if config.get("show_attribution", True):
        attr = str(config.get("attribution_format", "— {poet} · {source}")).format(
            poet=entry.get("poet", ""), source=entry.get("source", "")
        )
        attr_pct = max(
            50,
            int(round(float(config.get("attribution_size_pct", 60)) * scale)),
        )
        attr_font = pc.resolve_font(
            str(config.get("attribution_font", "thmanyah serif display")),
            str(config.get("fallback_font", pc.FALLBACK_FONT)),
        )
        attr_color = quoteattr(str(config.get("attribution_color", "#cfc3a8")))
        lines.append(
            f"<span font_family={quoteattr(attr_font)} size=\"{attr_pct}%\" "
            f"foreground={attr_color}>{escape(attr)}</span>"
        )
    return "\n".join(lines)


def compute_scale(
    entry: dict,
    config: dict,
    family: str,
    size: float,
) -> tuple[float, str, int, int]:
    base_scale = (
        float(config.get("three_verse_scale", 0.92))
        if len(entry["verses"]) >= 3
        else 1.0
    )
    max_scale = float(config.get("max_scale", 1.0))
    min_scale = float(config.get("min_scale", 0.54))
    max_width = int(config.get("max_width_px", 820))
    probe = make_markup(entry, config, family, size, 1.0)
    width, height = measure(probe, family, size)
    if width <= 0:
        return base_scale, probe, width, height
    fit = min(1.0, max_width / (width * base_scale)) if width * base_scale > 0 else 1.0
    scale = max(min_scale, min(max_scale, base_scale * fit))
    markup = make_markup(entry, config, family, size, scale)
    out_w, out_h = measure(markup, family, size)
    for _ in range(3):
        if out_w <= max_width or scale <= min_scale:
            break
        next_scale = max(min_scale, scale * max_width / out_w * 0.995)
        if next_scale >= scale:
            break
        scale = next_scale
        markup = make_markup(entry, config, family, size, scale)
        out_w, out_h = measure(markup, family, size)
    return scale, markup, out_w, out_h


# --------------------------------------------------------------------------- #
# Shadow / placement
# --------------------------------------------------------------------------- #
def _shadow_samples(config: dict) -> list[tuple[float, float, float]]:
    if not bool(config.get("shadow_enabled", True)):
        return []
    opacity = max(0.0, min(1.0, float(config.get("shadow_opacity", 0.55))))
    if opacity <= 0:
        return []
    ox = float(config.get("shadow_offset_x", 1.0))
    oy = float(config.get("shadow_offset_y", 1.0))
    blur = max(0.0, float(config.get("shadow_blur", 3.0)))
    samples: list[tuple[float, float, float]] = [(ox, oy, 1.0)]
    if blur > 0:
        for radius, weight in (
            (blur * 0.5, 0.55),
            (blur, 0.30),
            (blur * 1.5, 0.15),
        ):
            if radius <= 0:
                continue
            for i in range(8):
                angle = 2 * math.pi * i / 8
                samples.append(
                    (
                        ox + math.cos(angle) * radius,
                        oy + math.sin(angle) * radius,
                        weight / 8,
                    )
                )
    total = sum(weight for _dx, _dy, weight in samples) or 1.0
    return [(dx, dy, opacity * weight / total) for dx, dy, weight in samples]


def _draw_shadow(
    cr: cairo.Context,
    layout,
    x: float,
    y: float,
    config: dict,
    *,
    plain: bool = False,
) -> None:
    samples = _shadow_samples(config)
    if not samples:
        return
    shadow_rgb = _hex_to_rgb(str(config.get("shadow_color", "#000000")))
    for dx, dy, alpha in samples:
        if alpha <= 0:
            continue
        cr.save()
        cr.push_group()
        if plain:
            cr.set_source_rgba(*shadow_rgb, 1.0)
        cr.move_to(x + dx, y + dy)
        PangoCairo.show_layout(cr, layout)
        cr.pop_group_to_source()
        cr.paint_with_alpha(alpha)
        cr.restore()


def _shadow_markup(markup: str, color: str) -> str:
    return re.sub(r'foreground="[^"]*"', f'foreground="{color}"', markup)


def _anchor(
    canvas_w: float,
    canvas_h: float,
    width: float,
    height: float,
    padding: float,
    align: str,
    valign: str,
) -> tuple[float, float]:
    align = str(align or "left").lower()
    valign = str(valign or "top").lower()
    if align == "right":
        x = canvas_w - width - padding
    elif align == "center":
        x = (canvas_w - width) / 2
    else:
        x = padding
    if valign == "bottom":
        y = canvas_h - height - padding
    elif valign in ("middle", "center"):
        y = (canvas_h - height) / 2
    else:
        y = padding
    return x, y


# --------------------------------------------------------------------------- #
# PNG rendering
# --------------------------------------------------------------------------- #
def render_poem(
    entry: dict,
    config: dict,
    family: str,
    size: float,
    data_dir: Path,
) -> dict:
    scale, markup, text_w, text_h = compute_scale(entry, config, family, size)
    canvas_w = float(config.get("poem_width", 880))
    canvas_h = float(config.get("poem_height", 380))
    render_scale = float(config.get("render_scale", 2.0))
    surface, cr = _new_surface(canvas_w, canvas_h, render_scale)

    verse_color = str(config.get("verse_color", "#f5efe2"))
    colored = f"<span foreground={quoteattr(verse_color)}>{markup}</span>"
    layout = _markup_layout(cr, colored, family, size)
    shadow_layout = _markup_layout(
        cr,
        _shadow_markup(colored, str(config.get("shadow_color", "#000000"))),
        family,
        size,
    )
    x, y = _anchor(
        canvas_w,
        canvas_h,
        text_w,
        text_h,
        float(config.get("poem_padding", 24)),
        str(config.get("poem_align", "right")),
        str(config.get("poem_valign", "top")),
    )
    _draw_shadow(cr, shadow_layout, x, y, config)
    cr.move_to(x, y)
    PangoCairo.show_layout(cr, layout)

    stamp = int(datetime.now().timestamp() * 1000)
    path = data_dir / "render" / f"poem-{stamp}.png"
    pc.write_surface(surface, path)
    return {
        "id": entry.get("id"),
        "poet": entry.get("poet"),
        "source": entry.get("source"),
        "theme": entry.get("theme"),
        "verses": len(entry.get("verses", [])),
        "font": family,
        "size_pt": size,
        "scale": round(scale, 4),
        "text_width": text_w,
        "text_height": text_h,
        "png": str(path),
        "width": int(canvas_w),
        "height": int(canvas_h),
        "pixel_width": surface.get_width(),
        "pixel_height": surface.get_height(),
        "mtime": path.stat().st_mtime,
    }


def render_text_tile(
    text: str,
    config: dict,
    *,
    font_key: str,
    size_key: str,
    color_key: str,
    width_key: str,
    height_key: str,
    padding_key: str,
    align_key: str,
    valign_key: str,
    data_dir: Path,
    prefix: str,
) -> dict:
    font = pc.resolve_font(
        str(config.get(font_key, "")),
        str(config.get("fallback_font", pc.FALLBACK_FONT)),
    )
    size = float(config.get(size_key, 35))
    canvas_w = float(config.get(width_key, 700))
    canvas_h = float(config.get(height_key, 120))
    render_scale = float(config.get("render_scale", 2.0))
    surface, cr = _new_surface(canvas_w, canvas_h, render_scale)
    layout = _plain_layout(cr, text, font, size)
    text_w, text_h = layout.get_pixel_size()
    x, y = _anchor(
        canvas_w,
        canvas_h,
        text_w,
        text_h,
        float(config.get(padding_key, 24)),
        str(config.get(align_key, "left")),
        str(config.get(valign_key, "bottom")),
    )
    _draw_shadow(cr, layout, x, y, config, plain=True)
    cr.set_source_rgb(*_hex_to_rgb(str(config.get(color_key, "#f5e5d8"))))
    cr.move_to(x, y)
    PangoCairo.show_layout(cr, layout)

    stamp = int(datetime.now().timestamp() * 1000)
    path = data_dir / "render" / f"{prefix}-{stamp}.png"
    pc.write_surface(surface, path)
    return {
        "text": text,
        "font": font,
        "size_pt": size,
        "png": str(path),
        "width": int(canvas_w),
        "height": int(canvas_h),
        "pixel_width": surface.get_width(),
        "pixel_height": surface.get_height(),
        "mtime": path.stat().st_mtime,
    }


# --------------------------------------------------------------------------- #
# Selection / state
# --------------------------------------------------------------------------- #
def _select_entry(
    entries: list[dict],
    state: dict,
    *,
    force: bool,
    refresh: bool,
    online: bool,
    interval: float,
) -> tuple[dict, bool]:
    current = pc.entry_by_id(entries, state.get("current"))
    if current is None:
        return pc.choose_initial(entries, state), True
    if force:
        return pc.choose_next(entries, state), True
    if refresh:
        return current, False
    if pc.due(state, interval):
        if online:
            return pc.choose_next(entries, state), True
        return current, False
    return current, False


def _select_font(
    config: dict,
    state: dict,
    *,
    changed: bool,
    had_current: bool,
) -> tuple[str, bool]:
    old = state.get("font")
    if changed and had_current:
        family = pc.choose_next_font(config, state)
    elif not changed and old in pc.font_pool(config):
        family = str(old)
    else:
        family = pc.choose_initial_font(config, state)
    return family, state.get("font") != old


def _prev_meta(data_dir: Path) -> dict:
    meta = pc.load_json(data_dir / "render" / "render.json", {})
    return meta if isinstance(meta, dict) else {}


def _has_png(meta: dict, key: str) -> bool:
    item = meta.get(key)
    return (
        isinstance(item, dict)
        and isinstance(item.get("png"), str)
        and Path(item["png"]).exists()
    )


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #
def _status(plugin_dir: Path, data_dir: Path, config: dict, entries: list[dict], state: dict) -> int:
    current = pc.entry_by_id(entries, state.get("current"))
    print(f"Plugin dir : {plugin_dir}")
    print(f"Data dir   : {data_dir}")
    if current:
        print(f"Current    : {current['id']} — {current['poet']} — {current['theme']}")
    else:
        print("Current    : (none)")
    last = pc.parse_iso(state.get("last_change"))
    print(f"Last change: {last.isoformat() if last else '(never)'}")
    due_at = pc.next_due(state, float(config.get("interval_hours", 4)))
    print(f"Due now    : {pc.due(state, float(config.get('interval_hours', 4)))}")
    print(f"Next due   : {due_at.isoformat() if due_at else '(now)'}")
    print(f"Queue      : {len(state.get('queue', []))} pending")
    print(f"Font       : {state.get('font') or '(not chosen yet)'}")
    print(f"Font pool  : {', '.join(pc.font_pool(config))}")
    print(
        f"Config     : tashkeel={config.get('tashkeel')} "
        f"interval={config.get('interval_hours')}h "
        f"max_width={config.get('max_width_px')}px"
    )
    meta = _prev_meta(data_dir)
    if meta:
        poem = meta.get("poem") or {}
        weekday = meta.get("weekday") or {}
        date = meta.get("date") or {}
        print(f"Rendered   : {meta.get('generated', '(unknown)')}")
        print(f"Poem PNG   : {poem.get('png', '(none)')}")
        print(f"Weekday    : {weekday.get('text', '(none)')}")
        print(f"Date       : {date.get('text', '(none)')}")
    else:
        print("Rendered   : (none)")
    return 0


def _test(
    plugin_dir: Path,
    data_dir: Path,
    config: dict,
    entries: list[dict],
    state: dict,
    args: argparse.Namespace,
) -> int:
    work_state = copy.deepcopy(state)
    had_current = pc.entry_by_id(entries, work_state.get("current")) is not None
    entry, changed = _select_entry(
        entries,
        work_state,
        force=args.force,
        refresh=args.refresh,
        online=True,
        interval=float(config.get("interval_hours", 4)),
    )
    family, _font_changed = _select_font(
        config,
        work_state,
        changed=changed,
        had_current=had_current,
    )
    size = float(config.get("font_size_pt", 31.25))
    scale, markup, width, height = compute_scale(entry, config, family, size)
    print(f"Plugin dir : {plugin_dir}")
    print(f"Data dir   : {data_dir}")
    print(f"Entry      : {entry['id']}")
    print(f"Poet       : {entry['poet']} — {entry['source']}")
    print(f"Theme      : {entry['theme']}")
    print(f"Verses     : {len(entry['verses'])}")
    print(f"Font       : {family} {size:g}pt")
    print(
        f"Scale      : {scale:.2f}  "
        f"(text {width}×{height}px, max {config.get('max_width_px')}px)"
    )
    if width > int(config.get("max_width_px", 820)):
        print("Warning: text is still wider than max_width_px at min_scale.", flush=True)
    strings = ds.get_current_strings(
        eastern_numerals=bool(config.get("eastern_numerals", True))
    )
    print(f"Weekday    : {strings['weekday']}")
    print(f"Hijri date : {strings['date']}")
    print("Text       :")
    for verse in entry["verses"]:
        sadr, ajuz = verse_pair(verse, config.get("tashkeel", "light"))
        print(f"  {sadr} ۞ {ajuz}")
    print(
        "  "
        + str(config.get("attribution_format", "— {poet} · {source}")).format(
            poet=entry["poet"], source=entry["source"]
        )
    )
    if args.dump:
        print("\n--- markup ---")
        print(markup)
    return 0


def _render_date_only(
    data_dir: Path,
    config: dict,
    prev_meta: dict,
    notify: bool = False,
) -> int:
    strings = ds.get_current_strings(
        eastern_numerals=bool(config.get("eastern_numerals", True))
    )
    weekday_meta = render_text_tile(
        strings["weekday"],
        config,
        font_key="weekday_font",
        size_key="weekday_size_pt",
        color_key="weekday_color",
        width_key="weekday_width",
        height_key="weekday_height",
        padding_key="weekday_padding",
        align_key="weekday_align",
        valign_key="weekday_valign",
        data_dir=data_dir,
        prefix="weekday",
    )
    weekday_meta["weekday_index"] = strings["weekday_index"]
    date_meta = render_text_tile(
        strings["date"],
        config,
        font_key="date_font",
        size_key="date_size_pt",
        color_key="date_color",
        width_key="date_width",
        height_key="date_height",
        padding_key="date_padding",
        align_key="date_align",
        valign_key="date_valign",
        data_dir=data_dir,
        prefix="date",
    )
    date_meta.update(
        {
            "date_iso": strings["date_iso"],
            "hijri_year": strings["hijri_year"],
            "hijri_month": strings["hijri_month"],
            "hijri_day": strings["hijri_day"],
        }
    )
    meta = {
        "version": 1,
        "generated": pc.now_iso(),
        "poem": prev_meta.get("poem"),
        "weekday": weekday_meta,
        "date": date_meta,
        "state": prev_meta.get("state") or {},
    }
    pc.save_json(data_dir / "render" / "render.json", meta)
    pc.cleanup_versions(data_dir / "render", "weekday")
    pc.cleanup_versions(data_dir / "render", "date")
    pc.log(data_dir, f"date-only: {strings['date_iso']} {strings['weekday']}", config)
    if notify:
        print(f"Date updated: {strings['date_iso']} (weekday {strings['weekday_index']})", flush=True)
    else:
        print(f"Date updated: {strings['date_iso']} ({strings['weekday']})", flush=True)
    return 0


def _render(
    data_dir: Path,
    config: dict,
    entries: list[dict],
    state: dict,
    args: argparse.Namespace,
) -> int:
    prev_meta = _prev_meta(data_dir)
    interval = float(config.get("interval_hours", 4))

    if args.date_only:
        return _render_date_only(data_dir, config, prev_meta, notify=args.notify)

    due_now = pc.due(state, interval)
    online = False
    if due_now and not args.force and not args.refresh:
        online = pc.is_online(config)
        if not online:
            print("Offline: keeping the current poem.", flush=True)
            pc.log(data_dir, "offline: keeping current poem", config)

    had_current = pc.entry_by_id(entries, state.get("current")) is not None
    entry, changed = _select_entry(
        entries,
        state,
        force=args.force,
        refresh=args.refresh,
        online=online,
        interval=interval,
    )
    family, font_changed = _select_font(
        config,
        state,
        changed=changed,
        had_current=had_current,
    )
    if changed or font_changed:
        pc.save_state(data_dir, state)

    poem_meta = prev_meta.get("poem")
    need_poem = (
        args.force
        or args.refresh
        or changed
        or font_changed
        or not _has_png(prev_meta, "poem")
    )
    if need_poem:
        poem_meta = render_poem(
            entry,
            config,
            family,
            float(config.get("font_size_pt", 31.25)),
            data_dir,
        )

    strings = ds.get_current_strings(
        eastern_numerals=bool(config.get("eastern_numerals", True))
    )
    old_weekday = prev_meta.get("weekday") if isinstance(prev_meta.get("weekday"), dict) else {}
    old_date = prev_meta.get("date") if isinstance(prev_meta.get("date"), dict) else {}
    need_weekday = (
        args.force
        or args.refresh
        or not _has_png(prev_meta, "weekday")
        or old_weekday.get("text") != strings["weekday"]
    )
    need_date = (
        args.force
        or args.refresh
        or not _has_png(prev_meta, "date")
        or old_date.get("text") != strings["date"]
    )

    weekday_meta = old_weekday if not need_weekday else None
    date_meta = old_date if not need_date else None
    if need_weekday:
        weekday_meta = render_text_tile(
            strings["weekday"],
            config,
            font_key="weekday_font",
            size_key="weekday_size_pt",
            color_key="weekday_color",
            width_key="weekday_width",
            height_key="weekday_height",
            padding_key="weekday_padding",
            align_key="weekday_align",
            valign_key="weekday_valign",
            data_dir=data_dir,
            prefix="weekday",
        )
        weekday_meta["weekday_index"] = strings["weekday_index"]
    if need_date:
        date_meta = render_text_tile(
            strings["date"],
            config,
            font_key="date_font",
            size_key="date_size_pt",
            color_key="date_color",
            width_key="date_width",
            height_key="date_height",
            padding_key="date_padding",
            align_key="date_align",
            valign_key="date_valign",
            data_dir=data_dir,
            prefix="date",
        )
        date_meta.update(
            {
                "date_iso": strings["date_iso"],
                "hijri_year": strings["hijri_year"],
                "hijri_month": strings["hijri_month"],
                "hijri_day": strings["hijri_day"],
            }
        )

    if not (need_poem or need_weekday or need_date or not prev_meta):
        print("Nothing to update.", flush=True)
        return 0

    meta = {
        "version": 1,
        "generated": pc.now_iso(),
        "poem": poem_meta,
        "weekday": weekday_meta,
        "date": date_meta,
        "state": {
            "current": state.get("current"),
            "font": state.get("font"),
            "last_change": state.get("last_change"),
        },
    }
    pc.save_json(data_dir / "render" / "render.json", meta)
    pc.cleanup_versions(data_dir / "render", "poem")
    pc.cleanup_versions(data_dir / "render", "weekday")
    pc.cleanup_versions(data_dir / "render", "date")

    if need_poem:
        action = "rotated" if (changed or args.force) else "refreshed"
        if args.notify:
            print(
                f"Poem {action}: {entry['id']} "
                f"({len(entry['verses'])} verses, {family}, "
                f"scale {float((poem_meta or {}).get('scale', 0.0)):.2f})",
                flush=True,
            )
        else:
            print(
                f"Poem {action}: {entry['id']} — {entry['poet']} "
                f"({len(entry['verses'])} verses, {family}, "
                f"scale {float((poem_meta or {}).get('scale', 0.0)):.2f})",
                flush=True,
            )
        pc.log(
            data_dir,
            f"poem {action}: {entry['id']} font={family}",
            config,
        )
    else:
        print(f"Poem unchanged: {entry['id']} ({family})", flush=True)
    if need_weekday or need_date:
        if args.notify:
            print(f"Date updated: {strings['date_iso']} (weekday {strings['weekday_index']})", flush=True)
        else:
            print(f"Date updated: {strings['date_iso']} ({strings['weekday']})", flush=True)
        pc.log(data_dir, f"date: {strings['date_iso']} {strings['weekday']}", config)
    return 0


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--plugin-dir",
        type=Path,
        default=None,
        help="the arabic-poem plugin directory (default: parent of renderer/)",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        help="persistent Noctalia plugin data directory",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--force",
        action="store_true",
        help="rotate now, ignoring interval and connectivity",
    )
    group.add_argument(
        "--refresh",
        action="store_true",
        help="re-render the current poem and date",
    )
    group.add_argument(
        "--status",
        action="store_true",
        help="print rotation state and render metadata",
    )
    parser.add_argument(
        "--if-due",
        action="store_true",
        help="rotate only when due and online (default)",
    )
    parser.add_argument(
        "--notify",
        action="store_true",
        help="print concise English-only messages for Noctalia notifications",
    )
    parser.add_argument(
        "--date-only",
        action="store_true",
        help="re-render only the weekday/date tiles",
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="show the selection without writing",
    )
    parser.add_argument(
        "--dump",
        action="store_true",
        help="with --test, print raw Pango markup",
    )
    args = parser.parse_args(argv)

    plugin_dir = (
        args.plugin_dir
        if args.plugin_dir is not None
        else Path(__file__).resolve().parents[1]
    ).expanduser().resolve()
    data_dir = (
        args.data_dir if args.data_dir is not None else pc.DEFAULT_DATA_DIR
    ).expanduser().resolve()

    create = not (args.status or args.test)
    if create:
        installed_fonts = pc.ensure_bundled_fonts(plugin_dir)
        if installed_fonts:
            print(
                "Installed bundled fonts: " + ", ".join(installed_fonts),
                flush=True,
            )
    config = pc.load_config(plugin_dir, data_dir, create=create)
    corpus = pc.load_corpus(plugin_dir)
    entries = pc.enabled_entries(corpus)
    if not entries:
        pc.fail("the corpus has no enabled entries")
    state = pc.load_state(data_dir)

    if args.status:
        return _status(plugin_dir, data_dir, config, entries, state)
    if args.test:
        return _test(plugin_dir, data_dir, config, entries, state, args)

    pc.ensure_dir(data_dir)
    pc.ensure_dir(data_dir / "render")
    lock_path = data_dir / "render.lock"
    with open(lock_path, "w", encoding="utf-8") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("Another render is already running.", flush=True)
            return 0
        try:
            return _render(data_dir, config, entries, state, args)
        except Exception as exc:
            pc.log(data_dir, f"ERROR: {exc!r}", config)
            print(f"Error: {exc}", file=sys.stderr, flush=True)
            return 1


if __name__ == "__main__":
    raise SystemExit(main())

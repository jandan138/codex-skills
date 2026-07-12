#!/usr/bin/env python3
"""Render a v1 scientific figure specification into canonical SVG."""

from __future__ import annotations

import argparse
import base64
import html
import json
import math
import mimetypes
import re
import sys
from pathlib import Path
from typing import Any


def esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def safe_id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", value)


def merge_theme(default: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(default)
    merged.update({k: v for k, v in override.items() if k != "palette"})
    palette = dict(default.get("palette", {}))
    palette.update(override.get("palette", {}))
    merged["palette"] = palette
    return merged


def resolve_color(value: Any, theme: dict[str, Any], fallback: str = "#000000") -> str:
    if not isinstance(value, str) or not value:
        return fallback
    if value.startswith("@"):
        return str(theme.get("palette", {}).get(value[1:], fallback))
    return value


def font_stack(theme: dict[str, Any]) -> str:
    """Return one deduplicated SVG/CSS font-family stack from the theme."""
    primary = str(theme.get("font_family", "Noto Sans")).strip() or "Noto Sans"
    fallbacks = theme.get("font_fallbacks", ["Liberation Sans", "DejaVu Sans", "sans-serif"])
    if not isinstance(fallbacks, list):
        fallbacks = [fallbacks]
    families: list[str] = []
    seen: set[str] = set()
    for raw in [primary, *fallbacks]:
        family = str(raw).strip()
        key = family.casefold()
        if family and key not in seen:
            families.append(family)
            seen.add(key)
    return ", ".join(families)


def unit_vector(a: dict[str, float], b: dict[str, float]) -> tuple[float, float, float]:
    dx = b["x"] - a["x"]
    dy = b["y"] - a["y"]
    length = math.hypot(dx, dy)
    if length == 0:
        return 0.0, 0.0, 0.0
    return dx / length, dy / length, length


def rounded_path(points: list[dict[str, float]], radius: float) -> str:
    if len(points) < 2:
        return ""
    if len(points) == 2 or radius <= 0:
        return "M" + " L".join(f"{p['x']:g},{p['y']:g}" for p in points)
    commands = [f"M{points[0]['x']:g},{points[0]['y']:g}"]
    for index in range(1, len(points) - 1):
        previous, current, following = points[index - 1], points[index], points[index + 1]
        ux1, uy1, len1 = unit_vector(current, previous)
        ux2, uy2, len2 = unit_vector(current, following)
        if len1 == 0 or len2 == 0:
            commands.append(f"L{current['x']:g},{current['y']:g}")
            continue
        bend = min(radius, len1 / 2.0, len2 / 2.0)
        before = {"x": current["x"] + ux1 * bend, "y": current["y"] + uy1 * bend}
        after = {"x": current["x"] + ux2 * bend, "y": current["y"] + uy2 * bend}
        commands.append(f"L{before['x']:g},{before['y']:g}")
        commands.append(f"Q{current['x']:g},{current['y']:g} {after['x']:g},{after['y']:g}")
    commands.append(f"L{points[-1]['x']:g},{points[-1]['y']:g}")
    return " ".join(commands)


def edge_points(edge: dict[str, Any], ports: dict[str, dict[str, Any]]) -> list[dict[str, float]]:
    if isinstance(edge.get("points"), list) and len(edge["points"]) >= 2:
        return [{"x": float(p["x"]), "y": float(p["y"])} for p in edge["points"]]
    start = ports[edge["from"]]
    end = ports[edge["to"]]
    a = {"x": float(start["x"]), "y": float(start["y"])}
    b = {"x": float(end["x"]), "y": float(end["y"])}
    if edge.get("route") == "orthogonal" and a["x"] != b["x"] and a["y"] != b["y"]:
        middle_x = (a["x"] + b["x"]) / 2.0
        return [a, {"x": middle_x, "y": a["y"]}, {"x": middle_x, "y": b["y"]}, b]
    return [a, b]


def dash_array(kind: str, width: float) -> str | None:
    if kind == "dashed":
        return f"{width * 4:g} {width * 2.5:g}"
    if kind == "dotted":
        return f"{width:g} {width * 2.5:g}"
    return None


def wrap_text(text: str, width: float, font_size: float) -> list[str]:
    if not text:
        return [""]
    max_chars = max(1, int(width / max(font_size * 0.56, 1)))
    result: list[str] = []
    for paragraph in text.splitlines() or [text]:
        words = paragraph.split(" ")
        line = ""
        for word in words:
            candidate = word if not line else f"{line} {word}"
            if len(candidate) <= max_chars:
                line = candidate
            else:
                if line:
                    result.append(line)
                if len(word) <= max_chars:
                    line = word
                else:
                    result.extend(word[i : i + max_chars] for i in range(0, len(word), max_chars))
                    line = ""
        if line or not words:
            result.append(line)
    return result or [""]


def render_text(item: dict[str, Any], theme: dict[str, Any]) -> str:
    x, y = float(item["x"]), float(item["y"])
    width, height = float(item["width"]), float(item["height"])
    size = float(item.get("font_size", 18))
    weight = {"normal": 400, "medium": 500, "semibold": 600, "bold": 700}.get(item.get("font_weight", "normal"), 400)
    color = resolve_color(item.get("color", "@text"), theme, "#17212B")
    align = item.get("align", "left")
    anchor = {"left": "start", "center": "middle", "right": "end"}[align]
    tx = x if align == "left" else x + width / 2 if align == "center" else x + width
    lines = wrap_text(str(item.get("text", "")), width, size)
    line_height = size * 1.2
    total_height = line_height * len(lines)
    valign = item.get("valign", "middle")
    if valign == "top":
        first_y = y + size
    elif valign == "bottom":
        first_y = y + height - total_height + size
    else:
        first_y = y + (height - total_height) / 2 + size
    family = esc(font_stack(theme))
    tspans = "".join(
        f'<tspan x="{tx:g}" y="{first_y + index * line_height:g}">{esc(line)}</tspan>'
        for index, line in enumerate(lines)
    )
    return (
        f'<text id="{esc(item["id"])}" text-anchor="{anchor}" '
        f'font-family="{family}" font-size="{size:g}" font-weight="{weight}" fill="{esc(color)}">{tspans}</text>'
    )


def data_uri(path: Path) -> str:
    mime, _ = mimetypes.guess_type(path.name)
    if path.suffix.lower() == ".svg":
        mime = "image/svg+xml"
    mime = mime or "application/octet-stream"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def render_asset(asset: dict[str, Any], spec_dir: Path, embed: bool, theme: dict[str, Any]) -> tuple[str, str]:
    aid = safe_id(str(asset["id"]))
    x, y = float(asset["x"]), float(asset["y"])
    width, height = float(asset["width"]), float(asset["height"])
    radius = float(asset.get("clip_radius", 0))
    clip_id = f"clip-asset-{aid}"
    clip = f'<clipPath id="{clip_id}"><rect x="{x:g}" y="{y:g}" width="{width:g}" height="{height:g}" rx="{radius:g}"/></clipPath>'
    path_value = asset.get("path")
    resolved = (spec_dir / str(path_value)).resolve() if path_value else None
    if not resolved or not resolved.is_file() or asset.get("placeholder") is True:
        label = asset.get("placeholder_label") or "ASSET SLOT"
        body = (
            f'<g id="{aid}" clip-path="url(#{clip_id})">'
            f'<rect x="{x:g}" y="{y:g}" width="{width:g}" height="{height:g}" rx="{radius:g}" fill="#F2F5F8" stroke="#A8B4BE" stroke-dasharray="8 6"/>'
            f'<path d="M{x + width * 0.12:g},{y + height * 0.75:g} L{x + width * 0.38:g},{y + height * 0.48:g} L{x + width * 0.57:g},{y + height * 0.64:g} L{x + width * 0.78:g},{y + height * 0.35:g}" fill="none" stroke="#7B8994" stroke-width="2.5"/>'
            f'<text x="{x + width / 2:g}" y="{y + height * 0.9:g}" text-anchor="middle" font-family="{esc(font_stack(theme))}" font-size="{max(10, min(width, height) * 0.09):g}" fill="#667580">{esc(label)}</text>'
            "</g>"
        )
        return clip, body
    href = data_uri(resolved) if embed else resolved.as_posix()
    preserve = {"contain": "xMidYMid meet", "cover": "xMidYMid slice", "stretch": "none"}.get(asset.get("fit"), "xMidYMid meet")
    body = (
        f'<image id="{aid}" x="{x:g}" y="{y:g}" width="{width:g}" height="{height:g}" '
        f'href="{esc(href)}" preserveAspectRatio="{preserve}" clip-path="url(#{clip_id})">'
        f'<title>{esc(asset.get("alt", aid))}</title></image>'
    )
    return clip, body


def render_edge(edge: dict[str, Any], ports: dict[str, dict[str, Any]], theme: dict[str, Any]) -> tuple[str, str]:
    eid = safe_id(str(edge["id"]))
    points = edge_points(edge, ports)
    width = float(edge.get("width", theme.get("connector_width", 2.5)))
    color = resolve_color(edge.get("color", "@connector"), theme, "#1769E8")
    radius = float(edge.get("corner_radius", max(width * 2.5, 5)))
    marker_size = max(8.0, width * 4.2)
    marker_id = f"arrow-{eid}"
    marker = (
        f'<marker id="{marker_id}" viewBox="0 0 10 10" refX="8.6" refY="5" '
        f'markerWidth="{marker_size:g}" markerHeight="{marker_size:g}" markerUnits="userSpaceOnUse" orient="auto-start-reverse">'
        f'<path d="M0 0 L10 5 L0 10 Z" fill="{esc(color)}"/></marker>'
    )
    arrow = edge.get("arrowhead", "end")
    marker_start = f' marker-start="url(#{marker_id})"' if arrow in {"start", "both"} else ""
    marker_end = f' marker-end="url(#{marker_id})"' if arrow in {"end", "both"} else ""
    dash = dash_array(str(edge.get("dash", "solid")), width)
    dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
    path = rounded_path(points, radius)
    label = ""
    if edge.get("label"):
        middle = points[len(points) // 2]
        label = (
            f'<text x="{middle["x"]:g}" y="{middle["y"] - 7:g}" text-anchor="middle" '
            f'font-family="{esc(font_stack(theme))}" font-size="12" fill="{esc(color)}">{esc(edge["label"])}</text>'
        )
    body = (
        f'<g id="{eid}"><path d="{path}" fill="none" stroke="{esc(color)}" stroke-width="{width:g}" '
        f'stroke-linecap="round" stroke-linejoin="round"{dash_attr}{marker_start}{marker_end}>'
        f'<title>{esc(edge.get("meaning", eid))}</title></path>{label}</g>'
    )
    return marker, body


def render_panel(panel: dict[str, Any], theme: dict[str, Any]) -> tuple[str, str]:
    pid = safe_id(str(panel["id"]))
    x, y = float(panel["x"]), float(panel["y"])
    width, height = float(panel["width"]), float(panel["height"])
    radius = float(panel.get("radius", theme.get("panel_radius", 18)))
    stroke_width = float(panel.get("stroke_width", theme.get("panel_stroke_width", 2)))
    fill = resolve_color(panel.get("fill", "@panel_fill"), theme, "#FFFFFF")
    stroke = resolve_color(panel.get("stroke", "@primary"), theme, "#1769E8")
    header_height = float(panel.get("header_height", 0))
    header_fill = resolve_color(panel.get("header_fill", panel.get("stroke", "@primary")), theme, stroke)
    header_text = resolve_color(panel.get("header_text_color", "@on_primary"), theme, "#FFFFFF")
    clip_id = f"clip-panel-{pid}"
    clip = f'<clipPath id="{clip_id}"><rect x="{x:g}" y="{y:g}" width="{width:g}" height="{height:g}" rx="{radius:g}"/></clipPath>'
    parts = [f'<g id="{pid}"><title>{esc(panel.get("semantic_role", panel.get("title", pid)))}</title>']
    parts.append(f'<rect x="{x:g}" y="{y:g}" width="{width:g}" height="{height:g}" rx="{radius:g}" fill="{esc(fill)}"/>')
    if header_height > 0:
        parts.append(f'<rect x="{x:g}" y="{y:g}" width="{width:g}" height="{header_height:g}" fill="{esc(header_fill)}" clip-path="url(#{clip_id})"/>')
    parts.append(f'<rect x="{x:g}" y="{y:g}" width="{width:g}" height="{height:g}" rx="{radius:g}" fill="none" stroke="{esc(stroke)}" stroke-width="{stroke_width:g}"/>')
    title_size = float(panel.get("title_font_size", max(16, min(30, header_height * 0.44 if header_height else 22))))
    if width < 360:
        title_size = min(title_size, max(12.0, (width - 36) / max(len(str(panel.get("title", ""))) * 0.58, 1)))
    title_y = y + (header_height / 2 + title_size * 0.34 if header_height else title_size + 12)
    title_color = header_text if header_height else resolve_color("@text", theme, "#17212B")
    parts.append(
        f'<text x="{x + 18:g}" y="{title_y:g}" font-family="{esc(font_stack(theme))}" '
        f'font-size="{title_size:g}" font-weight="700" fill="{esc(title_color)}">{esc(panel.get("title", ""))}</text>'
    )
    subtitle = panel.get("subtitle")
    if subtitle:
        compact_subtitle = width < 360 or len(str(subtitle)) > max(18, int(width / max(title_size * 0.55, 1)))
        if header_height and not compact_subtitle:
            parts.append(
                f'<text x="{x + width - 16:g}" y="{title_y:g}" text-anchor="end" '
                f'font-family="{esc(font_stack(theme))}" font-size="{max(11, title_size * 0.55):g}" '
                f'font-weight="600" fill="{esc(title_color)}">{esc(subtitle)}</text>'
            )
        else:
            subtitle_size = max(11.0, min(14.0, title_size * 0.58))
            subtitle_top = y + (header_height if header_height else title_size + 16) + 6
            subtitle_height = max(18.0, height - (subtitle_top - y) - 8)
            parts.append(
                render_text(
                    {
                        "id": f"{pid}-subtitle",
                        "text": str(subtitle),
                        "x": x + 14,
                        "y": subtitle_top,
                        "width": max(1.0, width - 28),
                        "height": subtitle_height,
                        "font_size": subtitle_size,
                        "font_weight": "semibold",
                        "color": "@muted_text",
                        "align": "center",
                        "valign": "top",
                    },
                    theme,
                )
            )
    parts.append("</g>")
    return clip, "".join(parts)


def load_theme(spec: dict[str, Any], explicit_theme: Path | None, script_dir: Path) -> dict[str, Any]:
    default_path = script_dir.parent / "assets" / "default-theme.json"
    default: dict[str, Any] = {}
    selected = explicit_theme or (default_path if default_path.is_file() else None)
    if selected:
        loaded = json.loads(selected.read_text(encoding="utf-8-sig"))
        if "theme" in loaded and isinstance(loaded["theme"], dict):
            default = loaded["theme"]
        elif isinstance(loaded, dict):
            default = loaded
    return merge_theme(default, spec.get("theme", {}))


def build_svg(spec: dict[str, Any], spec_path: Path, theme_path: Path | None, embed_assets: bool, debug_ports: bool) -> str:
    canvas = spec["canvas"]
    width, height = float(canvas["width"]), float(canvas["height"])
    theme = load_theme(spec, theme_path, Path(__file__).resolve().parent)
    background = resolve_color(canvas.get("background", "@background"), theme, "#FFFFFF")
    ports = {str(port["id"]): port for port in spec.get("ports", [])}

    defs: list[str] = []
    external_edges: list[str] = []
    internal_edges: list[str] = []
    for edge in spec.get("edges", []):
        marker, body = render_edge(edge, ports, theme)
        defs.append(marker)
        (internal_edges if edge.get("scope") == "internal" else external_edges).append(body)

    panels: list[str] = []
    for panel in sorted(spec.get("panels", []), key=lambda value: int(value.get("z", 0))):
        clip, body = render_panel(panel, theme)
        defs.append(clip)
        panels.append(body)

    assets: list[str] = []
    for asset in spec.get("assets", []):
        clip, body = render_asset(asset, spec_path.parent, embed_assets, theme)
        defs.append(clip)
        assets.append(body)

    text_blocks = [render_text(item, theme) for item in spec.get("texts", [])]
    port_layer = ""
    if debug_ports:
        port_layer = "".join(
            f'<g><circle cx="{float(port["x"]):g}" cy="{float(port["y"]):g}" r="4" fill="#FF00A8"/>'
            f'<text x="{float(port["x"]) + 6:g}" y="{float(port["y"]) - 6:g}" font-size="10" fill="#7A004F">{esc(port["id"])}</text></g>'
            for port in spec.get("ports", [])
        )

    metadata = json.dumps(
        {
            "generator": "build-scientific-figures",
            "spec_version": spec.get("version"),
            "mode": spec.get("mode"),
            "title": spec.get("title", ""),
            "provenance": spec.get("provenance", []),
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    family = font_stack(theme)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'width="{width:g}" height="{height:g}" viewBox="0 0 {width:g} {height:g}" role="img">'
        f'<title>{esc(spec.get("title", "Scientific figure"))}</title><metadata>{esc(metadata)}</metadata>'
        f'<defs>{"".join(defs)}<style>text{{font-family:{esc(family)};}}</style></defs>'
        f'<rect width="{width:g}" height="{height:g}" fill="{esc(background)}"/>'
        f'<g id="external-edges">{"".join(external_edges)}</g>'
        f'<g id="panels">{"".join(panels)}</g>'
        f'<g id="assets">{"".join(assets)}</g>'
        f'<g id="internal-edges">{"".join(internal_edges)}</g>'
        f'<g id="texts">{"".join(text_blocks)}</g>'
        f'<g id="debug-ports">{port_layer}</g></svg>\n'
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render a validated scientific figure specification to canonical SVG.")
    parser.add_argument("spec", type=Path, help="Path to figure-spec.json")
    parser.add_argument("--output", "-o", type=Path, required=True, help="Destination SVG")
    parser.add_argument("--theme", type=Path, help="Optional theme JSON; spec values override it")
    parser.add_argument("--link-assets", action="store_true", help="Link local assets instead of embedding data URIs")
    parser.add_argument("--debug-ports", action="store_true", help="Draw port markers and ids")
    parser.add_argument("--require-approved", action="store_true", help="Refuse final rendering until semantic_graph_approved is true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        spec = json.loads(args.spec.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: cannot read specification: {exc}", file=sys.stderr)
        return 2
    if args.require_approved and spec.get("review", {}).get("semantic_graph_approved") is not True:
        print("ERROR: semantic graph is not approved; update review.semantic_graph_approved first.", file=sys.stderr)
        return 2
    try:
        svg = build_svg(spec, args.spec.resolve(), args.theme, not args.link_assets, args.debug_ports)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(svg, encoding="utf-8", newline="\n")
    except Exception as exc:  # keep CLI failure concise while preserving nonzero exit
        print(f"ERROR: SVG rendering failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"output": str(args.output.resolve()), "format": "svg"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Validate a build-scientific-figures v1 figure specification.

The validator intentionally uses only the Python standard library so it can run
before optional rendering dependencies are installed.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path
from typing import Any


ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9._-]*$")
HEX_RE = re.compile(r"^#[0-9A-Fa-f]{6}(?:[0-9A-Fa-f]{2})?$")
TOKEN_RE = re.compile(r"^@[A-Za-z][A-Za-z0-9._-]*$")
PORTABLE_FONT_WARNINGS = {"century gothic", "calibri", "aptos", "arial"}


def issue(level: str, code: str, message: str, path: str = "$") -> dict[str, str]:
    return {"level": level, "code": code, "path": path, "message": message}


def is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def validate_id(value: Any, path: str, issues: list[dict[str, str]]) -> None:
    if not isinstance(value, str) or not ID_RE.fullmatch(value):
        issues.append(issue("error", "invalid_id", "Use an identifier beginning with a letter and containing only letters, digits, '.', '_' or '-'.", path))


def validate_color(value: Any, path: str, issues: list[dict[str, str]]) -> None:
    if not isinstance(value, str) or not (HEX_RE.fullmatch(value) or TOKEN_RE.fullmatch(value)):
        issues.append(issue("error", "invalid_color", "Use #RRGGBB, #RRGGBBAA, or a palette token such as @primary.", path))


def validate_box(item: dict[str, Any], path: str, canvas: tuple[float, float], issues: list[dict[str, str]]) -> None:
    values: dict[str, float] = {}
    for key in ("x", "y", "width", "height"):
        value = item.get(key)
        if not is_number(value):
            issues.append(issue("error", "invalid_geometry", f"{key} must be a finite number.", f"{path}.{key}"))
            return
        values[key] = float(value)
    if values["width"] <= 0 or values["height"] <= 0:
        issues.append(issue("error", "invalid_geometry", "width and height must be positive.", path))
        return
    width, height = canvas
    if values["x"] < 0 or values["y"] < 0 or values["x"] + values["width"] > width or values["y"] + values["height"] > height:
        issues.append(issue("error", "outside_canvas", "Bounding box extends outside the canvas.", path))


def point_distance(a: dict[str, Any], b: dict[str, Any]) -> float:
    try:
        return math.hypot(float(a["x"]) - float(b["x"]), float(a["y"]) - float(b["y"]))
    except (KeyError, TypeError, ValueError):
        return math.inf


def validate_spec(spec: Any, spec_path: Path, check_assets: bool, require_approved: bool) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    if not isinstance(spec, dict):
        return [issue("error", "invalid_root", "The specification root must be a JSON object.")]

    if spec.get("version") != "1.0":
        issues.append(issue("error", "unsupported_version", "version must be '1.0'.", "$.version"))
    if spec.get("mode") not in {"exact", "inspired", "original"}:
        issues.append(issue("error", "invalid_mode", "mode must be exact, inspired, or original.", "$.mode"))

    canvas_obj = spec.get("canvas")
    if not isinstance(canvas_obj, dict) or not is_number(canvas_obj.get("width")) or not is_number(canvas_obj.get("height")):
        issues.append(issue("error", "invalid_canvas", "canvas.width and canvas.height must be finite numbers.", "$.canvas"))
        canvas = (1.0, 1.0)
    else:
        canvas = (float(canvas_obj["width"]), float(canvas_obj["height"]))
        if canvas[0] <= 0 or canvas[1] <= 0:
            issues.append(issue("error", "invalid_canvas", "Canvas dimensions must be positive.", "$.canvas"))
        if "background" in canvas_obj:
            validate_color(canvas_obj["background"], "$.canvas.background", issues)

    theme = spec.get("theme")
    if not isinstance(theme, dict):
        issues.append(issue("error", "missing_theme", "theme must be an object.", "$.theme"))
        theme = {}
    font_family = theme.get("font_family")
    if not isinstance(font_family, str) or not font_family.strip():
        issues.append(issue("error", "missing_font", "theme.font_family is required.", "$.theme.font_family"))
    elif font_family.strip().lower() in PORTABLE_FONT_WARNINGS:
        issues.append(issue("warning", "font_portability", f"'{font_family}' is not a safe Linux default; prefer Noto Sans or Liberation Sans.", "$.theme.font_family"))
    palette = theme.get("palette")
    if not isinstance(palette, dict) or not palette:
        issues.append(issue("error", "missing_palette", "theme.palette must contain at least one color.", "$.theme.palette"))
    else:
        for key, value in palette.items():
            if not isinstance(key, str) or not ID_RE.fullmatch(key):
                issues.append(issue("error", "invalid_palette_key", "Palette keys must be valid identifiers.", f"$.theme.palette.{key}"))
            if not isinstance(value, str) or not HEX_RE.fullmatch(value):
                issues.append(issue("error", "invalid_palette_color", "Palette values must use #RRGGBB or #RRGGBBAA.", f"$.theme.palette.{key}"))

    collections = {
        "panels": spec.get("panels", []),
        "texts": spec.get("texts", []),
        "ports": spec.get("ports", []),
        "edges": spec.get("edges", []),
        "assets": spec.get("assets", []),
    }
    for name, value in collections.items():
        if not isinstance(value, list):
            issues.append(issue("error", "invalid_collection", f"{name} must be an array.", f"$.{name}"))
            collections[name] = []

    all_ids: dict[str, str] = {}
    for collection_name, items in collections.items():
        for index, item in enumerate(items):
            path = f"$.{collection_name}[{index}]"
            if not isinstance(item, dict):
                issues.append(issue("error", "invalid_item", "Array item must be an object.", path))
                continue
            item_id = item.get("id")
            validate_id(item_id, f"{path}.id", issues)
            if isinstance(item_id, str):
                if item_id in all_ids:
                    issues.append(issue("error", "duplicate_id", f"Identifier '{item_id}' is already used at {all_ids[item_id]}.", f"{path}.id"))
                else:
                    all_ids[item_id] = path

    panel_ids = {item.get("id") for item in collections["panels"] if isinstance(item, dict) and isinstance(item.get("id"), str)}
    asset_ids = {item.get("id") for item in collections["assets"] if isinstance(item, dict) and isinstance(item.get("id"), str)}
    owner_ids = panel_ids | asset_ids

    for index, panel in enumerate(collections["panels"]):
        if not isinstance(panel, dict):
            continue
        path = f"$.panels[{index}]"
        validate_box(panel, path, canvas, issues)
        if not isinstance(panel.get("title"), str):
            issues.append(issue("error", "missing_panel_title", "Panel title must be a string.", f"{path}.title"))
        for key in ("fill", "stroke", "header_fill", "header_text_color"):
            if key in panel:
                validate_color(panel[key], f"{path}.{key}", issues)

    for collection_name in ("texts", "assets"):
        for index, item in enumerate(collections[collection_name]):
            if not isinstance(item, dict):
                continue
            path = f"$.{collection_name}[{index}]"
            validate_box(item, path, canvas, issues)
            owner = item.get("owner")
            if owner is not None and owner not in owner_ids:
                issues.append(issue("error", "unknown_owner", f"Owner '{owner}' does not name a panel or asset.", f"{path}.owner"))

    for index, asset in enumerate(collections["assets"]):
        if not isinstance(asset, dict):
            continue
        path = f"$.assets[{index}]"
        if asset.get("fit") not in {"contain", "cover", "stretch"}:
            issues.append(issue("error", "invalid_fit", "fit must be contain, cover, or stretch.", f"{path}.fit"))
        if not isinstance(asset.get("alt"), str) or not asset["alt"].strip():
            issues.append(issue("error", "missing_alt", "Every asset needs meaningful alt text.", f"{path}.alt"))
        asset_path = asset.get("path")
        if not asset_path and asset.get("placeholder") is not True:
            issues.append(issue("error", "missing_asset", "Provide path or set placeholder to true.", path))
        if check_assets and asset_path:
            resolved = (spec_path.parent / str(asset_path)).resolve()
            if not resolved.is_file():
                issues.append(issue("error", "asset_not_found", f"Asset does not exist: {resolved}", f"{path}.path"))

    ports: dict[str, dict[str, Any]] = {}
    for index, port in enumerate(collections["ports"]):
        if not isinstance(port, dict):
            continue
        path = f"$.ports[{index}]"
        if isinstance(port.get("id"), str):
            ports[port["id"]] = port
        if not is_number(port.get("x")) or not is_number(port.get("y")):
            issues.append(issue("error", "invalid_port", "Port x and y must be finite numbers.", path))
        elif not (0 <= float(port["x"]) <= canvas[0] and 0 <= float(port["y"]) <= canvas[1]):
            issues.append(issue("error", "outside_canvas", "Port lies outside the canvas.", path))
        if port.get("scope") not in {"internal", "external", "junction"}:
            issues.append(issue("error", "invalid_port_scope", "Port scope must be internal, external, or junction.", f"{path}.scope"))
        owner = port.get("owner")
        if owner is not None and owner not in owner_ids:
            issues.append(issue("error", "unknown_owner", f"Owner '{owner}' does not name a panel or asset.", f"{path}.owner"))

    seen_edges: set[tuple[str, str, str]] = set()
    for index, edge in enumerate(collections["edges"]):
        if not isinstance(edge, dict):
            continue
        path = f"$.edges[{index}]"
        source = edge.get("from")
        target = edge.get("to")
        if source not in ports:
            issues.append(issue("error", "unknown_port", f"Unknown source port '{source}'.", f"{path}.from"))
        if target not in ports:
            issues.append(issue("error", "unknown_port", f"Unknown target port '{target}'.", f"{path}.to"))
        if edge.get("scope") not in {"internal", "external"}:
            issues.append(issue("error", "invalid_edge_scope", "Edge scope must be internal or external.", f"{path}.scope"))
        if edge.get("arrowhead") not in {"none", "start", "end", "both"}:
            issues.append(issue("error", "invalid_arrowhead", "arrowhead must be none, start, end, or both.", f"{path}.arrowhead"))
        if not isinstance(edge.get("meaning"), str) or not edge["meaning"].strip():
            issues.append(issue("error", "missing_meaning", "Every edge must state its semantic meaning.", f"{path}.meaning"))
        if "color" in edge:
            validate_color(edge["color"], f"{path}.color", issues)
        points = edge.get("points")
        if points is not None:
            if not isinstance(points, list) or len(points) < 2:
                issues.append(issue("error", "invalid_route", "points must contain at least two coordinate objects.", f"{path}.points"))
            else:
                for point_index, point in enumerate(points):
                    point_path = f"{path}.points[{point_index}]"
                    if not isinstance(point, dict) or not is_number(point.get("x")) or not is_number(point.get("y")):
                        issues.append(issue("error", "invalid_point", "Each point needs finite x and y values.", point_path))
                    elif not (0 <= float(point["x"]) <= canvas[0] and 0 <= float(point["y"]) <= canvas[1]):
                        issues.append(issue("error", "outside_canvas", "Route point lies outside the canvas.", point_path))
                if source in ports and isinstance(points[0], dict) and point_distance(points[0], ports[source]) > 2.0:
                    issues.append(issue("warning", "route_source_mismatch", "First route point is more than 2 px from its source port.", f"{path}.points[0]"))
                if target in ports and isinstance(points[-1], dict) and point_distance(points[-1], ports[target]) > 2.0:
                    issues.append(issue("warning", "route_target_mismatch", "Last route point is more than 2 px from its target port.", f"{path}.points[-1]"))
        elif source in ports and target in ports and edge.get("route") == "explicit":
            issues.append(issue("error", "missing_route", "Explicit routes require points.", f"{path}.points"))
        if source in ports and target in ports and edge.get("scope") == "internal":
            source_owner = ports[source].get("owner")
            target_owner = ports[target].get("owner")
            if source_owner and target_owner and source_owner != target_owner:
                issues.append(issue("error", "internal_crosses_owner", "Internal edges must remain inside one owner; model cross-panel flow as external.", path))
        if isinstance(source, str) and isinstance(target, str):
            signature = (source, target, str(edge.get("meaning", "")))
            if signature in seen_edges:
                issues.append(issue("warning", "duplicate_edge", "Duplicate semantic edge.", path))
            seen_edges.add(signature)

    outputs = spec.get("outputs")
    if not isinstance(outputs, dict) or not isinstance(outputs.get("formats"), list):
        issues.append(issue("error", "invalid_outputs", "outputs.formats must be an array.", "$.outputs"))
    else:
        formats = outputs["formats"]
        invalid_formats = [value for value in formats if value not in {"svg", "png", "pdf", "pptx"}]
        if invalid_formats:
            issues.append(issue("error", "invalid_output_format", f"Unsupported formats: {invalid_formats}", "$.outputs.formats"))
        if "svg" not in formats:
            issues.append(issue("error", "missing_canonical_svg", "SVG is the canonical output and must be requested.", "$.outputs.formats"))
        for expected in ("png", "pdf"):
            if expected not in formats:
                issues.append(issue("warning", "missing_portable_output", f"Portable v1 normally includes {expected.upper()} output.", "$.outputs.formats"))

    review = spec.get("review")
    approved = isinstance(review, dict) and review.get("semantic_graph_approved") is True
    if require_approved and not approved:
        issues.append(issue("error", "semantic_review_required", "Approve the semantic graph before rendering final artwork.", "$.review.semantic_graph_approved"))
    elif not approved:
        issues.append(issue("warning", "semantic_review_pending", "Semantic graph has not been approved yet.", "$.review.semantic_graph_approved"))

    provenance = spec.get("provenance", [])
    if not isinstance(provenance, list):
        issues.append(issue("error", "invalid_provenance", "provenance must be an array.", "$.provenance"))
    else:
        provenance_ids: set[str] = set()
        for index, entry in enumerate(provenance):
            path = f"$.provenance[{index}]"
            if not isinstance(entry, dict):
                issues.append(issue("error", "invalid_provenance_item", "Provenance entry must be an object.", path))
                continue
            entry_id = entry.get("id")
            validate_id(entry_id, f"{path}.id", issues)
            if isinstance(entry_id, str):
                if entry_id in provenance_ids:
                    issues.append(issue("error", "duplicate_provenance_id", f"Duplicate provenance id '{entry_id}'.", f"{path}.id"))
                provenance_ids.add(entry_id)
            if not isinstance(entry.get("source"), str) or not entry["source"].strip():
                issues.append(issue("error", "missing_source", "Provenance source is required.", f"{path}.source"))
            if entry.get("status") not in {"verified", "user-provided", "inferred", "unverified"}:
                issues.append(issue("error", "invalid_provenance_status", "Invalid provenance status.", f"{path}.status"))
            if entry.get("status") in {"inferred", "unverified"}:
                issues.append(issue("warning", "unverified_claim", "Review inferred or unverified figure content before publication.", path))
            for target_id in entry.get("applies_to", []):
                if target_id not in all_ids:
                    issues.append(issue("error", "unknown_provenance_target", f"Unknown applies_to id '{target_id}'.", f"{path}.applies_to"))
        if spec.get("mode") in {"inspired", "original"} and not provenance:
            issues.append(issue("warning", "missing_provenance", "Paper-grounded figures should retain source mappings.", "$.provenance"))

    return issues


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate a build-scientific-figures v1 JSON specification.")
    parser.add_argument("spec", type=Path, help="Path to figure-spec.json")
    parser.add_argument("--check-assets", action="store_true", help="Require every non-placeholder asset path to exist")
    parser.add_argument("--require-approved", action="store_true", help="Fail until review.semantic_graph_approved is true")
    parser.add_argument("--strict", action="store_true", help="Treat warnings as validation failures")
    parser.add_argument("--json", action="store_true", dest="as_json", help="Print machine-readable JSON")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        # utf-8-sig accepts ordinary UTF-8 and the BOM emitted by legacy
        # Windows PowerShell's `Set-Content -Encoding utf8`.
        spec = json.loads(args.spec.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        print(f"ERROR: specification not found: {args.spec}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as exc:
        print(f"ERROR: invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}", file=sys.stderr)
        return 2

    issues = validate_spec(spec, args.spec.resolve(), args.check_assets, args.require_approved)
    errors = [entry for entry in issues if entry["level"] == "error"]
    warnings = [entry for entry in issues if entry["level"] == "warning"]
    result = {
        "valid": not errors and not (args.strict and warnings),
        "errors": len(errors),
        "warnings": len(warnings),
        "issues": issues,
    }
    if args.as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        for entry in issues:
            print(f"{entry['level'].upper():7} {entry['code']:28} {entry['path']}: {entry['message']}")
        print(f"Validation {'passed' if result['valid'] else 'failed'}: {len(errors)} error(s), {len(warnings)} warning(s).")
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

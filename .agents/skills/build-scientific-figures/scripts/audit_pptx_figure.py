#!/usr/bin/env python3
"""Audit scientific-figure PPTX complexity, portability, and theme effects."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
from typing import Any, Sequence
import zipfile
from xml.etree import ElementTree as ET


NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
}


def _words(text: str) -> list[str]:
    return re.findall(r"[\wμ≤≥·*]+", text, flags=re.UNICODE)


def audit(path: Path) -> dict[str, Any]:
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        slide_names = sorted(
            name
            for name in names
            if name.startswith("ppt/slides/slide") and name.endswith(".xml")
        )
        slide_roots = [ET.fromstring(archive.read(name)) for name in slide_names]
        relationship_text = "\n".join(
            archive.read(name).decode("utf-8", errors="replace")
            for name in names
            if name.endswith(".rels")
        )

    shape_count = 0
    picture_count = 0
    connector_count = 0
    text_shape_count = 0
    word_count = 0
    font_sizes: set[float] = set()
    bold_runs = 0
    text_runs = 0
    outer_shadows = 0
    nonzero_effect_refs = 0
    round_adjustments: list[float] = []
    path_hits: list[str] = []

    for root in slide_roots:
        shapes = root.findall(".//p:spTree/*", NS)
        for shape in shapes:
            local = shape.tag.rsplit("}", 1)[-1]
            if local not in {"sp", "pic", "cxnSp", "graphicFrame", "grpSp"}:
                continue
            shape_count += 1
            picture_count += local == "pic"
            connector_count += local == "cxnSp"
            texts = [node.text or "" for node in shape.findall(".//a:t", NS)]
            visible = "".join(texts).strip()
            if visible:
                text_shape_count += 1
                word_count += len(_words(visible))
                if re.search(r"(?:[A-Za-z]:\\|/home/|/root/|/cpfs/)", visible):
                    path_hits.append(visible)
            for run in shape.findall(".//a:r", NS):
                text_node = run.find("a:t", NS)
                if text_node is None or not (text_node.text or "").strip():
                    continue
                text_runs += 1
                properties = run.find("a:rPr", NS)
                if properties is not None:
                    size = properties.get("sz")
                    if size:
                        font_sizes.add(int(size) / 100.0)
                    bold_runs += properties.get("b") in {"1", "true"}
            for properties in shape.findall(".//a:defRPr", NS):
                size = properties.get("sz")
                if size:
                    font_sizes.add(int(size) / 100.0)
            outer_shadows += len(shape.findall(".//a:outerShdw", NS))
            nonzero_effect_refs += sum(
                effect.get("idx", "0") != "0"
                for effect in shape.findall(".//p:style/a:effectRef", NS)
            )
            for geometry in shape.findall(".//a:prstGeom", NS):
                if geometry.get("prst") != "roundRect":
                    continue
                for guide in geometry.findall("a:avLst/a:gd", NS):
                    if guide.get("name") == "adj":
                        formula = guide.get("fmla", "")
                        match = re.fullmatch(r"val\s+(-?\d+)", formula)
                        if match:
                            round_adjustments.append(int(match.group(1)) / 100000.0)

    bold_ratio = bold_runs / text_runs if text_runs else 0.0
    return {
        "schema_version": "scientific-figure-pptx-audit-v1",
        "path": str(path.resolve()),
        "slides": len(slide_names),
        "shape_count": shape_count,
        "picture_count": picture_count,
        "connector_count": connector_count,
        "text_shape_count": text_shape_count,
        "word_count": word_count,
        "font_sizes_pt": sorted(font_sizes),
        "minimum_font_pt": min(font_sizes) if font_sizes else None,
        "bold_run_ratio": bold_ratio,
        "outer_shadow_count": outer_shadows,
        "nonzero_theme_effect_ref_count": nonzero_effect_refs,
        "round_rect_adjustments": sorted(set(round_adjustments)),
        "external_relationship_count": relationship_text.count('TargetMode="External"'),
        "machine_path_hits": path_hits,
    }


def _violations(report: dict[str, Any], args: argparse.Namespace) -> list[str]:
    failures = []
    checks = (
        (args.max_shapes, report["shape_count"], "shape_count", lambda actual, limit: actual > limit),
        (args.max_text_shapes, report["text_shape_count"], "text_shape_count", lambda actual, limit: actual > limit),
        (args.max_words, report["word_count"], "word_count", lambda actual, limit: actual > limit),
        (args.max_font_sizes, len(report["font_sizes_pt"]), "font_size_count", lambda actual, limit: actual > limit),
        (args.min_font_pt, report["minimum_font_pt"], "minimum_font_pt", lambda actual, limit: actual is None or actual < limit),
        (args.max_bold_ratio, report["bold_run_ratio"], "bold_run_ratio", lambda actual, limit: actual > limit),
    )
    for limit, actual, name, predicate in checks:
        if limit is not None and predicate(actual, limit):
            failures.append(f"{name}={actual} violates limit {limit}")
    if args.single_slide and report["slides"] != 1:
        failures.append(f"slides={report['slides']} but exactly one is required")
    if args.no_external and report["external_relationship_count"]:
        failures.append(f"external_relationship_count={report['external_relationship_count']}")
    if args.require_flat and (report["outer_shadow_count"] or report["nonzero_theme_effect_ref_count"]):
        failures.append(
            "flat theme required but shadow/effect references remain: "
            f"outer={report['outer_shadow_count']} effect_refs={report['nonzero_theme_effect_ref_count']}"
        )
    if args.no_machine_paths and report["machine_path_hits"]:
        failures.append(f"machine-specific paths found: {report['machine_path_hits']}")
    return failures


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pptx", type=Path)
    parser.add_argument("--pretty", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--max-shapes", type=int)
    parser.add_argument("--max-text-shapes", type=int)
    parser.add_argument("--max-words", type=int)
    parser.add_argument("--max-font-sizes", type=int)
    parser.add_argument("--min-font-pt", type=float)
    parser.add_argument("--max-bold-ratio", type=float)
    parser.add_argument("--single-slide", action="store_true")
    parser.add_argument("--no-external", action="store_true")
    parser.add_argument("--require-flat", action="store_true")
    parser.add_argument("--no-machine-paths", action="store_true")
    args = parser.parse_args(argv)
    report = audit(args.pptx)
    report["violations"] = _violations(report, args)
    payload = json.dumps(report, indent=2 if args.pretty else None, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 1 if report["violations"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

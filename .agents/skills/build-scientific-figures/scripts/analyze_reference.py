#!/usr/bin/env python3
"""Extract portable, non-semantic visual facts from a reference raster image."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path


def rgb_hex(rgb: tuple[int, int, int]) -> str:
    return "#" + "".join(f"{channel:02X}" for channel in rgb)


def relative_luminance(rgb: tuple[int, int, int]) -> float:
    converted = []
    for channel in rgb:
        value = channel / 255.0
        converted.append(value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4)
    return 0.2126 * converted[0] + 0.7152 * converted[1] + 0.0722 * converted[2]


def contrast_ratio(a: float, b: float) -> float:
    high, low = max(a, b), min(a, b)
    return (high + 0.05) / (low + 0.05)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Measure canvas, aspect ratio, palette, and review grid for a reference image.")
    parser.add_argument("image", type=Path, help="PNG, JPEG, WebP, or another Pillow-supported image")
    parser.add_argument("--output", "-o", type=Path, required=True, help="Destination reference-analysis.json")
    parser.add_argument("--swatches", type=int, default=12, help="Dominant color count; default: 12")
    parser.add_argument("--grid", default="4x4", help="Normalized manual-review grid, e.g. 4x4")
    parser.add_argument("--thumbnail", type=Path, help="Optional 1200 px maximum-dimension PNG preview")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        from PIL import Image, ImageOps  # type: ignore
    except ImportError:
        print("ERROR: Pillow is required; install scripts/requirements.txt.", file=sys.stderr)
        return 2
    if not args.image.is_file():
        print(f"ERROR: image not found: {args.image}", file=sys.stderr)
        return 2
    try:
        columns, rows = (int(value) for value in args.grid.lower().split("x", 1))
        if columns <= 0 or rows <= 0:
            raise ValueError
    except ValueError:
        print("ERROR: --grid must look like 4x4 and use positive integers.", file=sys.stderr)
        return 2

    with Image.open(args.image) as opened:
        image = ImageOps.exif_transpose(opened).convert("RGB")
        width, height = image.size
        sample = image.copy()
        sample.thumbnail((512, 512))
        quantized = sample.quantize(colors=max(2, min(args.swatches, 64)), method=Image.Quantize.MEDIANCUT).convert("RGB")
        colors = quantized.getcolors(maxcolors=quantized.width * quantized.height) or []
        total = quantized.width * quantized.height
        swatches = []
        for count, color in sorted(colors, reverse=True)[: args.swatches]:
            rgb = tuple(int(value) for value in color)
            luminance = relative_luminance(rgb)
            white_contrast = contrast_ratio(luminance, 1.0)
            black_contrast = contrast_ratio(luminance, 0.0)
            swatches.append(
                {
                    "hex": rgb_hex(rgb),
                    "rgb": list(rgb),
                    "fraction": round(count / total, 6),
                    "relative_luminance": round(luminance, 6),
                    "recommended_text": "#FFFFFF" if white_contrast >= black_contrast else "#000000",
                    "contrast_white": round(white_contrast, 3),
                    "contrast_black": round(black_contrast, 3),
                }
            )
        if args.thumbnail:
            preview = image.copy()
            preview.thumbnail((1200, 1200))
            args.thumbnail.parent.mkdir(parents=True, exist_ok=True)
            preview.save(args.thumbnail, format="PNG")

    cells = []
    for row in range(rows):
        for column in range(columns):
            cells.append(
                {
                    "id": f"r{row + 1}c{column + 1}",
                    "normalized": {
                        "x": round(column / columns, 6),
                        "y": round(row / rows, 6),
                        "width": round(1 / columns, 6),
                        "height": round(1 / rows, 6),
                    },
                    "review": ["panel boundaries", "text hierarchy", "asset crop", "ports and arrows"],
                }
            )
    analysis = {
        "schema_version": "1.0",
        "source": str(args.image.resolve()),
        "canvas": {"width": width, "height": height, "aspect_ratio": round(width / height, 8)},
        "dominant_colors": swatches,
        "review_grid": {"columns": columns, "rows": rows, "cells": cells},
        "semantic_status": "not_analyzed",
        "instructions": "Treat these as measurements only. Manually identify semantic panels and arrow topology before reconstruction.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(analysis, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output.resolve()), "width": width, "height": height, "swatches": len(swatches)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

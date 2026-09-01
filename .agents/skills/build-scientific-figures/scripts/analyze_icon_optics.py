#!/usr/bin/env python3
"""Measure visible alpha geometry for one or more raster figure components."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from PIL import Image


def analyze(path: Path) -> dict[str, Any]:
    image = Image.open(path).convert("RGBA")
    alpha = image.getchannel("A")
    bbox = alpha.getbbox()
    if bbox is None:
        raise ValueError(f"image has no visible alpha content: {path}")
    total = weighted_x = weighted_y = 0.0
    for y in range(image.height):
        for x in range(image.width):
            value = alpha.getpixel((x, y))
            if value:
                total += value
                weighted_x += (x + 0.5) * value
                weighted_y += (y + 0.5) * value
    if total <= 0:
        raise ValueError(f"image has zero alpha mass: {path}")
    visible_width = bbox[2] - bbox[0]
    visible_height = bbox[3] - bbox[1]
    centroid = [weighted_x / total, weighted_y / total]
    return {
        "path": path.as_posix(),
        "canvas_px": [image.width, image.height],
        "alpha_bbox_px": list(bbox),
        "visible_size_px": [visible_width, visible_height],
        "alpha_centroid_px": centroid,
        "alpha_centroid_normalized": [centroid[0] / image.width, centroid[1] / image.height],
        "visible_fraction": (visible_width * visible_height) / (image.width * image.height),
        "alpha_extrema": list(alpha.getextrema()),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("images", nargs="+", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args(argv)
    payload = {
        "schema_version": "scientific-icon-optics-v1",
        "images": [analyze(path.resolve()) for path in args.images],
    }
    rendered = json.dumps(payload, indent=2 if args.pretty else None, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

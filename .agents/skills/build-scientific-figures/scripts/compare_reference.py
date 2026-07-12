#!/usr/bin/env python3
"""Create deterministic raster evidence for a reference-versus-render comparison."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Iterable


def parse_region(value: str) -> tuple[str, tuple[int, int, int, int]]:
    try:
        name, coordinates = value.split(":", 1)
        x, y, width, height = (int(token) for token in coordinates.split(","))
        if not name or min(x, y) < 0 or width <= 0 or height <= 0:
            raise ValueError
        return name, (x, y, x + width, y + height)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("region must be name:x,y,width,height") from exc


def metrics(reference, candidate) -> dict[str, float]:
    from PIL import ImageChops, ImageStat  # type: ignore

    difference = ImageChops.difference(reference, candidate)
    stat = ImageStat.Stat(difference)
    means = [value / 255.0 for value in stat.mean]
    rms = [value / 255.0 for value in stat.rms]
    return {
        "mean_absolute_error": round(sum(means) / len(means), 8),
        "root_mean_square_error": round(math.sqrt(sum(value * value for value in rms) / len(rms)), 8),
        "max_channel_error": round(max(extreme[1] / 255.0 for extreme in stat.extrema), 8),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare a candidate render with a reference image and write visual evidence.")
    parser.add_argument("reference", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--region", action="append", type=parse_region, default=[], help="Repeat name:x,y,width,height for high-risk crops")
    parser.add_argument("--fail-above", type=float, help="Exit 1 when full-image MAE exceeds this 0..1 threshold")
    parser.add_argument("--no-resize", action="store_true", help="Fail instead of resizing a candidate with different dimensions")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        from PIL import Image, ImageChops, ImageEnhance, ImageOps  # type: ignore
    except ImportError:
        print("ERROR: Pillow is required; install scripts/requirements.txt.", file=sys.stderr)
        return 2
    if not args.reference.is_file() or not args.candidate.is_file():
        print("ERROR: reference and candidate must both exist.", file=sys.stderr)
        return 2
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    with Image.open(args.reference) as opened_reference, Image.open(args.candidate) as opened_candidate:
        reference = ImageOps.exif_transpose(opened_reference).convert("RGB")
        candidate = ImageOps.exif_transpose(opened_candidate).convert("RGB")
    original_candidate_size = candidate.size
    resized = False
    if candidate.size != reference.size:
        if args.no_resize:
            print(f"ERROR: dimensions differ: reference={reference.size}, candidate={candidate.size}", file=sys.stderr)
            return 2
        candidate = candidate.resize(reference.size, Image.Resampling.LANCZOS)
        resized = True

    difference = ImageChops.difference(reference, candidate)
    grayscale = ImageOps.grayscale(difference)
    enhanced = ImageEnhance.Contrast(grayscale).enhance(3.0)
    heatmap = ImageOps.colorize(enhanced, black="#081229", mid="#FFB000", white="#FF1744")
    overlay = Image.blend(reference, candidate, 0.5)
    difference.save(output_dir / "difference.png")
    heatmap.save(output_dir / "heatmap.png")
    overlay.save(output_dir / "overlay.png")
    candidate.save(output_dir / "candidate-normalized.png")

    report_regions = [{"name": "full", "box": [0, 0, reference.width, reference.height], "metrics": metrics(reference, candidate)}]
    for name, box in args.region:
        if box[2] > reference.width or box[3] > reference.height:
            print(f"ERROR: region '{name}' extends outside the reference canvas.", file=sys.stderr)
            return 2
        ref_crop = reference.crop(box)
        candidate_crop = candidate.crop(box)
        safe_name = "".join(character if character.isalnum() or character in "-_" else "-" for character in name)
        ref_crop.save(output_dir / f"region-{safe_name}-reference.png")
        candidate_crop.save(output_dir / f"region-{safe_name}-candidate.png")
        ImageChops.difference(ref_crop, candidate_crop).save(output_dir / f"region-{safe_name}-difference.png")
        report_regions.append({"name": name, "box": list(box), "metrics": metrics(ref_crop, candidate_crop)})

    full_mae = report_regions[0]["metrics"]["mean_absolute_error"]
    passed = args.fail_above is None or full_mae <= args.fail_above
    report = {
        "schema_version": "1.0",
        "reference": str(args.reference.resolve()),
        "candidate": str(args.candidate.resolve()),
        "reference_size": list(reference.size),
        "candidate_original_size": list(original_candidate_size),
        "candidate_resized": resized,
        "regions": report_regions,
        "threshold": args.fail_above,
        "passed": passed,
        "interpretation": "Raster metrics are evidence, not semantic approval. Review topology and arrow direction separately.",
    }
    report_path = output_dir / "comparison-report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"report": str(report_path), "mae": full_mae, "passed": passed}, ensure_ascii=False))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

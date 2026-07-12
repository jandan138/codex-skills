#!/usr/bin/env python3
"""Extract page-addressable text and optional previews from a paper PDF."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def portable_source_path(source: Path, manifest_dir: Path) -> str:
    """Return a POSIX-style relative source path without leaking machine roots."""
    try:
        relative = os.path.relpath(source, manifest_dir)
    except ValueError:
        # Windows cannot express a relative path across drives. The hash and
        # source_pdf fields still identify the original without exposing it.
        relative = source.name
    return Path(relative).as_posix()


def parse_pages(value: str | None, page_count: int) -> list[int]:
    if not value:
        return list(range(page_count))
    selected: set[int] = set()
    for part in value.split(","):
        token = part.strip()
        if not token:
            continue
        if "-" in token:
            start_text, end_text = token.split("-", 1)
            start, end = int(start_text), int(end_text)
            if start > end:
                start, end = end, start
            selected.update(range(start - 1, end))
        else:
            selected.add(int(token) - 1)
    invalid = sorted(index + 1 for index in selected if index < 0 or index >= page_count)
    if invalid:
        raise ValueError(f"page selection outside document: {invalid}")
    return sorted(selected)


def extract_with_pymupdf(pdf: Path, output_dir: Path, render_pages: bool, dpi: int, pages_value: str | None) -> tuple[list[dict], str]:
    import fitz  # type: ignore

    document = fitz.open(pdf)
    selected = parse_pages(pages_value, document.page_count)
    records: list[dict] = []
    previews = output_dir / "pages"
    if render_pages:
        previews.mkdir(parents=True, exist_ok=True)
    for index in selected:
        page = document.load_page(index)
        text = page.get_text("text", sort=True).replace("\r\n", "\n").replace("\r", "\n").strip()
        record: dict[str, object] = {"page": index + 1, "text": text}
        if render_pages:
            scale = dpi / 72.0
            pixmap = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
            image_path = previews / f"page-{index + 1:04d}.png"
            pixmap.save(image_path)
            record["image"] = image_path.relative_to(output_dir).as_posix()
            record["image_width"] = pixmap.width
            record["image_height"] = pixmap.height
        records.append(record)
    return records, f"PyMuPDF {getattr(fitz, '__version__', 'unknown')}"


def split_pdftotext_pages(text: str) -> list[str]:
    chunks = text.replace("\r\n", "\n").replace("\r", "\n").split("\f")
    if chunks and not chunks[-1].strip():
        chunks.pop()
    return [chunk.strip() for chunk in chunks]


def render_with_pdftoppm(pdf: Path, output_dir: Path, dpi: int) -> dict[int, str]:
    executable = shutil.which("pdftoppm")
    if not executable:
        return {}
    previews = output_dir / "pages"
    previews.mkdir(parents=True, exist_ok=True)
    prefix = previews / "page"
    completed = subprocess.run(
        [executable, "-png", "-r", str(dpi), str(pdf), str(prefix)],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"pdftoppm failed: {completed.stderr.strip()}")
    result: dict[int, str] = {}
    for image in sorted(previews.glob("page-*.png")):
        suffix = image.stem.rsplit("-", 1)[-1]
        if suffix.isdigit():
            result[int(suffix)] = image.relative_to(output_dir).as_posix()
    return result


def extract_with_poppler(pdf: Path, output_dir: Path, render_pages: bool, dpi: int, pages_value: str | None) -> tuple[list[dict], str]:
    executable = shutil.which("pdftotext")
    if not executable:
        raise RuntimeError("Neither PyMuPDF nor pdftotext is available.")
    completed = subprocess.run(
        [executable, "-layout", str(pdf), "-"],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"pdftotext failed: {completed.stderr.decode(errors='replace').strip()}")
    text = completed.stdout.decode("utf-8", errors="replace")
    pages = split_pdftotext_pages(text)
    selected = parse_pages(pages_value, len(pages))
    images = render_with_pdftoppm(pdf, output_dir, dpi) if render_pages else {}
    records = []
    for index in selected:
        record: dict[str, object] = {"page": index + 1, "text": pages[index]}
        if index + 1 in images:
            record["image"] = images[index + 1]
        records.append(record)
    return records, "Poppler pdftotext"


def write_text_corpus(records: Iterable[dict], path: Path) -> list[dict]:
    pieces: list[str] = []
    manifest_records: list[dict] = []
    offset = 0
    for record in records:
        header = f"=== PAGE {record['page']} ===\n"
        body = str(record.get("text", "")).strip() + "\n"
        block = header + body
        start = offset
        pieces.append(block)
        offset += len(block)
        clean_record = {key: value for key, value in record.items() if key != "text"}
        clean_record.update({"text_start": start, "text_end": offset, "characters": len(body.rstrip("\n"))})
        manifest_records.append(clean_record)
    path.write_text("\n".join(pieces), encoding="utf-8", newline="\n")
    return manifest_records


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract page-addressable text and optional page PNGs from a paper PDF.")
    parser.add_argument("pdf", type=Path, help="Input paper PDF")
    parser.add_argument("--output-dir", type=Path, required=True, help="New or empty output directory")
    parser.add_argument("--pages", help="1-based selection such as 1-4,7,10")
    parser.add_argument("--render-pages", action="store_true", help="Render selected pages to PNG when a backend is available")
    parser.add_argument("--dpi", type=int, default=144, help="Preview DPI; default: 144")
    parser.add_argument("--force", action="store_true", help="Allow writing into an existing output directory")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    pdf = args.pdf.resolve()
    output_dir = args.output_dir.resolve()
    if not pdf.is_file():
        print(f"ERROR: PDF not found: {pdf}", file=sys.stderr)
        return 2
    if output_dir.exists() and any(output_dir.iterdir()) and not args.force:
        print(f"ERROR: output directory is not empty: {output_dir}; pass --force to reuse it.", file=sys.stderr)
        return 2
    output_dir.mkdir(parents=True, exist_ok=True)

    records: list[dict]
    extractor: str
    try:
        try:
            records, extractor = extract_with_pymupdf(pdf, output_dir, args.render_pages, args.dpi, args.pages)
        except ImportError:
            records, extractor = extract_with_poppler(pdf, output_dir, args.render_pages, args.dpi, args.pages)
    except (RuntimeError, ValueError) as exc:
        print(f"ERROR: paper extraction failed: {exc}", file=sys.stderr)
        return 1

    corpus_path = output_dir / "paper.txt"
    page_manifest = write_text_corpus(records, corpus_path)
    manifest = {
        "schema_version": "1.0",
        "source_pdf": pdf.name,
        "source_path": portable_source_path(pdf, output_dir),
        "source_path_base": "paper-manifest-directory",
        "sha256": sha256_file(pdf),
        "bytes": pdf.stat().st_size,
        "extractor": extractor,
        "selected_pages": [record["page"] for record in page_manifest],
        "text_file": corpus_path.name,
        "pages": page_manifest,
        "instructions": "Use page numbers in every provenance entry; treat inferred claims as unverified until reviewed.",
    }
    manifest_path = output_dir / "paper-manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"manifest": str(manifest_path), "pages": len(page_manifest), "extractor": extractor}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

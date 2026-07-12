#!/usr/bin/env python3
"""Validate an SVG and write a passive, self-contained safe copy.

The sanitizer is deliberately strict. It rejects active elements, event handlers,
external resource references, XML entities/DOCTYPEs, and stylesheet processing
instructions instead of attempting to repair potentially hostile input.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import sys
import tempfile
import xml.etree.ElementTree as ET


SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"

FORBIDDEN_ELEMENTS = {
    "script",
    "foreignobject",
    "iframe",
    "object",
    "embed",
}

URL_ATTRIBUTES = {"href", "src", "poster"}

URL_FUNCTION_RE = re.compile(r"url\s*\(\s*([^)]*?)\s*\)", re.IGNORECASE | re.DOTALL)
CSS_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
EXTERNAL_SCHEME_RE = re.compile(
    r"(?:https?|ftp|file|javascript|vbscript|data)\s*:", re.IGNORECASE
)
PROTOCOL_RELATIVE_RE = re.compile(r"(?:^|[\s('\"=])//")


class UnsafeSVG(ValueError):
    """Raised when the input violates the passive SVG policy."""


def local_name(name: str) -> str:
    """Return an XML local name for a Clark-notation or prefixed name."""

    if name.startswith("{") and "}" in name:
        return name.split("}", 1)[1]
    return name.rsplit(":", 1)[-1]


def compact_for_scheme_check(value: str) -> str:
    """Remove ASCII whitespace/control characters used to disguise URL schemes."""

    return "".join(ch for ch in value if ord(ch) > 0x20 and ord(ch) != 0x7F)


def validate_url_functions(value: str, context: str) -> None:
    """Allow only fragment-local url(#id) references."""

    matches = list(URL_FUNCTION_RE.finditer(value))
    stripped = CSS_COMMENT_RE.sub("", value)
    if re.search(r"url\s*\(", stripped, re.IGNORECASE) and not matches:
        raise UnsafeSVG(f"malformed URL function in {context}")

    for match in matches:
        target = match.group(1).strip().strip("'\"").strip()
        if not re.fullmatch(r"#[A-Za-z_][A-Za-z0-9_.:-]*", target):
            raise UnsafeSVG(f"non-local URL reference {target!r} in {context}")


def validate_css(value: str, context: str) -> None:
    """Reject CSS constructs capable of loading or disguising active content."""

    if "\\" in value:
        raise UnsafeSVG(f"CSS escapes are not allowed in {context}")

    plain = CSS_COMMENT_RE.sub("", value)
    compact = compact_for_scheme_check(plain).lower()
    forbidden_tokens = ("@import", "expression(", "-moz-binding", "behavior:")
    if any(token in compact for token in forbidden_tokens):
        raise UnsafeSVG(f"active or importing CSS in {context}")

    validate_url_functions(plain, context)
    if EXTERNAL_SCHEME_RE.search(compact) or PROTOCOL_RELATIVE_RE.search(plain):
        raise UnsafeSVG(f"external or executable URL in {context}")


def validate_attribute(name: str, value: str, element: str) -> None:
    """Validate one attribute under the strict passive-resource policy."""

    attr = local_name(name).lower()
    context = f"attribute {name!r} on <{element}>"

    if attr.startswith("on"):
        raise UnsafeSVG(f"event attribute {name!r} on <{element}> is not allowed")
    if attr == "base":
        raise UnsafeSVG(f"xml:base on <{element}> is not allowed")

    normalized = value.strip()
    if attr in URL_ATTRIBUTES and normalized and not re.fullmatch(
        r"#[A-Za-z_][A-Za-z0-9_.:-]*", normalized
    ):
        raise UnsafeSVG(f"non-local resource {normalized!r} in {context}")

    if attr == "style":
        validate_css(value, context)
    else:
        validate_url_functions(value, context)
        compact = compact_for_scheme_check(value)
        if EXTERNAL_SCHEME_RE.search(compact) or PROTOCOL_RELATIVE_RE.search(value):
            raise UnsafeSVG(f"external or executable URL in {context}")


def validate_tree(root: ET.Element) -> None:
    """Validate all elements, attributes, and embedded style text."""

    if local_name(root.tag).lower() != "svg":
        raise UnsafeSVG("root element must be <svg>")

    for element in root.iter():
        tag = local_name(element.tag).lower()
        if tag in FORBIDDEN_ELEMENTS:
            raise UnsafeSVG(f"element <{tag}> is not allowed")

        for name, value in element.attrib.items():
            validate_attribute(name, value, tag)

        if tag == "style":
            validate_css("".join(element.itertext()), "<style> element")


def parse_and_validate(source: Path) -> ET.ElementTree:
    """Parse an SVG after rejecting unsafe XML declarations."""

    try:
        raw = source.read_bytes()
    except OSError as exc:
        raise UnsafeSVG(f"cannot read input: {exc}") from exc

    # Keep the declaration scan byte-exact. NUL bytes indicate UTF-16/32 or
    # malformed input and could otherwise hide a DTD from the ASCII guard.
    if b"\x00" in raw:
        raise UnsafeSVG("NUL bytes and UTF-16/32 encoded SVG are not allowed")

    lowered = raw.lower()
    if b"<!doctype" in lowered or b"<!entity" in lowered:
        raise UnsafeSVG("DOCTYPE and ENTITY declarations are not allowed")
    if b"<?xml-stylesheet" in lowered:
        raise UnsafeSVG("xml-stylesheet processing instructions are not allowed")

    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise UnsafeSVG(f"invalid XML: {exc}") from exc

    validate_tree(root)
    return ET.ElementTree(root)


def write_safe_copy(tree: ET.ElementTree, destination: Path, overwrite: bool) -> None:
    """Write the validated tree atomically without leaving a partial output."""

    if destination.exists() and not overwrite:
        raise UnsafeSVG(f"output already exists: {destination}; use --force to replace it")

    destination.parent.mkdir(parents=True, exist_ok=True)
    ET.register_namespace("", SVG_NS)
    ET.register_namespace("xlink", XLINK_NS)

    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=f".{destination.name}.",
            suffix=".tmp",
            dir=destination.parent,
            delete=False,
        ) as temporary:
            temporary_name = temporary.name
            tree.write(temporary, encoding="utf-8", xml_declaration=True)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_name, destination)
        temporary_name = None
    except OSError as exc:
        raise UnsafeSVG(f"cannot write output: {exc}") from exc
    finally:
        if temporary_name is not None:
            try:
                os.unlink(temporary_name)
            except OSError:
                pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Reject active/external SVG content and write a validated safe copy."
    )
    parser.add_argument("input", type=Path, help="source SVG to validate")
    parser.add_argument("output", type=Path, help="path for the safe SVG copy")
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="replace an existing output file",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    source = args.input.resolve()
    destination = args.output.resolve()

    if source == destination:
        print("error: input and output must be different paths", file=sys.stderr)
        return 2

    try:
        tree = parse_and_validate(source)
        write_safe_copy(tree, destination, args.force)
    except UnsafeSVG as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(f"safe SVG written to {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

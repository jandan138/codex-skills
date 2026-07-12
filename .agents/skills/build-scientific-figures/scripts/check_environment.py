#!/usr/bin/env python3
"""Inspect optional rendering backends without installing or changing anything.

The module is intentionally standard-library only.  ``render_outputs.py`` imports
``inspect_environment`` so capability selection and the standalone diagnostic
command always agree.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import importlib.util
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


SCHEMA_VERSION = 1


COMMAND_SPECS: dict[str, dict[str, Any]] = {
    "inkscape": {
        "candidates": ("inkscape",),
        "version_args": ("--version",),
        "purpose": "SVG to PNG/PDF",
        "version_pattern": r"inkscape",
    },
    "rsvg_convert": {
        "candidates": ("rsvg-convert",),
        "version_args": ("--version",),
        "purpose": "SVG to PNG/PDF",
        "version_pattern": r"(?:rsvg|librsvg)",
    },
    "imagemagick": {
        # On Windows, `convert` belongs to the operating system. ImageMagick 6
        # installations on Unix commonly expose only `convert`, so probe it
        # there after the ImageMagick 7 `magick` entry point.
        "candidates": ("magick",) if platform.system() == "Windows" else ("magick", "convert"),
        "version_args": ("-version",),
        "purpose": "Fallback SVG/PDF rasterization",
        "version_pattern": r"imagemagick",
    },
    "libreoffice": {
        "candidates": ("soffice", "libreoffice"),
        "version_args": ("--version",),
        "purpose": "PPTX to PDF",
        "version_pattern": r"libreoffice",
    },
    "pdftocairo": {
        "candidates": ("pdftocairo",),
        "version_args": ("-v",),
        "purpose": "PDF to PNG",
        "version_pattern": r"pdftocairo",
    },
    "pdftoppm": {
        "candidates": ("pdftoppm",),
        "version_args": ("-v",),
        "purpose": "PDF to PNG",
        "version_pattern": r"pdftoppm",
    },
    "mutool": {
        "candidates": ("mutool",),
        "version_args": ("-v",),
        "purpose": "PDF to PNG",
        "version_pattern": r"(?:mutool|mupdf)",
        "allowed_returncodes": (0, 1),
    },
    "node": {
        "candidates": ("node",),
        "version_args": ("--version",),
        "purpose": "Optional Sharp/PDFKit and PptxGenJS backends",
        "version_pattern": r"^v?\d+\.",
    },
    "powershell": {
        "candidates": ("pwsh", "powershell"),
        "version_args": ("-NoProfile", "-NonInteractive", "-Command", "$PSVersionTable.PSVersion.ToString()"),
        "purpose": "Microsoft PowerPoint automation on Windows",
        "version_pattern": r"^\d+\.",
    },
}


MODULE_SPECS: dict[str, dict[str, str]] = {
    "cairosvg": {
        "import_name": "cairosvg",
        "distribution": "CairoSVG",
        "purpose": "SVG to PNG/PDF",
        "probe_code": (
            "import cairosvg; "
            "source=b'<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"1\" height=\"1\"/>'; "
            "png=cairosvg.svg2png(bytestring=source); pdf=cairosvg.svg2pdf(bytestring=source); "
            "assert png.startswith(b'\\x89PNG\\r\\n\\x1a\\n') and pdf.startswith(b'%PDF-')"
        ),
    },
    "pymupdf": {
        "import_name": "fitz",
        "distribution": "PyMuPDF",
        "purpose": "PDF to PNG",
        "probe_code": "import fitz; document=fitz.open(); document.close()",
    },
}


CAPABILITY_KEYS = (
    "svg_to_png",
    "svg_to_pdf",
    "pptx_to_pdf",
    "pdf_to_png",
    "pptx_to_png",
)

CAPABILITY_ALIASES = {key.replace("_to_", "-"): key for key in CAPABILITY_KEYS}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _first_line(value: str) -> str | None:
    for line in value.splitlines():
        line = line.strip()
        if line:
            return line[:500]
    return None


def _command_version(
    path: str,
    version_args: Iterable[str],
    timeout: float,
    allowed_returncodes: Iterable[int],
    version_pattern: str,
) -> tuple[str | None, str | None]:
    try:
        completed = subprocess.run(
            [path, *version_args],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
            shell=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return None, f"version probe failed: {exc}"

    # Poppler writes its version to stderr; most other tools use stdout.
    version = _first_line(completed.stdout) or _first_line(completed.stderr)
    if completed.returncode not in set(allowed_returncodes):
        return version, f"version probe exited with status {completed.returncode}"
    if not version:
        return None, "version probe produced no identifying output"
    if not re.search(version_pattern, version, flags=re.IGNORECASE):
        return version, f"version output did not match expected product pattern: {version_pattern}"
    return version, None


def _inspect_command(name: str, spec: dict[str, Any], check_versions: bool, timeout: float) -> dict[str, Any]:
    located_candidates: list[tuple[str, str]] = []
    for candidate in spec["candidates"]:
        candidate_path = shutil.which(candidate)
        if candidate_path:
            located_candidates.append((candidate, str(Path(candidate_path).resolve())))

    found_name: str | None = None
    found_path: str | None = None
    version: str | None = None
    warning: str | None = None
    candidate_failures: list[dict[str, Any]] = []
    if located_candidates and not check_versions:
        found_name, found_path = located_candidates[0]
    elif check_versions:
        for candidate, candidate_path in located_candidates:
            candidate_version, candidate_warning = _command_version(
                candidate_path,
                spec["version_args"],
                timeout,
                spec.get("allowed_returncodes", (0,)),
                spec["version_pattern"],
            )
            if candidate_warning is None:
                found_name = candidate
                found_path = candidate_path
                version = candidate_version
                break
            candidate_failures.append(
                {
                    "command": candidate,
                    "path": candidate_path,
                    "version": candidate_version,
                    "warning": candidate_warning,
                }
            )
        if located_candidates and found_path is None:
            found_name, found_path = located_candidates[0]
            version = candidate_failures[0]["version"] if candidate_failures else None
            warning = "; ".join(
                f"{item['command']}: {item['warning']}" for item in candidate_failures
            )

    result: dict[str, Any] = {
        "available": found_path is not None and (not check_versions or warning is None),
        "located": bool(located_candidates),
        "command": found_name,
        "path": found_path,
        "version": version,
        "purpose": spec["purpose"],
        "probe_warning": warning,
        "verification": (
            "not-run"
            if located_candidates and not check_versions
            else "passed"
            if found_path and warning is None
            else "failed"
            if located_candidates
            else "not-found"
        ),
        "candidate_failures": candidate_failures,
    }
    return result


def _inspect_module(spec: dict[str, str], timeout: float) -> dict[str, Any]:
    import_name = spec["import_name"]
    try:
        available = importlib.util.find_spec(import_name) is not None
    except (ImportError, AttributeError, ValueError):
        available = False

    located = available
    warning: str | None = None
    verification = "not-found"
    if located:
        try:
            completed = subprocess.run(
                [sys.executable, "-c", spec["probe_code"]],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                check=False,
                shell=False,
            )
            available = completed.returncode == 0
            verification = "passed" if available else "failed"
            if not available:
                detail = _first_line(completed.stderr) or _first_line(completed.stdout)
                warning = detail or f"module smoke test exited with status {completed.returncode}"
        except (OSError, subprocess.SubprocessError) as exc:
            available = False
            verification = "failed"
            warning = f"module smoke test failed: {exc}"

    version: str | None = None
    if available:
        try:
            version = importlib.metadata.version(spec["distribution"])
        except importlib.metadata.PackageNotFoundError:
            available = False
            verification = "failed"
            warning = (
                f"module is importable but {spec['distribution']} distribution metadata is unavailable"
            )

    return {
        "available": available,
        "located": located,
        "import_name": import_name,
        "distribution": spec["distribution"],
        "version": version,
        "purpose": spec["purpose"],
        "probe_warning": warning,
        "verification": verification,
    }


def _inspect_node_module(
    node_path: str | None,
    module_name: str,
    purpose: str,
    timeout: float,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "available": False,
        "module": module_name,
        "resolved": None,
        "version": None,
        "purpose": purpose,
        "probe_warning": None,
        "verification": "not-found",
    }
    if not node_path:
        result["probe_warning"] = "Node.js was not found"
        return result
    probe = (
        "const n=process.argv[1];"
        "try{const r=require.resolve(n);const loaded=require(n);"
        "if(loaded===null||loaded===undefined)throw new Error(n+' loaded no exports');let v=null;"
        "try{v=require(n+'/package.json').version}catch{};"
        "console.log(JSON.stringify({resolved:r,version:v}));}"
        "catch(e){console.error(e.message);process.exit(2)}"
    )
    try:
        completed = subprocess.run(
            [node_path, "-e", probe, module_name],
            cwd=str(Path(__file__).resolve().parent),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
            shell=False,
        )
        if completed.returncode == 0:
            payload = json.loads(completed.stdout)
            result.update(
                available=True,
                resolved=payload.get("resolved"),
                version=payload.get("version"),
                verification="require-passed",
            )
        else:
            result["verification"] = "failed"
            result["probe_warning"] = _first_line(completed.stderr) or f"module probe exited with status {completed.returncode}"
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        result["verification"] = "failed"
        result["probe_warning"] = f"Node module probe failed: {exc}"
    return result


def _inspect_node_svg_routes(node_path: str | None, timeout: float) -> dict[str, dict[str, Any]]:
    routes = {
        "sharp_png": {
            "available": False,
            "backend": "sharp",
            "format": "png",
            "purpose": "SVG to PNG",
            "verification": "not-found",
            "probe_warning": None,
        },
        "sharp_pdfkit_pdf": {
            "available": False,
            "backend": "sharp+pdfkit",
            "format": "pdf",
            "purpose": "Raster-backed SVG to PDF",
            "verification": "not-found",
            "probe_warning": None,
        },
    }
    if not node_path:
        for route in routes.values():
            route["probe_warning"] = "Node.js was not found or did not pass command verification"
        return routes

    helper = Path(__file__).resolve().with_name("render_svg.mjs")
    if not helper.is_file():
        for route in routes.values():
            route.update(
                verification="failed",
                probe_warning=f"renderer helper is missing: {helper}",
            )
        return routes

    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="2" height="2" '
        'viewBox="0 0 2 2"><rect width="2" height="2" fill="#336699"/></svg>'
    )
    try:
        with tempfile.TemporaryDirectory(prefix="figure-node-smoke-") as temporary_name:
            temporary = Path(temporary_name)
            source = temporary / "probe.svg"
            source.write_text(svg, encoding="utf-8", newline="\n")
            for route_name, route in routes.items():
                output_format = str(route["format"])
                output = temporary / f"{route_name}.{output_format}"
                try:
                    completed = subprocess.run(
                        [
                            node_path,
                            str(helper),
                            str(source),
                            "--output",
                            str(output),
                            "--format",
                            output_format,
                            "--dpi",
                            "96",
                        ],
                        cwd=str(helper.parent),
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        timeout=timeout,
                        check=False,
                        shell=False,
                    )
                    warning: str | None = None
                    if completed.returncode != 0:
                        warning = (
                            _first_line(completed.stderr)
                            or _first_line(completed.stdout)
                            or f"renderer smoke test exited with status {completed.returncode}"
                        )
                    elif not output.is_file():
                        warning = "renderer smoke test created no output"
                    else:
                        data = output.read_bytes()
                        if output_format == "png":
                            if not (
                                data.startswith(b"\x89PNG\r\n\x1a\n")
                                and b"IHDR" in data[:32]
                                and data.endswith(b"IEND\xaeB`\x82")
                            ):
                                warning = "Sharp smoke output is not a complete PNG"
                        elif not (
                            data.startswith(b"%PDF-")
                            and b"startxref" in data[-8192:]
                            and b"%%EOF" in data[-8192:]
                        ):
                            warning = "Sharp/PDFKit smoke output is not a complete PDF"
                    route.update(
                        available=warning is None,
                        verification="render-passed" if warning is None else "failed",
                        probe_warning=warning,
                        helper=str(helper),
                        output_bytes=output.stat().st_size if output.is_file() else None,
                    )
                except (OSError, subprocess.SubprocessError) as exc:
                    route.update(
                        verification="failed",
                        probe_warning=f"renderer smoke test failed: {exc}",
                        helper=str(helper),
                        output_bytes=None,
                    )
    except OSError as exc:
        for route in routes.values():
            route.update(
                verification="failed",
                probe_warning=f"could not prepare renderer smoke test: {exc}",
                helper=str(helper),
            )
    return routes


def _inspect_powerpoint(commands: dict[str, dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "available": False,
        "automation": "PowerPoint.Application COM",
        "purpose": "PPTX to PDF/PNG",
        "probe_warning": None,
        "verification": "registry-only",
    }
    if platform.system() != "Windows":
        result["verification"] = "not-applicable"
        result["probe_warning"] = "Microsoft PowerPoint COM automation is Windows-only"
        return result
    if not commands["powershell"]["available"]:
        result["verification"] = "failed"
        result["probe_warning"] = "PowerShell was not found"
        return result

    try:
        import winreg  # type: ignore[import-not-found]

        access_modes = [winreg.KEY_READ]
        for attribute in ("KEY_WOW64_64KEY", "KEY_WOW64_32KEY"):
            flag = getattr(winreg, attribute, 0)
            if flag:
                access_modes.append(winreg.KEY_READ | flag)

        for access in access_modes:
            try:
                with winreg.OpenKey(
                    winreg.HKEY_CLASSES_ROOT,
                    r"PowerPoint.Application\CLSID",
                    0,
                    access,
                ):
                    result["available"] = True
                    result["verification"] = "registry-passed"
                    result["probe_warning"] = None
                    break
            except OSError:
                continue
        if not result["available"]:
            result["verification"] = "failed"
            result["probe_warning"] = "PowerPoint.Application is not registered"
    except (ImportError, OSError) as exc:
        result["verification"] = "failed"
        result["probe_warning"] = f"PowerPoint registry probe failed: {exc}"
    return result


def _capability(
    available_backends: list[str],
    *,
    mode: str = "direct",
    unavailable_reason: str,
) -> dict[str, Any]:
    return {
        "available": bool(available_backends),
        "mode": mode if available_backends else "unavailable",
        "preferred_backend": available_backends[0] if available_backends else None,
        "backends": available_backends,
        "degradation": None if available_backends else unavailable_reason,
    }


def _available(items: dict[str, dict[str, Any]], key: str) -> bool:
    return bool(items.get(key, {}).get("available"))


def inspect_environment(*, check_versions: bool = True, timeout: float = 5.0) -> dict[str, Any]:
    """Return a JSON-serializable capability report without importing optional renderers."""

    commands = {
        name: _inspect_command(name, spec, check_versions, timeout)
        for name, spec in COMMAND_SPECS.items()
    }
    modules = {name: _inspect_module(spec, timeout) for name, spec in MODULE_SPECS.items()}
    node_command = commands.get("node", {})
    node_path = node_command.get("path") if node_command.get("available") else None
    node_modules = {
        "sharp": _inspect_node_module(node_path, "sharp", "SVG to PNG", timeout),
        "pdfkit": _inspect_node_module(node_path, "pdfkit", "Raster-backed SVG to PDF", timeout),
        "pptxgenjs": _inspect_node_module(node_path, "pptxgenjs", "Optional editable PPTX projection", timeout),
    }
    node_renderers = _inspect_node_svg_routes(node_path, timeout)
    powerpoint = _inspect_powerpoint(commands)

    svg_png_backends = [
        name
        for name, is_available in (
            ("cairosvg", _available(modules, "cairosvg")),
            ("sharp", _available(node_renderers, "sharp_png")),
            ("inkscape", _available(commands, "inkscape")),
            ("rsvg-convert", _available(commands, "rsvg_convert")),
            ("imagemagick", _available(commands, "imagemagick")),
        )
        if is_available
    ]
    svg_pdf_backends = [
        name
        for name, is_available in (
            ("cairosvg", _available(modules, "cairosvg")),
            ("sharp+pdfkit", _available(node_renderers, "sharp_pdfkit_pdf")),
            ("inkscape", _available(commands, "inkscape")),
            ("rsvg-convert", _available(commands, "rsvg_convert")),
            ("imagemagick", _available(commands, "imagemagick")),
        )
        if is_available
    ]
    pdf_png_backends = [
        name
        for name, is_available in (
            ("pymupdf", _available(modules, "pymupdf")),
            ("pdftocairo", _available(commands, "pdftocairo")),
            ("pdftoppm", _available(commands, "pdftoppm")),
            ("mutool", _available(commands, "mutool")),
            ("imagemagick", _available(commands, "imagemagick")),
        )
        if is_available
    ]
    pptx_pdf_backends = [
        name
        for name, is_available in (
            ("libreoffice", _available(commands, "libreoffice")),
            ("powerpoint", bool(powerpoint["available"])),
        )
        if is_available
    ]

    capabilities = {
        "svg_to_png": _capability(
            list(svg_png_backends),
            unavailable_reason="keep the SVG source; install one optional SVG renderer to produce PNG",
        ),
        "svg_to_pdf": _capability(
            list(svg_pdf_backends),
            unavailable_reason="keep the SVG source; install one optional SVG renderer to produce PDF",
        ),
        "pptx_to_pdf": _capability(
            pptx_pdf_backends,
            unavailable_reason="keep the editable PPTX source; no presentation renderer is available",
        ),
        "pdf_to_png": _capability(
            pdf_png_backends,
            unavailable_reason="keep the PDF source; no PDF rasterizer is available",
        ),
    }

    pptx_png_backends: list[str] = []
    if powerpoint["available"]:
        pptx_png_backends.append("powerpoint-direct")
    for pptx_backend in pptx_pdf_backends:
        for raster_backend in pdf_png_backends:
            pptx_png_backends.append(f"{pptx_backend}+{raster_backend}")
    capabilities["pptx_to_png"] = _capability(
        pptx_png_backends,
        mode="direct-or-chained" if powerpoint["available"] else "chained",
        unavailable_reason=(
            "keep the editable PPTX source; PNG needs PowerPoint direct export or both a PPTX-to-PDF "
            "backend and a PDF rasterizer"
        ),
    )

    available_count = sum(bool(capabilities[key]["available"]) for key in CAPABILITY_KEYS)
    if available_count == len(CAPABILITY_KEYS):
        grade = "full"
        level = 0
    elif available_count:
        grade = "partial"
        level = 1
    else:
        grade = "source-only"
        level = 2

    return {
        "schema_version": SCHEMA_VERSION,
        "checked_at": _utc_now(),
        "read_only_probe": True,
        "automatic_installation": False,
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python_version": platform.python_version(),
            "python_executable": str(Path(sys.executable).resolve()),
            "cwd": str(Path.cwd().resolve()),
        },
        "commands": commands,
        "python_modules": modules,
        "node_modules": node_modules,
        "node_renderers": node_renderers,
        "powerpoint": powerpoint,
        "capabilities": capabilities,
        "degradation": {
            "level": level,
            "grade": grade,
            "available_capabilities": available_count,
            "total_capabilities": len(CAPABILITY_KEYS),
        },
    }


def _atomic_write_json(path: Path, payload: dict[str, Any], *, pretty: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    indent = 2 if pretty else None
    serialized = json.dumps(payload, ensure_ascii=False, indent=indent, sort_keys=pretty) + "\n"
    handle, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(serialized)
        os.replace(temporary_name, path)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except OSError:
            pass
        raise


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Inspect optional scientific-figure rendering backends. "
            "This command is read-only and never installs dependencies."
        )
    )
    parser.add_argument(
        "--json",
        "--output",
        dest="json_path",
        type=Path,
        metavar="PATH",
        help="also write the complete report to PATH",
    )
    parser.add_argument("--pretty", action="store_true", help="pretty-print JSON")
    parser.add_argument("--quiet", action="store_true", help="do not print JSON to stdout")
    parser.add_argument(
        "--no-version-checks",
        action="store_true",
        help="only locate commands; do not execute command version flags (module smoke tests still run)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=5.0,
        metavar="SECONDS",
        help="per-command version probe timeout (default: 5)",
    )
    parser.add_argument(
        "--require",
        action="append",
        choices=sorted(CAPABILITY_ALIASES),
        default=[],
        metavar="CAPABILITY",
        help="return status 2 if CAPABILITY is unavailable; may be repeated",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="return status 2 unless every advertised conversion capability is available",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.timeout <= 0:
        parser.error("--timeout must be greater than zero")

    report = inspect_environment(check_versions=not args.no_version_checks, timeout=args.timeout)
    if args.json_path:
        _atomic_write_json(args.json_path.resolve(), report, pretty=args.pretty)
    if not args.quiet:
        print(json.dumps(report, ensure_ascii=False, indent=2 if args.pretty else None, sort_keys=args.pretty))

    required = [CAPABILITY_ALIASES[item] for item in args.require]
    missing_required = [key for key in required if not report["capabilities"][key]["available"]]
    if args.strict and report["degradation"]["grade"] != "full":
        return 2
    return 2 if missing_required else 0


if __name__ == "__main__":
    raise SystemExit(main())

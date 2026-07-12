#!/usr/bin/env python3
"""Render SVG/PPTX derivatives with capability-aware fallback and QA reporting.

Supported routes:

* SVG  -> PNG and/or PDF
* PPTX -> PDF and/or one PNG per slide

Only already-installed backends are used.  Missing optional tools are a supported
degraded state and are recorded as ``skipped`` in ``qa-report.json``.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile
import zlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from check_environment import inspect_environment


SCHEMA_VERSION = 1
SUPPORTED_INPUTS = {".svg", ".pptx"}
SUPPORTED_FORMATS = ("png", "pdf")
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _truncate(value: str | None, limit: int = 4000) -> str:
    if not value:
        return ""
    value = value.strip()
    return value if len(value) <= limit else value[:limit] + "\n…[truncated]"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _inspect_png(path: Path) -> dict[str, Any]:
    file_size = path.stat().st_size
    with path.open("rb") as stream:
        if stream.read(8) != PNG_SIGNATURE:
            raise ValueError("invalid PNG signature")
        saw_ihdr = False
        saw_idat = False
        saw_iend = False
        width = 0
        height = 0
        while not saw_iend:
            header = stream.read(8)
            if len(header) != 8:
                raise ValueError("truncated PNG chunk header")
            length, chunk_type = struct.unpack(">I4s", header)
            if length > file_size:
                raise ValueError("PNG chunk length exceeds file size")
            data = stream.read(length)
            checksum_bytes = stream.read(4)
            if len(data) != length or len(checksum_bytes) != 4:
                raise ValueError("truncated PNG chunk")
            expected_crc = struct.unpack(">I", checksum_bytes)[0]
            actual_crc = zlib.crc32(chunk_type)
            actual_crc = zlib.crc32(data, actual_crc) & 0xFFFFFFFF
            if actual_crc != expected_crc:
                raise ValueError(f"PNG {chunk_type.decode('ascii', errors='replace')} chunk CRC mismatch")
            if not saw_ihdr:
                if chunk_type != b"IHDR" or length != 13:
                    raise ValueError("PNG does not begin with a 13-byte IHDR chunk")
                width, height = struct.unpack(">II", data[:8])
                if width <= 0 or height <= 0:
                    raise ValueError("PNG dimensions are not positive")
                saw_ihdr = True
            elif chunk_type == b"IHDR":
                raise ValueError("PNG contains more than one IHDR chunk")
            if chunk_type == b"IDAT":
                saw_idat = True
            if chunk_type == b"IEND":
                if length != 0:
                    raise ValueError("PNG IEND chunk is not empty")
                saw_iend = True
        if stream.read(1):
            raise ValueError("PNG contains data after IEND")
    if not saw_idat:
        raise ValueError("PNG contains no IDAT image data")
    return {
        "passed": True,
        "details": "PNG chunk structure and CRC checks are valid",
        "width_px": width,
        "height_px": height,
    }


def _inspect_pdf(path: Path) -> dict[str, Any]:
    file_size = path.stat().st_size
    if file_size < 100:
        raise ValueError("PDF is too small to contain a complete document")
    with path.open("rb") as stream:
        header = stream.read(1024)
        stream.seek(max(0, file_size - 8192))
        trailer = stream.read()
    match = re.search(br"%PDF-(\d\.\d)", header)
    if not match or match.start() > 128:
        raise ValueError("PDF header is missing or too far from the start of the file")
    if b"startxref" not in trailer:
        raise ValueError("PDF startxref marker is missing from the trailer")
    if b"%%EOF" not in trailer:
        raise ValueError("PDF EOF marker is missing from the trailer")
    return {
        "passed": True,
        "details": "PDF header, cross-reference marker, and EOF trailer are present",
        "pdf_version": match.group(1).decode("ascii"),
    }


def _path_metadata(path: Path) -> dict[str, Any]:
    result: dict[str, Any] = {
        "path": str(path.resolve()),
        "exists": path.is_file(),
        "size_bytes": None,
        "sha256": None,
        "validation": {"passed": False, "details": "file does not exist"},
    }
    if not path.is_file():
        return result

    result["size_bytes"] = path.stat().st_size
    result["sha256"] = _sha256(path)
    suffix = path.suffix.lower()
    if suffix == ".png":
        try:
            result["validation"] = _inspect_png(path)
        except (OSError, ValueError, struct.error) as exc:
            result["validation"] = {"passed": False, "details": str(exc)}
    elif suffix == ".pdf":
        try:
            result["validation"] = _inspect_pdf(path)
        except (OSError, ValueError) as exc:
            result["validation"] = {"passed": False, "details": str(exc)}
    else:
        result["validation"] = {
            "passed": path.stat().st_size > 0,
            "details": "file is non-empty" if path.stat().st_size > 0 else "file is empty",
        }
    return result


def _validate_source(path: Path) -> dict[str, Any]:
    result: dict[str, Any] = {
        "path": str(path),
        "type": path.suffix.lower().lstrip("."),
        "passed": False,
        "details": None,
        "size_bytes": None,
        "sha256": None,
        "slide_count": None,
    }
    if not path.exists():
        result["details"] = "source does not exist"
        return result
    if not path.is_file():
        result["details"] = "source is not a regular file"
        return result
    if path.suffix.lower() not in SUPPORTED_INPUTS:
        result["details"] = f"unsupported source type: {path.suffix or '(none)'}"
        return result

    result["size_bytes"] = path.stat().st_size
    result["sha256"] = _sha256(path)
    try:
        if path.suffix.lower() == ".svg":
            root = ET.parse(path).getroot()
            local_name = root.tag.rsplit("}", 1)[-1].lower()
            if local_name != "svg":
                raise ValueError("XML root element is not <svg>")
            result["details"] = "SVG XML is well-formed"
        else:
            with zipfile.ZipFile(path) as archive:
                names = set(archive.namelist())
                required = {"[Content_Types].xml", "ppt/presentation.xml"}
                missing = sorted(required - names)
                if missing:
                    raise ValueError("PPTX is missing: " + ", ".join(missing))
                corrupt_member = archive.testzip()
                if corrupt_member:
                    raise ValueError(f"PPTX ZIP member failed CRC: {corrupt_member}")
                presentation_root = ET.fromstring(archive.read("ppt/presentation.xml"))
                slide_count = sum(
                    element.tag.rsplit("}", 1)[-1] == "sldId"
                    for element in presentation_root.iter()
                )
                if slide_count < 1:
                    raise ValueError("PPTX contains no slides")
                result["slide_count"] = slide_count
            result["details"] = (
                f"PPTX package structure and CRC checks are valid ({slide_count} slide(s))"
            )
    except (ET.ParseError, OSError, ValueError, zipfile.BadZipFile) as exc:
        result["details"] = str(exc)
        return result

    result["passed"] = True
    return result


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(serialized)
        os.replace(temporary_name, path)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except OSError:
            pass
        raise


def _run_command(command: list[str], timeout: float) -> dict[str, Any]:
    display_command = [str(part) for part in command]
    try:
        completed = subprocess.run(
            display_command,
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
        return {
            "command": display_command,
            "returncode": completed.returncode,
            "stdout": _truncate(completed.stdout),
            "stderr": _truncate(completed.stderr),
            "timed_out": False,
            "error": None,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "command": display_command,
            "returncode": None,
            "stdout": _truncate(exc.stdout.decode(errors="replace") if isinstance(exc.stdout, bytes) else exc.stdout),
            "stderr": _truncate(exc.stderr.decode(errors="replace") if isinstance(exc.stderr, bytes) else exc.stderr),
            "timed_out": True,
            "error": f"command exceeded {timeout:g} seconds",
        }
    except OSError as exc:
        return {
            "command": display_command,
            "returncode": None,
            "stdout": "",
            "stderr": "",
            "timed_out": False,
            "error": str(exc),
        }


def _command_path(environment: dict[str, Any], key: str) -> str | None:
    value = environment["commands"].get(key, {})
    return value.get("path") if value.get("available") else None


def _fresh_temp_path(parent: Path, suffix: str) -> Path:
    descriptor, name = tempfile.mkstemp(prefix=".render-", suffix=suffix, dir=str(parent))
    os.close(descriptor)
    path = Path(name)
    path.unlink(missing_ok=True)
    return path


def _validated_output(path: Path, expected_format: str) -> tuple[bool, str]:
    metadata = _path_metadata(path)
    if path.suffix.lower() != f".{expected_format}":
        return False, f"unexpected output suffix: {path.suffix}"
    validation = metadata["validation"]
    return bool(validation["passed"]), str(validation["details"])


def _module_attempt(backend: str, action: Callable[[], None]) -> dict[str, Any]:
    attempt: dict[str, Any] = {
        "backend": backend,
        "command": None,
        "returncode": None,
        "stdout": "",
        "stderr": "",
        "timed_out": False,
        "error": None,
    }
    try:
        action()
    except Exception as exc:  # Optional backends raise implementation-specific errors.
        attempt["error"] = f"{type(exc).__name__}: {exc}"
    return attempt


def _external_attempt(backend: str, command: list[str], timeout: float) -> dict[str, Any]:
    attempt = _run_command(command, timeout)
    attempt["backend"] = backend
    if attempt["returncode"] not in (0, None) and not attempt["error"]:
        attempt["error"] = f"command exited with status {attempt['returncode']}"
    return attempt


def _convert_svg(
    source: Path,
    target: Path,
    output_format: str,
    environment: dict[str, Any],
    dpi: int,
    timeout: float,
) -> dict[str, Any]:
    capability = environment["capabilities"][f"svg_to_{output_format}"]
    backends = list(capability["backends"])
    result: dict[str, Any] = {
        "success": False,
        "available": bool(backends),
        "backend": None,
        "attempts": [],
        "error": capability["degradation"],
    }
    if not backends:
        return result

    target.parent.mkdir(parents=True, exist_ok=True)
    for backend in backends:
        temporary = _fresh_temp_path(target.parent, f".{output_format}")
        if backend == "cairosvg":
            def render_with_cairosvg() -> None:
                import cairosvg  # type: ignore[import-not-found]

                function = cairosvg.svg2png if output_format == "png" else cairosvg.svg2pdf
                function(url=str(source), write_to=str(temporary), dpi=dpi)

            attempt = _module_attempt(backend, render_with_cairosvg)
        elif backend == "inkscape":
            executable = _command_path(environment, "inkscape")
            assert executable
            command = [
                executable,
                str(source),
                f"--export-type={output_format}",
                f"--export-filename={temporary}",
            ]
            if output_format == "png":
                command.append(f"--export-dpi={dpi}")
            attempt = _external_attempt(backend, command, timeout)
        elif backend == "rsvg-convert":
            executable = _command_path(environment, "rsvg_convert")
            assert executable
            command = [
                executable,
                f"--format={output_format}",
                f"--output={temporary}",
                f"--dpi-x={dpi}",
                f"--dpi-y={dpi}",
                str(source),
            ]
            attempt = _external_attempt(backend, command, timeout)
        elif backend == "imagemagick":
            executable = _command_path(environment, "imagemagick")
            assert executable
            attempt = _external_attempt(
                backend,
                [executable, "-density", str(dpi), str(source), str(temporary)],
                timeout,
            )
        elif backend in {"sharp", "sharp+pdfkit"}:
            executable = _command_path(environment, "node")
            assert executable
            helper = Path(__file__).resolve().with_name("render_svg.mjs")
            attempt = _external_attempt(
                backend,
                [
                    executable,
                    str(helper),
                    str(source),
                    "--output",
                    str(temporary),
                    "--format",
                    output_format,
                    "--dpi",
                    str(dpi),
                ],
                timeout,
            )
        else:
            continue

        passed, detail = _validated_output(temporary, output_format)
        if attempt["error"] is None and not passed:
            attempt["error"] = f"output validation failed: {detail}"
        result["attempts"].append(attempt)
        if attempt["error"] is None and passed:
            os.replace(temporary, target)
            result.update(success=True, backend=backend, error=None)
            return result
        temporary.unlink(missing_ok=True)

    result["error"] = "all available SVG rendering backends failed"
    return result


def _ps_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _powershell_command(executable: str, script: str) -> list[str]:
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    return [executable, "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded]


def _powerpoint_pdf_script(source: Path, target: Path) -> str:
    return f"""
$ErrorActionPreference = 'Stop'
$application = $null
$presentation = $null
try {{
    $application = New-Object -ComObject PowerPoint.Application
    $presentation = $application.Presentations.Open({_ps_literal(str(source))}, $true, $false, $false)
    $presentation.SaveAs({_ps_literal(str(target))}, 32)
}} finally {{
    if ($null -ne $presentation) {{ try {{ $presentation.Close() }} catch {{}} }}
    if ($null -ne $application) {{ try {{ $application.Quit() }} catch {{}} }}
    [GC]::Collect()
    [GC]::WaitForPendingFinalizers()
}}
"""


def _powerpoint_png_script(source: Path, output_dir: Path, dpi: int) -> str:
    return f"""
$ErrorActionPreference = 'Stop'
$application = $null
$presentation = $null
try {{
    $application = New-Object -ComObject PowerPoint.Application
    $presentation = $application.Presentations.Open({_ps_literal(str(source))}, $true, $false, $false)
    $width = [Math]::Max(1, [int][Math]::Round($presentation.PageSetup.SlideWidth / 72.0 * {dpi}))
    $height = [Math]::Max(1, [int][Math]::Round($presentation.PageSetup.SlideHeight / 72.0 * {dpi}))
    for ($index = 1; $index -le $presentation.Slides.Count; $index++) {{
        $name = 'slide-' + $index.ToString('000') + '.png'
        $path = Join-Path {_ps_literal(str(output_dir))} $name
        $presentation.Slides.Item($index).Export($path, 'PNG', $width, $height)
    }}
}} finally {{
    if ($null -ne $presentation) {{ try {{ $presentation.Close() }} catch {{}} }}
    if ($null -ne $application) {{ try {{ $application.Quit() }} catch {{}} }}
    [GC]::Collect()
    [GC]::WaitForPendingFinalizers()
}}
"""


def _convert_pptx_pdf(
    source: Path,
    target: Path,
    environment: dict[str, Any],
    timeout: float,
) -> dict[str, Any]:
    capability = environment["capabilities"]["pptx_to_pdf"]
    backends = list(capability["backends"])
    result: dict[str, Any] = {
        "success": False,
        "available": bool(backends),
        "backend": None,
        "attempts": [],
        "error": capability["degradation"],
    }
    if not backends:
        return result

    target.parent.mkdir(parents=True, exist_ok=True)
    for backend in backends:
        temporary = _fresh_temp_path(target.parent, ".pdf")
        if backend == "libreoffice":
            executable = _command_path(environment, "libreoffice")
            assert executable
            with tempfile.TemporaryDirectory(prefix="figure-lo-") as work_name:
                work = Path(work_name)
                profile = work / "profile"
                profile.mkdir()
                command = [
                    executable,
                    "--headless",
                    f"-env:UserInstallation={profile.resolve().as_uri()}",
                    "--convert-to",
                    "pdf:impress_pdf_Export",
                    "--outdir",
                    str(work),
                    str(source),
                ]
                attempt = _external_attempt(backend, command, timeout)
                generated = work / f"{source.stem}.pdf"
                if attempt["error"] is None and generated.is_file():
                    shutil.copy2(generated, temporary)
                elif attempt["error"] is None:
                    attempt["error"] = "LibreOffice reported success but did not create the expected PDF"
        elif backend == "powerpoint":
            executable = _command_path(environment, "powershell")
            assert executable
            command = _powershell_command(executable, _powerpoint_pdf_script(source, temporary))
            attempt = _external_attempt(backend, command, timeout)
            # Avoid embedding a large opaque EncodedCommand in an audit report.
            attempt["command"] = [executable, "-NoProfile", "-NonInteractive", "<PowerPoint COM PDF export>"]
        else:
            continue

        passed, detail = _validated_output(temporary, "pdf")
        if attempt["error"] is None and not passed:
            attempt["error"] = f"output validation failed: {detail}"
        result["attempts"].append(attempt)
        if attempt["error"] is None and passed:
            os.replace(temporary, target)
            result.update(success=True, backend=backend, error=None)
            return result
        temporary.unlink(missing_ok=True)

    result["error"] = "all available PPTX-to-PDF backends failed"
    return result


def _natural_page_key(path: Path) -> tuple[int, str]:
    matches = re.findall(r"(\d+)", path.stem)
    return (int(matches[-1]) if matches else 0, path.name.lower())


def _valid_png_set(paths: Iterable[Path], expected_count: int | None = None) -> tuple[bool, str]:
    values = list(paths)
    if not values:
        return False, "renderer produced no PNG pages"
    if expected_count is not None and len(values) != expected_count:
        return False, f"renderer produced {len(values)} PNG page(s); expected {expected_count}"
    for path in values:
        passed, detail = _validated_output(path, "png")
        if not passed:
            return False, f"{path.name}: {detail}"
    return True, f"validated {len(values)} PNG page(s)"


def _convert_pdf_pngs(
    source: Path,
    work_root: Path,
    environment: dict[str, Any],
    dpi: int,
    timeout: float,
    expected_count: int,
) -> dict[str, Any]:
    capability = environment["capabilities"]["pdf_to_png"]
    backends = list(capability["backends"])
    result: dict[str, Any] = {
        "success": False,
        "available": bool(backends),
        "backend": None,
        "attempts": [],
        "paths": [],
        "error": capability["degradation"],
    }
    if not backends:
        return result

    for index, backend in enumerate(backends, start=1):
        attempt_dir = work_root / f"raster-{index}-{backend}"
        attempt_dir.mkdir(parents=True, exist_ok=True)
        prefix = attempt_dir / "page"
        if backend == "pymupdf":
            def render_with_pymupdf() -> None:
                import fitz  # type: ignore[import-not-found]

                document = fitz.open(str(source))
                try:
                    scale = dpi / 72.0
                    matrix = fitz.Matrix(scale, scale)
                    for page_index, page in enumerate(document, start=1):
                        pixmap = page.get_pixmap(matrix=matrix, alpha=False)
                        pixmap.save(str(attempt_dir / f"page-{page_index:03d}.png"))
                finally:
                    document.close()

            attempt = _module_attempt(backend, render_with_pymupdf)
        elif backend == "pdftocairo":
            executable = _command_path(environment, "pdftocairo")
            assert executable
            attempt = _external_attempt(
                backend,
                [executable, "-png", "-r", str(dpi), str(source), str(prefix)],
                timeout,
            )
        elif backend == "pdftoppm":
            executable = _command_path(environment, "pdftoppm")
            assert executable
            attempt = _external_attempt(
                backend,
                [executable, "-png", "-r", str(dpi), str(source), str(prefix)],
                timeout,
            )
        elif backend == "mutool":
            executable = _command_path(environment, "mutool")
            assert executable
            attempt = _external_attempt(
                backend,
                [executable, "draw", "-r", str(dpi), "-o", str(attempt_dir / "page-%03d.png"), str(source)],
                timeout,
            )
        elif backend == "imagemagick":
            executable = _command_path(environment, "imagemagick")
            assert executable
            attempt = _external_attempt(
                backend,
                [executable, "-density", str(dpi), str(source), str(attempt_dir / "page-%03d.png")],
                timeout,
            )
        else:
            continue

        paths = sorted(attempt_dir.glob("*.png"), key=_natural_page_key)
        passed, detail = _valid_png_set(paths, expected_count)
        if attempt["error"] is None and not passed:
            attempt["error"] = f"output validation failed: {detail}"
        result["attempts"].append(attempt)
        if attempt["error"] is None and passed:
            result.update(success=True, backend=backend, paths=paths, error=None)
            return result

    result["error"] = "all available PDF rasterization backends failed"
    return result


def _convert_powerpoint_pngs(
    source: Path,
    work_root: Path,
    environment: dict[str, Any],
    dpi: int,
    timeout: float,
    expected_count: int,
) -> dict[str, Any]:
    available = bool(environment["powerpoint"]["available"])
    result: dict[str, Any] = {
        "success": False,
        "available": available,
        "backend": None,
        "attempts": [],
        "paths": [],
        "error": "PowerPoint direct export is unavailable",
    }
    if not available:
        return result

    executable = _command_path(environment, "powershell")
    if not executable:
        return result
    attempt_dir = work_root / "powerpoint-direct"
    attempt_dir.mkdir(parents=True, exist_ok=True)
    command = _powershell_command(executable, _powerpoint_png_script(source, attempt_dir, dpi))
    attempt = _external_attempt("powerpoint-direct", command, timeout)
    attempt["command"] = [executable, "-NoProfile", "-NonInteractive", "<PowerPoint COM slide PNG export>"]
    paths = sorted(attempt_dir.glob("slide-*.png"), key=_natural_page_key)
    passed, detail = _valid_png_set(paths, expected_count)
    if attempt["error"] is None and not passed:
        attempt["error"] = f"output validation failed: {detail}"
    result["attempts"].append(attempt)
    if attempt["error"] is None and passed:
        result.update(success=True, backend="powerpoint-direct", paths=paths, error=None)
    else:
        result["error"] = "PowerPoint direct PNG export failed"
    return result


def _commit_pngs(paths: list[Path], target_dir: Path, overwrite: bool) -> list[Path]:
    target_dir.parent.mkdir(parents=True, exist_ok=True)
    target_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=".slides-transaction-", dir=str(target_dir.parent)
    ) as transaction_name:
        transaction = Path(transaction_name)
        staged_dir = transaction / "new"
        backup_dir = transaction / "old"
        staged_dir.mkdir()
        backup_dir.mkdir()

        staged: list[Path] = []
        for index, source in enumerate(paths, start=1):
            staged_path = staged_dir / f"slide-{index:03d}.png"
            shutil.copy2(source, staged_path)
            staged.append(staged_path)
        passed, detail = _valid_png_set(staged, len(paths))
        if not passed:
            raise ValueError(f"staged slide transaction failed validation: {detail}")

        old_paths = sorted(
            (path for path in target_dir.glob("slide-*.png") if path.is_file()),
            key=_natural_page_key,
        )
        if old_paths and not overwrite:
            raise FileExistsError("slide PNG targets appeared during rendering; rerun with --overwrite")

        moved_old: list[tuple[Path, Path]] = []
        placed_new: list[Path] = []
        try:
            for old in old_paths:
                backup = backup_dir / old.name
                os.replace(old, backup)
                moved_old.append((old, backup))
            for staged_path in staged:
                target = target_dir / staged_path.name
                if target.exists() and not overwrite:
                    raise FileExistsError(f"target appeared during rendering: {target}")
                os.replace(staged_path, target)
                placed_new.append(target)
        except Exception:
            for target in placed_new:
                try:
                    target.unlink(missing_ok=True)
                except OSError:
                    pass
            for original, backup in reversed(moved_old):
                try:
                    if backup.exists():
                        os.replace(backup, original)
                except OSError:
                    pass
            raise
        return placed_new


def _new_artifact(source: Path, output_format: str, target: Path) -> dict[str, Any]:
    return {
        "source": str(source),
        "source_type": source.suffix.lower().lstrip("."),
        "target_format": output_format,
        "target": str(target),
        "status": "pending",
        "reason_code": None,
        "backend": None,
        "route": None,
        "attempts": [],
        "outputs": [],
        "message": None,
    }


def _mark_existing(artifact: dict[str, Any], paths: list[Path]) -> None:
    artifact.update(
        status="skipped",
        reason_code="output_exists",
        message="output already exists; pass --overwrite to replace generated files",
        outputs=[_path_metadata(path) for path in paths],
    )


def _finish_conversion(artifact: dict[str, Any], conversion: dict[str, Any], target: Path) -> None:
    artifact["attempts"] = conversion["attempts"]
    artifact["backend"] = conversion["backend"]
    if conversion["success"]:
        artifact.update(
            status="rendered",
            reason_code=None,
            message="rendered and passed structural output validation",
            outputs=[_path_metadata(target)],
        )
    elif conversion["available"]:
        artifact.update(status="failed", reason_code="conversion_failed", message=conversion["error"])
    else:
        artifact.update(status="skipped", reason_code="no_backend", message=conversion["error"])


def _process_svg(
    source: Path,
    output_stem: str,
    output_dir: Path,
    formats: list[str],
    environment: dict[str, Any],
    dpi: int,
    timeout: float,
    overwrite: bool,
) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []
    for output_format in formats:
        target = output_dir / f"{output_stem}.{output_format}"
        artifact = _new_artifact(source, output_format, target)
        artifacts.append(artifact)
        if target.exists() and not target.is_file():
            artifact.update(
                status="failed",
                reason_code="invalid_target",
                message="target path exists and is not a regular file",
            )
            continue
        if target.exists() and not overwrite:
            _mark_existing(artifact, [target])
            continue
        try:
            conversion = _convert_svg(source, target, output_format, environment, dpi, timeout)
            _finish_conversion(artifact, conversion, target)
        except Exception as exc:
            artifact.update(
                status="failed",
                reason_code="internal_error",
                message=f"unexpected SVG renderer error: {type(exc).__name__}: {exc}",
            )
    return artifacts


def _process_pptx(
    source: Path,
    output_stem: str,
    output_dir: Path,
    formats: list[str],
    environment: dict[str, Any],
    dpi: int,
    timeout: float,
    overwrite: bool,
    expected_slide_count: int,
) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []
    pdf_artifact: dict[str, Any] | None = None
    pdf_target = output_dir / f"{output_stem}.pdf"

    if "pdf" in formats:
        pdf_artifact = _new_artifact(source, "pdf", pdf_target)
        artifacts.append(pdf_artifact)
        if pdf_target.exists() and not pdf_target.is_file():
            pdf_artifact.update(
                status="failed",
                reason_code="invalid_target",
                message="target path exists and is not a regular file",
            )
        elif pdf_target.exists() and not overwrite:
            _mark_existing(pdf_artifact, [pdf_target])
        else:
            try:
                conversion = _convert_pptx_pdf(source, pdf_target, environment, timeout)
                _finish_conversion(pdf_artifact, conversion, pdf_target)
            except Exception as exc:
                pdf_artifact.update(
                    status="failed",
                    reason_code="internal_error",
                    message=f"unexpected PPTX-to-PDF error: {type(exc).__name__}: {exc}",
                )

    if "png" not in formats:
        return artifacts

    png_dir = output_dir / f"{output_stem}-slides"
    png_artifact = _new_artifact(source, "png", png_dir)
    artifacts.append(png_artifact)
    if png_dir.exists() and not png_dir.is_dir():
        png_artifact.update(
            status="failed",
            reason_code="invalid_target",
            message="PNG target path exists and is not a directory",
        )
        return artifacts
    slide_entries = list(png_dir.glob("slide-*.png")) if png_dir.exists() else []
    invalid_entries = [
        entry for entry in slide_entries if not entry.is_file() or entry.is_symlink()
    ]
    if invalid_entries:
        png_artifact.update(
            status="failed",
            reason_code="invalid_target",
            message=(
                "slide target contains non-regular or symbolic-link path(s): "
                + ", ".join(str(entry) for entry in sorted(invalid_entries, key=lambda item: item.name))
            ),
        )
        return artifacts
    existing_pngs = sorted(slide_entries, key=_natural_page_key)
    if existing_pngs and not overwrite:
        _mark_existing(png_artifact, existing_pngs)
        return artifacts

    attempts: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="figure-png-") as work_name:
        work = Path(work_name)
        try:
            direct = _convert_powerpoint_pngs(
                source, work, environment, dpi, timeout, expected_slide_count
            )
        except Exception as exc:
            direct = {
                "success": False,
                "available": bool(environment["powerpoint"]["available"]),
                "backend": None,
                "attempts": [
                    {
                        "backend": "powerpoint-direct",
                        "command": None,
                        "returncode": None,
                        "stdout": "",
                        "stderr": "",
                        "timed_out": False,
                        "error": f"unexpected direct-export error: {type(exc).__name__}: {exc}",
                    }
                ],
                "paths": [],
                "error": "PowerPoint direct PNG export raised an unexpected error",
            }
        attempts.extend(direct["attempts"])
        if direct["success"]:
            try:
                outputs = _commit_pngs(direct["paths"], png_dir, overwrite)
                png_artifact.update(
                    status="rendered",
                    backend=direct["backend"],
                    route="pptx->png",
                    attempts=attempts,
                    outputs=[_path_metadata(path) for path in outputs],
                    message="rendered one validated PNG per slide",
                )
            except Exception as exc:
                png_artifact.update(
                    status="failed",
                    reason_code="commit_failed",
                    backend=direct["backend"],
                    route="pptx->png",
                    attempts=attempts,
                    message=f"slide transaction failed and was rolled back: {type(exc).__name__}: {exc}",
                )
            return artifacts

        # Use the PDF already rendered in this invocation when possible.  An
        # existing skipped PDF is not trusted because it may be stale.
        intermediate_pdf: Path
        pdf_backend: str | None = None
        if pdf_artifact and pdf_artifact["status"] == "rendered" and pdf_target.is_file():
            intermediate_pdf = pdf_target
            pdf_backend = pdf_artifact["backend"]
        else:
            intermediate_pdf = work / "intermediate.pdf"
            try:
                intermediate = _convert_pptx_pdf(source, intermediate_pdf, environment, timeout)
            except Exception as exc:
                intermediate = {
                    "success": False,
                    "available": bool(environment["capabilities"]["pptx_to_pdf"]["available"]),
                    "backend": None,
                    "attempts": [
                        {
                            "backend": "pptx-to-pdf",
                            "command": None,
                            "returncode": None,
                            "stdout": "",
                            "stderr": "",
                            "timed_out": False,
                            "error": f"unexpected intermediate-PDF error: {type(exc).__name__}: {exc}",
                        }
                    ],
                    "error": "PPTX-to-PDF intermediate raised an unexpected error",
                }
            attempts.extend(intermediate["attempts"])
            if not intermediate["success"]:
                route_available = direct["available"] or intermediate["available"]
                png_artifact.update(
                    status="failed" if route_available else "skipped",
                    reason_code="conversion_failed" if route_available else "no_backend",
                    attempts=attempts,
                    message=(
                        "PPTX-to-PNG requires PowerPoint direct export or a working PPTX-to-PDF backend"
                    ),
                )
                return artifacts
            pdf_backend = intermediate["backend"]

        try:
            raster = _convert_pdf_pngs(
                intermediate_pdf, work, environment, dpi, timeout, expected_slide_count
            )
        except Exception as exc:
            raster = {
                "success": False,
                "available": bool(environment["capabilities"]["pdf_to_png"]["available"]),
                "backend": None,
                "attempts": [
                    {
                        "backend": "pdf-to-png",
                        "command": None,
                        "returncode": None,
                        "stdout": "",
                        "stderr": "",
                        "timed_out": False,
                        "error": f"unexpected rasterization error: {type(exc).__name__}: {exc}",
                    }
                ],
                "paths": [],
                "error": "PDF rasterization raised an unexpected error",
            }
        attempts.extend(raster["attempts"])
        if raster["success"]:
            try:
                outputs = _commit_pngs(raster["paths"], png_dir, overwrite)
                png_artifact.update(
                    status="rendered",
                    backend=f"{pdf_backend}+{raster['backend']}",
                    route="pptx->pdf->png",
                    attempts=attempts,
                    outputs=[_path_metadata(path) for path in outputs],
                    message="rendered one validated PNG per slide through a PDF intermediate",
                )
            except Exception as exc:
                png_artifact.update(
                    status="failed",
                    reason_code="commit_failed",
                    backend=f"{pdf_backend}+{raster['backend']}",
                    route="pptx->pdf->png",
                    attempts=attempts,
                    message=f"slide transaction failed and was rolled back: {type(exc).__name__}: {exc}",
                )
        else:
            png_artifact.update(
                status="failed" if (direct["available"] or raster["available"]) else "skipped",
                reason_code=(
                    "conversion_failed" if (direct["available"] or raster["available"]) else "no_backend"
                ),
                attempts=attempts,
                message=raster["error"],
            )
    return artifacts


def _invalid_source_artifacts(
    source: Path,
    output_stem: str,
    output_dir: Path,
    formats: list[str],
    validation: dict[str, Any],
) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []
    for output_format in formats:
        if source.suffix.lower() == ".pptx" and output_format == "png":
            target = output_dir / f"{output_stem}-slides"
        else:
            target = output_dir / f"{output_stem}.{output_format}"
        artifact = _new_artifact(source, output_format, target)
        artifact.update(
            status="failed",
            reason_code="source_invalid",
            message=validation["details"],
        )
        artifacts.append(artifact)
    return artifacts


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Render SVG/PPTX derivatives with installed tools only and write qa-report.json. "
            "Unavailable optional backends degrade to a documented skip."
        )
    )
    parser.add_argument("inputs", nargs="+", type=Path, metavar="INPUT", help="SVG or PPTX source file")
    parser.add_argument(
        "--output-dir",
        type=Path,
        metavar="DIR",
        help="artifact directory (default: rendered/ beside one input, or ./rendered for many)",
    )
    parser.add_argument(
        "--report",
        type=Path,
        metavar="PATH",
        help="QA report path (default: OUTPUT_DIR/qa-report.json)",
    )
    parser.add_argument(
        "--formats",
        nargs="+",
        choices=SUPPORTED_FORMATS,
        default=list(SUPPORTED_FORMATS),
        metavar="FORMAT",
        help="requested derivatives: png, pdf, or both (default: png pdf)",
    )
    parser.add_argument("--dpi", type=int, default=180, help="PNG raster resolution (default: 180)")
    parser.add_argument(
        "--timeout",
        type=float,
        default=180.0,
        metavar="SECONDS",
        help="timeout for each external conversion attempt (default: 180)",
    )
    parser.add_argument("--overwrite", action="store_true", help="replace generated targets")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="return status 2 when any requested derivative is skipped or fails",
    )
    parser.add_argument(
        "--no-version-checks",
        action="store_true",
        help="skip backend version subprocesses during environment inspection",
    )
    parser.add_argument("--quiet", action="store_true", help="suppress the one-line summary")
    return parser


def _default_output_dir(inputs: list[Path]) -> Path:
    if len(inputs) == 1:
        return inputs[0].parent / "rendered"
    return Path.cwd() / "rendered"


def _output_stems(inputs: list[Path]) -> list[str]:
    """Return case-insensitively unique names without discarding source identity."""

    counts: dict[str, int] = {}
    for source in inputs:
        key = (source.stem or "figure").casefold()
        counts[key] = counts.get(key, 0) + 1

    used: dict[str, int] = {}
    values: list[str] = []
    for source in inputs:
        stem = source.stem or "figure"
        if counts[stem.casefold()] > 1:
            digest = hashlib.sha256(str(source).encode("utf-8")).hexdigest()[:8]
            stem = f"{stem}-{digest}"
        key = stem.casefold()
        occurrence = used.get(key, 0) + 1
        used[key] = occurrence
        values.append(stem if occurrence == 1 else f"{stem}-{occurrence}")
    return values


def _same_location(first: Path, second: Path) -> bool:
    first_key = os.path.normcase(os.path.abspath(str(first)))
    second_key = os.path.normcase(os.path.abspath(str(second)))
    if first_key == second_key:
        return True
    try:
        return first.exists() and second.exists() and os.path.samefile(first, second)
    except OSError:
        return False


def _path_within(child: Path, parent: Path) -> bool:
    child_key = os.path.normcase(os.path.abspath(str(child)))
    parent_key = os.path.normcase(os.path.abspath(str(parent)))
    try:
        return os.path.commonpath([child_key, parent_key]) == parent_key
    except ValueError:
        return False


def _planned_targets(
    inputs: list[Path],
    output_stems: list[str],
    output_dir: Path,
    formats: list[str],
) -> tuple[list[Path], list[Path]]:
    files: list[Path] = []
    slide_dirs: list[Path] = []
    for source, stem in zip(inputs, output_stems):
        if source.suffix.lower() == ".pptx":
            if "pdf" in formats:
                files.append(output_dir / f"{stem}.pdf")
            if "png" in formats:
                slide_dirs.append(output_dir / f"{stem}-slides")
        else:
            files.extend(output_dir / f"{stem}.{output_format}" for output_format in formats)
    return files, slide_dirs


def _report_conflicts(
    report_path: Path,
    inputs: list[Path],
    planned_files: list[Path],
    slide_dirs: list[Path],
    output_dir: Path,
) -> list[str]:
    errors: list[str] = []
    if _same_location(report_path, output_dir):
        errors.append("report path is the output directory")
    if report_path.exists() and report_path.is_dir():
        errors.append("report path is an existing directory")
    for source in inputs:
        if _same_location(report_path, source):
            errors.append(f"report path conflicts with source: {source}")
    for target in planned_files:
        if _same_location(report_path, target) or _path_within(report_path, target):
            errors.append(f"report path conflicts with planned file output: {target}")
    for slide_dir in slide_dirs:
        if _path_within(report_path, slide_dir):
            errors.append(f"report path is inside planned slide output directory: {slide_dir}")
    return list(dict.fromkeys(errors))


def _fallback_report_roots(output_dir: Path, parent_override: Path | None) -> list[Path]:
    raw_roots = [
        parent_override,
        output_dir if (not output_dir.exists() or output_dir.is_dir()) else None,
        output_dir.parent,
        Path.cwd(),
        Path(tempfile.gettempdir()),
        Path.home(),
    ]
    roots: list[Path] = []
    seen: set[str] = set()
    for raw_root in raw_roots:
        if raw_root is None:
            continue
        try:
            root = raw_root.expanduser().resolve()
        except OSError:
            continue
        key = os.path.normcase(os.path.abspath(str(root)))
        if key in seen or (root.exists() and not root.is_dir()):
            continue
        seen.add(key)
        roots.append(root)
    return roots


def _fallback_report_candidates(
    output_dir: Path,
    inputs: list[Path],
    planned_files: list[Path],
    slide_dirs: list[Path],
    *,
    parent_override: Path | None = None,
) -> Iterable[Path]:
    del slide_dirs  # A unique .json fallback is safe inside a slide directory.
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    for root_index, root in enumerate(_fallback_report_roots(output_dir, parent_override)):
        for index in range(64):
            suffix = "" if index == 0 else f"-{index}"
            candidate = root / f"qa-report-preflight-{stamp}-{os.getpid()}-{root_index}{suffix}.json"
            try:
                candidate = candidate.resolve()
                conflicts = (
                    candidate.exists()
                    or _same_location(candidate, output_dir)
                    or any(_same_location(candidate, source) for source in inputs)
                    or any(_same_location(candidate, target) for target in planned_files)
                )
            except OSError:
                continue
            if not conflicts:
                yield candidate
                break


def _fallback_report_path(
    output_dir: Path,
    inputs: list[Path],
    planned_files: list[Path],
    slide_dirs: list[Path],
    *,
    parent_override: Path | None = None,
) -> Path:
    candidate = next(
        iter(
            _fallback_report_candidates(
                output_dir,
                inputs,
                planned_files,
                slide_dirs,
                parent_override=parent_override,
            )
        ),
        None,
    )
    if candidate is None:
        raise OSError("could not select a collision-free fallback QA report path")
    return candidate


def _write_report_resilient(
    report_path: Path,
    report: dict[str, Any],
    output_dir: Path,
    inputs: list[Path],
    planned_files: list[Path],
    slide_dirs: list[Path],
) -> Path:
    try:
        _atomic_write_json(report_path, report)
        return report_path
    except OSError as first_error:
        failures = [
            f"{report_path}: {type(first_error).__name__}: {first_error}"
        ]
        for fallback in _fallback_report_candidates(
            output_dir,
            inputs,
            planned_files,
            slide_dirs,
            parent_override=Path.cwd(),
        ):
            if _same_location(fallback, report_path):
                continue
            report["request"]["report_path_effective"] = str(fallback)
            report["report_write_warnings"] = [
                "report write required fallback; failed path(s): " + " | ".join(failures)
            ]
            try:
                _atomic_write_json(fallback, report)
                return fallback
            except OSError as fallback_error:
                failures.append(
                    f"{fallback}: {type(fallback_error).__name__}: {fallback_error}"
                )
                continue
        raise OSError("all QA report destinations failed: " + " | ".join(failures))


def _failed_environment(message: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "checked_at": _utc_now(),
        "read_only_probe": True,
        "automatic_installation": False,
        "probe_error": message,
        "capabilities": {},
        "degradation": {"level": 2, "grade": "source-only"},
    }


def _avoid_physical_report_alias(
    report_path: Path,
    report: dict[str, Any],
    artifacts: list[dict[str, Any]],
    output_dir: Path,
    inputs: list[Path],
    planned_files: list[Path],
    slide_dirs: list[Path],
) -> Path:
    """Recheck aliases after rendering, when samefile can see new outputs."""

    conflicts: list[Path] = []
    for artifact in artifacts:
        for output in artifact.get("outputs", []):
            output_value = output.get("path") if isinstance(output, dict) else None
            if not output_value:
                continue
            output_path = Path(output_value)
            if _same_location(report_path, output_path):
                conflicts.append(output_path)
    if not conflicts:
        return report_path

    fallback = _fallback_report_path(
        output_dir, inputs, planned_files, slide_dirs
    )
    report.setdefault("report_path_safety_warnings", []).append(
        "requested report path became a physical alias of rendered output(s): "
        + ", ".join(str(path) for path in conflicts)
    )
    report["request"]["report_path_effective"] = str(fallback)
    return fallback


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not 36 <= args.dpi <= 1200:
        parser.error("--dpi must be between 36 and 1200")
    if args.timeout <= 0:
        parser.error("--timeout must be greater than zero")

    inputs = [path.expanduser().resolve() for path in args.inputs]
    output_stems = _output_stems(inputs)
    output_dir = (args.output_dir or _default_output_dir(inputs)).expanduser().resolve()
    formats = list(dict.fromkeys(args.formats))
    requested_report_path = (
        args.report or (output_dir / "qa-report.json")
    ).expanduser().resolve()
    planned_files, slide_dirs = _planned_targets(inputs, output_stems, output_dir, formats)
    setup_errors = _report_conflicts(
        requested_report_path, inputs, planned_files, slide_dirs, output_dir
    )
    report_path = requested_report_path
    if setup_errors:
        report_path = _fallback_report_path(
            output_dir, inputs, planned_files, slide_dirs
        )

    try:
        if output_dir.exists() and not output_dir.is_dir():
            raise NotADirectoryError(f"output path is not a directory: {output_dir}")
        output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        setup_errors.append(f"cannot prepare output directory: {type(exc).__name__}: {exc}")
        if args.report is None:
            report_path = _fallback_report_path(
                output_dir,
                inputs,
                planned_files,
                slide_dirs,
                parent_override=Path.cwd(),
            )

    try:
        environment = inspect_environment(
            check_versions=not args.no_version_checks,
            timeout=min(args.timeout, 10.0),
        )
    except Exception as exc:
        message = f"environment inspection failed: {type(exc).__name__}: {exc}"
        setup_errors.append(message)
        environment = _failed_environment(message)

    if setup_errors:
        message = "; ".join(setup_errors)
        source_checks = [
            {
                "path": str(source),
                "type": source.suffix.lower().lstrip("."),
                "passed": False,
                "skipped": True,
                "details": "source validation was skipped because render preflight failed",
                "size_bytes": None,
                "sha256": None,
                "slide_count": None,
            }
            for source in inputs
        ]
        artifacts: list[dict[str, Any]] = []
        for source, output_stem in zip(inputs, output_stems):
            failed_items = _invalid_source_artifacts(
                source,
                output_stem,
                output_dir,
                formats,
                {"details": message},
            )
            for artifact in failed_items:
                artifact["reason_code"] = "configuration_error"
            artifacts.extend(failed_items)
        summary = {
            "requested": len(artifacts),
            "rendered": 0,
            "skipped": 0,
            "failed": len(artifacts),
        }
        report = {
            "schema_version": SCHEMA_VERSION,
            "generated_at": _utc_now(),
            "status": "failed",
            "request": {
                "inputs": [str(path) for path in inputs],
                "output_names": [
                    {"source": str(source), "stem": stem}
                    for source, stem in zip(inputs, output_stems)
                ],
                "output_dir": str(output_dir),
                "formats": formats,
                "dpi": args.dpi,
                "timeout_seconds": args.timeout,
                "overwrite": args.overwrite,
                "strict": args.strict,
                "report_path_requested": str(requested_report_path),
                "report_path_effective": str(report_path),
            },
            "policy": {
                "automatic_installation": False,
                "missing_backend_is_degraded_skip": True,
                "source_files_modified": False,
            },
            "configuration_errors": setup_errors,
            "environment": environment,
            "source_checks": source_checks,
            "artifacts": artifacts,
            "summary": summary,
        }
        try:
            report_path = _write_report_resilient(
                report_path,
                report,
                output_dir,
                inputs,
                planned_files,
                slide_dirs,
            )
        except OSError as exc:
            print(f"could not write QA report: {exc}", file=sys.stderr)
            return 1
        if not args.quiet:
            print(f"rendered=0 skipped=0 failed={len(artifacts)} report={report_path}")
        return 2 if args.strict else 1

    source_checks: list[dict[str, Any]] = []
    artifacts: list[dict[str, Any]] = []
    for source, output_stem in zip(inputs, output_stems):
        try:
            validation = _validate_source(source)
        except Exception as exc:
            validation = {
                "path": str(source),
                "type": source.suffix.lower().lstrip("."),
                "passed": False,
                "details": f"source validation error: {type(exc).__name__}: {exc}",
                "size_bytes": None,
                "sha256": None,
            }
        source_checks.append(validation)
        if not validation["passed"]:
            artifacts.extend(
                _invalid_source_artifacts(source, output_stem, output_dir, formats, validation)
            )
            continue
        try:
            if source.suffix.lower() == ".svg":
                artifacts.extend(
                    _process_svg(
                        source,
                        output_stem,
                        output_dir,
                        formats,
                        environment,
                        args.dpi,
                        args.timeout,
                        args.overwrite,
                    )
                )
            else:
                artifacts.extend(
                    _process_pptx(
                        source,
                        output_stem,
                        output_dir,
                        formats,
                        environment,
                        args.dpi,
                        args.timeout,
                        args.overwrite,
                        int(validation["slide_count"]),
                    )
                )
        except Exception as exc:
            internal_validation = {
                "details": f"unexpected renderer error: {type(exc).__name__}: {exc}"
            }
            internal_artifacts = _invalid_source_artifacts(
                source, output_stem, output_dir, formats, internal_validation
            )
            for artifact in internal_artifacts:
                artifact["reason_code"] = "internal_error"
            artifacts.extend(internal_artifacts)

    summary = {
        "requested": len(artifacts),
        "rendered": sum(item["status"] == "rendered" for item in artifacts),
        "skipped": sum(item["status"] == "skipped" for item in artifacts),
        "failed": sum(item["status"] == "failed" for item in artifacts),
    }
    status = "failed" if summary["failed"] else "partial" if summary["skipped"] else "passed"
    report = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _utc_now(),
        "status": status,
        "request": {
            "inputs": [str(path) for path in inputs],
            "output_names": [
                {"source": str(source), "stem": stem}
                for source, stem in zip(inputs, output_stems)
            ],
            "output_dir": str(output_dir),
            "formats": formats,
            "dpi": args.dpi,
            "timeout_seconds": args.timeout,
            "overwrite": args.overwrite,
            "strict": args.strict,
            "report_path_requested": str(requested_report_path),
            "report_path_effective": str(report_path),
        },
        "policy": {
            "automatic_installation": False,
            "missing_backend_is_degraded_skip": True,
            "source_files_modified": False,
        },
        "environment": environment,
        "source_checks": source_checks,
        "artifacts": artifacts,
        "summary": summary,
    }
    report_path = _avoid_physical_report_alias(
        report_path,
        report,
        artifacts,
        output_dir,
        inputs,
        planned_files,
        slide_dirs,
    )
    try:
        report_path = _write_report_resilient(
            report_path,
            report,
            output_dir,
            inputs,
            planned_files,
            slide_dirs,
        )
    except OSError as exc:
        print(f"could not write QA report: {exc}", file=sys.stderr)
        return 1

    if not args.quiet:
        print(
            f"rendered={summary['rendered']} skipped={summary['skipped']} "
            f"failed={summary['failed']} report={report_path}"
        )
    if args.strict and (summary["skipped"] or summary["failed"]):
        return 2
    return 1 if summary["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

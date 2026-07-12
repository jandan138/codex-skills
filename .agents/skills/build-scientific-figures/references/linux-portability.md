# Linux portability and rendering backends

Use this reference when a scientific-figure job must run on Linux, in a
container, through WSL, or on both Linux and Windows. The skill's authoritative
artifacts remain `figure-spec.json` and SVG; PPTX is an editable delivery format,
not the cross-platform source of truth.

## Contents

- [Portability contract](#portability-contract)
- [Inspect before rendering](#inspect-before-rendering)
- [Backend selection and fallback order](#backend-selection-and-fallback-order)
- [Optional Linux packages](#optional-linux-packages)
- [Render commands and output layout](#render-commands-and-output-layout)
- [Understand `qa-report.json`](#understand-qa-reportjson)
- [Fonts and layout fidelity](#fonts-and-layout-fidelity)
- [Headless Linux, containers, and WSL](#headless-linux-containers-and-wsl)
- [Release checklist](#release-checklist)

## Portability contract

- Run the scripts with Python 3.10 or newer. The scripts themselves use only the
  Python standard library.
- Treat every renderer as optional. Detect installed capabilities; never run
  `pip`, `apt`, `dnf`, `pacman`, or another installer automatically.
- Preserve SVG and PPTX sources when a derivative cannot be rendered. A missing
  backend is a documented degradation (`skipped`), not silent success.
- Generate `qa-report.json` for every parsed render request with a writable
  report destination. Preflight or write failures try collision-free fallback
  reports across the output directory, its parent, the current working
  directory, the system temporary directory, and the user's home directory.
  Use `--strict` only in CI or another workflow where missing derivatives must
  fail the job.
- Do not assume pixel-identical output across renderers. Fonts, SVG filters,
  transparency, color management, and office-layout engines can differ.

## Inspect before rendering

Run the read-only probe:

```bash
python scripts/check_environment.py --pretty
python scripts/check_environment.py --json build/environment.json --quiet
```

The probe reports three degradation grades:

| Level | Grade | Meaning |
|---:|---|---|
| 0 | `full` | Every advertised SVG, PPTX, PDF, and PNG route is available. |
| 1 | `partial` | At least one derivative route is available; unavailable routes must be skipped. |
| 2 | `source-only` | No derivative renderer was found; retain and validate source artifacts only. |

By default, command backends must return an allowed status and recognizable
product/version text. If the first command name fails verification, the probe
continues through aliases such as `magick` to `convert`, `soffice` to
`libreoffice`, and `pwsh` to `powershell`. Optional Python modules pass an
isolated smoke test (CairoSVG renders a minimal in-memory SVG; PyMuPDF opens an
empty document). Node packages must load with `require()`, and the exact
Sharp/PDFKit helper renders a temporary PNG and PDF before either route is
advertised. `--no-version-checks` leaves command entries as `located` but
`verification: not-run`; reserve that faster mode for diagnostics, not a strict
CI capability gate. Python and Node renderer smoke tests still run in that mode.

To gate one capability, repeat `--require` as needed:

```bash
python scripts/check_environment.py --require svg-png --require svg-pdf
```

Use `--strict` on the probe to require all advertised conversion capabilities.
The probe returns `0` when requirements are met and `2` when a required
capability is absent.

## Backend selection and fallback order

The renderer tries each installed backend in order and validates the output
signature before accepting it.

| Route | Backend order | Degraded result when unavailable |
|---|---|---|
| SVG to PNG/PDF | CairoSVG; Sharp (+ PDFKit for PDF); Inkscape; `rsvg-convert`; ImageMagick | Keep SVG; mark derivative `skipped`. |
| PPTX to PDF | LibreOffice Impress, Microsoft PowerPoint COM on Windows | Keep editable PPTX; mark PDF `skipped`. |
| PDF to PNG | PyMuPDF, `pdftocairo`, `pdftoppm`, MuPDF `mutool`, ImageMagick | Keep PDF; mark PNGs `skipped`. |
| PPTX to PNG | PowerPoint direct export, then PPTX-to-PDF plus any PDF rasterizer | Keep PPTX and any successful PDF; mark PNGs `skipped`. |

ImageMagick is deliberately last. Its SVG delegates vary by installation, and
many distributions disable PDF decoding through `policy.xml`. A failed backend
does not stop fallback to the next detected backend.

On Linux and macOS, the probe recognizes both ImageMagick 7's `magick` command
and ImageMagick 6's `convert` command. On Windows it ignores `convert.exe`
because that name is also used by an unrelated operating-system utility.

## Optional Linux packages

Choose dependencies explicitly for the required routes. Typical package names
are shown below; confirm names for the target distribution and image.

```bash
# Debian / Ubuntu
sudo apt install inkscape librsvg2-bin libreoffice-impress poppler-utils \
  fonts-dejavu fonts-liberation

# Fedora / RHEL-family
sudo dnf install inkscape librsvg2-tools libreoffice-impress poppler-utils \
  dejavu-sans-fonts liberation-fonts

# Arch Linux
sudo pacman -S inkscape librsvg libreoffice-fresh poppler \
  ttf-dejavu ttf-liberation
```

Alternatively, install the optional Python libraries into a caller-managed
virtual environment:

```bash
python -m pip install -r scripts/requirements.txt
```

These are operator examples only. The skill scripts never execute them.
The requirements add CairoSVG and PyMuPDF for rendering/extraction plus Pillow
for reference analysis and raster comparison. CairoSVG may still require system
Cairo libraries even when its Python package is importable.

For a self-contained Node route with prebuilt Linux binaries, install the Skill's optional package
set. Sharp renders PNG; PDFKit wraps that raster at the correct physical page size for a portable
PDF fallback; PptxGenJS supplies the optional editable projection.

```bash
npm install --prefix scripts
```

The Sharp/PDFKit PDF is raster-backed. Prefer CairoSVG, Inkscape, or `rsvg-convert` when a vector PDF
is required, and record the selected backend in `qa-report.json`. Copying an existing `node_modules`
directory across operating systems or CPU architectures is not treated as installed merely because
`require.resolve()` succeeds: `check_environment.py` loads the native binding and exercises the
same `render_svg.mjs` PNG and PDF routes used for delivery.

## Render commands and output layout

Render both derivatives from SVG:

```bash
python scripts/render_outputs.py figure.svg \
  --output-dir build --formats png pdf --dpi 180
```

Render a PDF and one PNG per slide from PPTX:

```bash
python scripts/render_outputs.py figure.pptx \
  --output-dir build --formats pdf png --dpi 180
```

For one input, the default output directory is `rendered/` beside the source.
For multiple inputs, it is `./rendered`. SVG derivatives are named
`<stem>.png` and `<stem>.pdf`. PPTX slide images are written as
`<stem>-slides/slide-001.png`, `slide-002.png`, and so on. The default report is
`<output-dir>/qa-report.json`.

If multiple inputs have stems that collide case-insensitively, the renderer adds
an eight-character source-path hash (and, for an exact duplicate argument, an
ordinal) to each output stem. This prevents cross-platform overwrite and
`output_exists` misattribution.

Existing generated targets are not replaced unless `--overwrite` is supplied.
When replacing a slide-image set, the script removes only matching
`slide-*.png` files and preserves unrelated files in that directory. New slides
are staged and validated first; a handled commit error restores the prior set.
Any matching `slide-*.png` entry that is a directory, symbolic link, FIFO, or
another non-regular file is an `invalid_target` failure regardless of
`--overwrite`; it is never inventoried as a valid existing slide.

The report path must not alias a source, a planned PDF/PNG, the output directory,
or any path inside a planned slide directory. A conflicting explicit path is
recorded as a preflight failure in a collision-free fallback report; the source
and derivatives are not touched. If a report destination becomes unwritable,
the renderer attempts one unique candidate per fallback root and records every
failed destination. Exhaustion returns a handled report-write failure rather
than an uncaught fallback-selection exception.

Exit statuses are intentionally degradation-aware:

- `0`: no conversion failed; this can include `skipped` derivatives when an
  optional backend is absent.
- `1`: at least one installed backend route was attempted but all candidates
  for a requested derivative failed, or a source/target was invalid.
- `2`: `--strict` was supplied and at least one requested derivative was
  skipped or failed, or command-line syntax/range validation failed before a
  render request could be initialized.

## Understand `qa-report.json`

The report records:

- the exact inputs, formats, DPI, timeout, and overwrite policy;
- source package/XML validation and SHA-256 hashes;
- the read-only environment and capability probe;
- isolated Python-module, Node `require()`, and Node PNG/PDF route smoke results;
- every attempted backend, exit status, bounded stdout/stderr, and failure
  reason;
- output paths, sizes, hashes, full PNG chunk/CRC checks, PDF header/xref/EOF
  checks, and PPTX-slide-to-PNG count checks;
- a summary of `rendered`, `skipped`, and `failed` derivatives.

Interpret status as follows:

- `passed`: every requested derivative rendered successfully.
- `partial`: no renderer failed, but one or more derivatives were intentionally
  skipped (including collision protection or missing backends).
- `failed`: a source was invalid or every detected backend for a requested
  derivative failed.

An existing output skipped without `--overwrite` is inventoried in the report,
but it is not evidence that the existing file corresponds to the current
source. Use an empty output directory or `--overwrite` for reproducible CI.

## Fonts and layout fidelity

Font substitution is the most common cross-platform difference. Before a
release render:

1. Use redistributable fonts that can be installed on every target system.
2. Inspect Linux availability with `fc-match "Font Name"` and `fc-list`.
3. Avoid relying on Microsoft-only fonts unless the deployment image legally
   provides them.
4. Prefer SVG text converted to paths only for final locked artwork. Keep a
   text-editable SVG/PPTX source separately for accessibility and revision.
5. Compare the PNG render with the authoritative SVG after switching renderer,
   office version, or font package.

LibreOffice and PowerPoint use different layout engines. A PPTX that is editable
in both applications can still reflow labels, crop text, or move connectors.
For Linux-first reproducibility, approve the SVG/PDF render as the visual ground
truth and treat PPTX rendering as a compatibility check.

## Headless Linux, containers, and WSL

- LibreOffice is invoked with `--headless` and an isolated temporary user
  profile, avoiding a locked desktop profile and allowing concurrent jobs.
- Ensure the process has writable system temporary storage and a writable
  output directory. Read-only containers need an explicit writable mount.
- Bake renderers and fonts into a pinned container image when repeatability
  matters. Record the image digest beside `qa-report.json`.
- Set a UTF-8 locale in minimal images so non-ASCII labels and paths survive
  command-line conversion.
- Under WSL, prefer files inside the Linux filesystem for heavy rendering.
  `/mnt/c` or `/mnt/g` works but can be slower and may expose case-sensitivity
  differences.
- PowerPoint COM is Windows-only. Do not attempt to call it from Linux or WSL;
  use LibreOffice for PPTX-to-PDF and Poppler/MuPDF for PNG derivation.

## Release checklist

1. Run `check_environment.py` on the actual render host.
2. Confirm required fonts resolve to the expected files.
3. Render into a clean directory with an explicit DPI.
4. Inspect the authoritative SVG plus at least one raster derivative.
5. Review `qa-report.json`; accept every `skipped` item deliberately.
6. Archive the source specification, SVG, derivatives, report, renderer
   versions, and container digest or operating-system version together.

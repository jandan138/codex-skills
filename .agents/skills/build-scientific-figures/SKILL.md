---
name: build-scientific-figures
description: Reconstruct publication-style scientific figures from reference images and create original paper-grounded figures from PDFs, research notes, simulation frames, plots, and user assets. Use when Codex must analyze visual grammar, model scientific semantics and arrow topology, author or validate figure-spec.json, generate SVG/PNG/PDF or optional editable PPTX, create safe SVG icons and placeholders, or run visual and provenance QA for method diagrams, pipelines, architecture figures, and multi-panel research graphics.
---

# Build Scientific Figures

Create reproducible research figures through a reviewed semantic specification rather than a single
image-generation prompt. Treat `figure-spec.json` and canonical SVG as source; treat PNG, PDF, and
PPTX as derived deliverables.

## Non-negotiable rules

- Model scientific meaning before geometry. Inventory nodes, ports, edges, direction, scope, and
  evidence before routing a connector.
- Keep internal temporal/action arrows separate from external data, control, merge, distribution,
  and feedback networks.
- Never invent a scientific relationship, number, unit, capability, or experimental result.
- Preserve provenance for paper claims, user assets, generated icons, simulation renders, and
  external visual material.
- Use real experiment or simulation images as raster assets. Use code-native, sanitized SVG for
  small schematic icons and connector networks.
- Use Linux-safe relative paths, UTF-8, and open fonts. Never require PowerShell, Office COM,
  Windows absolute paths, or a proprietary font for the canonical output.
- Do not mark the semantic graph approved when material ambiguity remains. Ask for review before
  final artwork.
- Render and inspect final artifacts. A correct editable source is not evidence of a correct export.

## Route the task

Read [input-and-modes.md](references/input-and-modes.md), then choose exactly one mode:

- `exact`: authorized coordinate-level reconstruction;
- `inspired`: new composition informed by a reference's visual grammar;
- `original`: paper-driven design from first principles.

For publication-bound work based on another paper, prefer `inspired`. Do not bundle or redistribute
the source reference as a Skill asset unless the repository maintainer explicitly authorizes that
specific file and its provenance and reuse boundary are documented. A bundled case study is not a
license to reuse its third-party reference image in a new publication.

Read only the references required by the task:

- Paper, manuscript, or supplement: [paper-to-figure.md](references/paper-to-figure.md)
- Reference screenshot or design language: [visual-grammar.md](references/visual-grammar.md)
- EBench reference-to-editable-PPTX example: [ebench-case-study.md](references/ebench-case-study.md)
- Story-first paper hero, Figure 1 simplification, or repeated visual-polish iteration: [story-first-hero.md](references/story-first-hero.md)
- Sequence, branch, merge, feedback, or long connector: [arrow-topology.md](references/arrow-topology.md)
- Spec authoring or backend behavior: [figure-spec.md](references/figure-spec.md)
- Linux/runtime capability or fallback: [linux-portability.md](references/linux-portability.md)
- Native PPTX hardening, typography budgets, theme effects, or LibreOffice drift: [pptx-figure-hardening.md](references/pptx-figure-hardening.md)
- Final review and evidence: [qa-rubric.md](references/qa-rubric.md)

## Workflow

### 1. Establish inputs and output contract

Inventory the paper, reference figures, user-owned assets, requested canvas, venue, caption, and
formats. Preserve originals. Create a separate working directory for extracted text, safe SVGs,
specs, renders, and QA evidence.

Run the environment probe before promising derived formats:

```bash
python scripts/check_environment.py --pretty
```

Do not install system or language packages silently. If required portable outputs are unavailable,
report the missing capability and use the commands in `linux-portability.md` after authorization.

### 2. Extract evidence

For a paper PDF:

```bash
python scripts/ingest_paper.py paper.pdf --output-dir work/paper --render-pages
```

For a raster reference:

```bash
python scripts/analyze_reference.py reference.png --output work/reference-analysis.json
```

The reference analyzer provides measurements, not semantics. Inspect the native-resolution image
and manually identify panel hierarchy, text, ports, arrowheads, crossings, junctions, asset crops,
and reading order.

### 3. Build and review the semantic graph

State the figure's one-sentence communication job. Create an inventory of modules, states,
transformations, inputs, outputs, branches, merges, feedback loops, metrics, and results. For every
edge, record source port, destination port, direction, internal/external scope, and meaning.

Show the user or author a compact node-edge table and list every inferred or unverified item. Do
not proceed to final rendering until material ambiguity is resolved. Record approval in
`review.semantic_graph_approved`.

### 4. Author the figure specification

Copy `assets/templates/wide-pipeline.spec.json` only when its topology fits; otherwise create a v1
spec using `assets/figure-spec.schema.json`. Replace neutral labels and geometry rather than forcing
paper semantics into the template. Immediately reset `review.semantic_graph_approved` to `false`
after copying; the template's approval covers only its neutral example, never the adapted figure.

Use stable semantic ids. Resolve all external and internal relationships to declared ports. Keep
real assets replaceable and give each asset meaningful alt text. Use named placeholders when an
asset is missing.

Validate before rendering:

```bash
python scripts/validate_figure_spec.py figure-spec.json --check-assets --require-approved --strict
```

Do not suppress a validation error. Resolve warnings that affect scientific meaning, publication
portability, or final rendering.

### 5. Create and secure vector assets

Generate small icons from simple SVG primitives with a consistent viewBox, stroke width, round caps,
and theme colors. Do not use scripts, `foreignObject`, external URLs, remote fonts, event attributes,
or embedded HTML.

Sanitize every untrusted or model-authored SVG before insertion:

```bash
python scripts/sanitize_svg.py source.svg safe.svg
```

Use only the safe copy in the spec. Preserve source, generator/model, prompt or design brief, date,
and manual edits in provenance.

### 6. Render canonical SVG and portable outputs

```bash
python scripts/build_svg.py figure-spec.json --output out/figure.svg --require-approved
python scripts/render_outputs.py out/figure.svg --output-dir out/rendered
```

The SVG must succeed first. Generate PNG and PDF through the first available verified backend. Keep
the structured `qa-report.json` emitted by the renderer.

When editable PPTX is requested, prefer the installed Presentations skill and its supported
Artifact Tool runtime. If it is unavailable, use the optional public PptxGenJS projection:

```bash
npm install --prefix scripts
node scripts/build_pptx.mjs figure-spec.json --output out/figure.pptx
python scripts/render_outputs.py out/figure.pptx --output-dir out/pptx-render
```

PptxGenJS panels, text, and segmented connectors remain editable, but the canonical SVG controls
exact rounded routes and crops. Do not claim legacy SVG fallback compatibility unless a real raster
fallback was generated and tested.

For a paper hero or editable PPTX, run `scripts/audit_pptx_figure.py` after the final save. Treat
shape, word, font-size, and bold-ratio budgets as context-sensitive diagnostics; set hard limits only
when the author has approved them or when a validated case study supplies a relevant starting point.

### 7. Perform four-layer review

Review in this order:

1. semantics and claims;
2. graph topology and arrow direction;
3. geometry, crops, alignment, and connector landing;
4. style, final rendering, portability, and provenance.

For a reference reconstruction, generate raster evidence:

```bash
python scripts/compare_reference.py reference.png rendered.png \
  --output-dir out/comparison --region arrows:x,y,width,height
```

Use [qa-rubric.md](references/qa-rubric.md). Raster similarity cannot approve semantics. Close a
finding only after inspecting a fresh render of the exact delivered artifact.

## Output guarantees and fallbacks

- Always retain valid `figure-spec.json` and SVG.
- Produce PNG and PDF when a renderer backend is available; the environment probe must identify one
  before committing to the format.
- Treat PPTX as optional unless the environment probe and a test render confirm a supported backend.
- If conversion is skipped, mark the format `skipped` with the missing capability in the QA report;
  do not fabricate an empty or unverified deliverable.
- Keep absolute machine paths out of specs, SVG links, PPTX relationships, and provenance intended
  for distribution.

## Acceptance

Deliver only when:

- strict spec validation passes;
- semantic review is approved;
- every edge has a declared meaning and correct ports;
- SVG, PNG, PDF, and any PPTX show the same scientific topology;
- final renders contain no clipping, missing glyphs, broken SVGs, accidental overlaps, or canvas
  overflow;
- required text remains legible at final size and in grayscale;
- provenance distinguishes verified evidence, user assets, inference, and generated illustration;
- QA contains no Critical or Major finding.

Return the deliverables, a concise change summary, the renderer/backend used, any skipped optional
format, and unresolved Minor findings. Do not attach working directories or source-paper pages
unless requested.

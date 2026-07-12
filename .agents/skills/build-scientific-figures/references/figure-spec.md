# Figure specification

The v1 figure specification is the shared intermediate representation for SVG, raster, PDF, and
optional PPTX backends. Validate it before rendering.

## Core objects

- `canvas`: logical pixel dimensions and background.
- `theme`: open-font stack, semantic palette, panel and connector defaults.
- `panels`: named containers or cards with absolute geometry.
- `texts`: standalone labels and annotations.
- `assets`: real images or explicit placeholders with alt text and fitting rules.
- `ports`: semantic endpoints with owners and absolute coordinates.
- `edges`: directed or undirected relationships between declared ports.
- `outputs`: requested render formats; SVG is mandatory.
- `review`: human semantic-graph approval state.
- `provenance`: page-addressable evidence and asset origin.

Use stable, human-readable ids. Do not treat exporter-generated random ids as source-of-truth
identifiers.

## Geometry and layering

All coordinates use the canvas pixel coordinate system. Keep every bounding box and route point
inside the canvas. The SVG renderer uses this order:

1. canvas background;
2. external edges;
3. panels;
4. raster or SVG assets;
5. internal edges;
6. text and optional debug ports.

This order allows panel boundaries to mask incoming external connector ends while preserving
internal time or action arrows over frame content.

Use explicit points for high-risk routes. The first and last points must coincide with the declared
source and destination ports. Use `route: orthogonal` only when a deterministic midpoint route is
acceptable.

## Theme tokens

Colors may be literal `#RRGGBB` values or tokens such as `@primary`. Tokens resolve through
`theme.palette`. Prefer semantic tokens in reusable templates and literal colors only for
source-matched exact mode.

Use Noto Sans as the default Linux font. Treat proprietary fonts as optional exact-mode inputs and
record fallback behavior.

## Assets

Resolve relative paths from the spec file. Set `placeholder: true` when a real asset is unavailable;
do not use a fabricated image that could be mistaken for evidence. Run untrusted SVG through
`scripts/sanitize_svg.py` before referencing it.

`fit` values:

- `contain`: show the entire asset with possible letterboxing;
- `cover`: fill the slot while preserving aspect ratio and cropping overflow;
- `stretch`: distort to the slot; use only for intentionally abstract textures.

## Validation and rendering

From the skill directory:

```bash
python scripts/validate_figure_spec.py assets/templates/wide-pipeline.spec.json \
  --require-approved --strict
python scripts/build_svg.py assets/templates/wide-pipeline.spec.json \
  --output /tmp/scientific-figure/figure.svg --require-approved
python scripts/render_outputs.py /tmp/scientific-figure/figure.svg \
  --output-dir /tmp/scientific-figure/rendered
```

For the optional public PptxGenJS backend:

```bash
npm install --prefix scripts
node scripts/build_pptx.mjs figure-spec.json --output figure.pptx
```

Prefer the Presentations skill and its supported runtime when it is available. Otherwise treat the
PptxGenJS output as an editable projection: panels, text, and segmented connectors remain editable,
but exact rounded connector geometry and image cropping may differ from the canonical SVG.

## Schema and compatibility

`assets/figure-spec.schema.json` documents the public v1 shape. `scripts/validate_figure_spec.py`
adds cross-object checks that JSON Schema cannot express, including id uniqueness, port ownership,
edge endpoints, internal-owner boundaries, asset existence, canvas bounds, source mappings, and the
semantic review gate.

Keep `version: "1.0"` until a backward-incompatible field change is required. Add optional fields
without changing existing meaning; do not silently reinterpret `scope`, `arrowhead`, or provenance
status.

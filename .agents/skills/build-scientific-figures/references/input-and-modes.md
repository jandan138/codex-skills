# Inputs and fidelity modes

Use this reference before creating a workspace or interpreting a reference figure.

## Input inventory

Record every supplied item before analysis:

- reference figures, screenshots, slide decks, or PDFs;
- the paper PDF and any supplement;
- real experiment, simulator, microscope, plot, or camera frames;
- logos, icons, fonts, and institutional style requirements;
- requested canvas, target venue, caption, and output formats;
- whether the user owns or is authorized to reproduce the reference design.

Do not silently search for missing private assets. Keep supplied assets unchanged in a source
directory and place derived crops, sanitized SVGs, and renders in a separate working directory.

## Fidelity modes

Choose exactly one mode and store it in `figure-spec.json`.

### `exact`

Use for an author-owned figure, an authorized template, internal reconstruction, or a user request
that explicitly requires coordinate-level fidelity. Match composition, typography, crop, connector
topology, and visual hierarchy. Preserve the source separately and document authorization. Do not
publish or distribute an exact reconstruction when the rights are unclear.

### `inspired`

Use a reference only to learn its visual grammar. Preserve useful principles such as density,
panel rhythm, or image-to-diagram balance while changing composition, geometry, palette, icon
vocabulary, and wording. This is the default for a publication-bound figure based on another
paper's design.

### `original`

Derive the figure from the paper's scientific semantics and user assets. Use the neutral bundled
theme or a user-provided brand system. Do not use a third-party figure as a spatial template.

When the user's intent is ambiguous, prefer `inspired` for reference-led work and `original` for
paper-only work. State the assumption before rendering.

## Minimum input contract

Before final rendering, establish:

1. a one-sentence message the figure must communicate;
2. the audience and target venue;
3. authoritative labels, numbers, units, and claims;
4. the node-edge semantic graph;
5. source and destination ports for every directed relationship;
6. the asset manifest and provenance status;
7. the requested output formats and target canvas;
8. an approved semantic review record.

Missing visual assets may be represented as named placeholders. Missing scientific relationships,
numbers, or units may not be invented.

## Output contract

Treat `figure-spec.json` and the canonical SVG as the reproducible source. Produce SVG, PNG, and
PDF after the required renderer capability is available. Produce PPTX only when a supported
presentation backend is detected; a skipped PPTX must not invalidate otherwise successful portable
outputs, but it must be recorded in the QA report.

Keep these artifacts together:

- `figure-spec.json`;
- canonical `.svg`;
- `.png` and `.pdf` render products;
- optional `.pptx` editable projection;
- paper and asset manifests;
- comparison evidence and `qa-report.json`.

## Human review checkpoint

Do not set `review.semantic_graph_approved` to `true` on the model's behalf when source semantics are
ambiguous. Show a compact node-edge inventory, list every inferred or unverified claim, and obtain
confirmation. After approval, record the approver and notes in the spec. Geometry and styling may
iterate afterward without changing approved semantics.

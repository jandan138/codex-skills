# Native PPTX figure hardening

Use this reference when the editable deliverable is a scientific-figure PPTX or when LibreOffice,
PowerPoint, or PDF export changes geometry or typography.

## Theme effects

New PowerPoint auto-shapes can inherit a theme `effectRef` even when no explicit shadow is visible
in the authoring library. `shape.shadow.inherit = false` typically emits an empty `effectLst`, but
LibreOffice may still honor a nonzero `p:style/a:effectRef`.

For a deliberately flat figure:

1. disable shadow inheritance;
2. remove explicit `outerShdw` effects;
3. set the shape style's `effectRef idx` to `0`;
4. reopen and render through the target application;
5. inspect the pixels rather than approving the XML alone.

Run `scripts/audit_pptx_figure.py --require-flat` to detect remaining effects.

## Rounded rectangles

The rectangular bounding box of a `roundRect` is not its visible interior near a corner. A title
box can be inside the bounding box and still protrude beyond the rounded outline. PowerPoint's
common default adjustment is approximately `0.16667` of the shorter side, which produces large
corner radii on wide or tall panels.

Prefer one of these approaches:

- place titles directly inside a mathematically safe part of the panel and use a divider;
- reduce the outer panel's corner adjustment;
- move an independent title bar below the corner arc with sufficient horizontal inset.

When containment matters, validate the title box corners and divider endpoints against the actual
rounded outline, not only `left/top/width/height` inequalities.

## Text and alignment

- Use a small, deliberate font-size set. A large number of local sizes usually indicates text was
  squeezed after layout.
- Check text at the actual paper inclusion width. PPT source points are scaled with the canvas.
- Normalize margins and vertical anchors within a repeated family.
- Compare exact EMU coordinates for row/column baselines. Differences around `0.03 inch` are
  visible in dense tables.
- Prefer a controlled line break at a semantic boundary, such as an underscore, over renderer-
  chosen character wrapping.
- Re-render after every width, font, icon, or label change; those edits can change line breaks.

## Connectors

- Encode an orthogonal route as explicit segments when renderer-native elbow connectors drift.
- Put the arrowhead only on the final segment.
- Give each segment a stable semantic name.
- Keep internal temporal arrows separate from external evidence/control routes.
- Use a declared junction for a merge. Plain geometric overlap is not a scientific merge.

## Required round-trip

For an editable PPTX, keep all three artifacts:

1. the delivered PPTX;
2. a PDF exported by the target office renderer;
3. a PNG rendered from that PDF.

Inspect the full figure and dense crops. Check one slide, no external relationships, no machine-
specific paths, no missing fonts, no clipped text, and no unexplained theme effects. Canonical SVG
or code output does not substitute for reviewing the actual PPTX round-trip.

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
  For uniform scaling, `paper_pt = source_pt * inserted_width / source_canvas_width`, using the
  same units for both widths. For example, 8 pt on a 183 mm source becomes about 7 pt at 160 mm.
  Inspect the actual PDF; this example is not a minimum-font recommendation.
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

## Embedded image quality

A high-resolution slide PNG does not prove that the office-exported PDF retains source image
pixels. Compare embedded image dimensions with the originals and their final placed size. Prefer
export settings that preserve image quality, then inspect the resulting PDF for downsampling.

If an export still reduces essential images, a source-pixel restoration is an optional, narrowly
verified fallback. Retain the original PDF, map each target unambiguously, and preserve placement,
clipping, page dimensions, native text, vectors, color interpretation, and transparency. Compare
decoded replacement pixels with the original asset and confirm unchanged page drawing commands;
render again to detect masking or color changes. Do not retouch evidence or strip alpha as part of
this operation. A mapping tied to one export's object names and dimensions is not a reusable
general-purpose restoration tool. A changed export must be remapped and revalidated.

## Manuscript integration

Integrate only within the author's requested scope. Retain the accepted source and caption, update
the active manuscript reference and provenance, and protect the accepted figure from unrelated
multi-figure exporters (a versioned output filename is one practical option).

Compile the manuscript and inspect the actual figure page, dense regions, and print-size details.
Check font scaling, embedded images, label alignment, caption meaning, and connection topology.
Compare page count and compiler warnings against the pre-change baseline, verify references resolve,
and check that neighboring figures were not changed. Report remaining small-text limits explicitly.
Keep required/optional procedures, schematic-versus-observed boundaries, and planned-versus-achieved
outcomes recoverable after graphic labels are shortened or removed.

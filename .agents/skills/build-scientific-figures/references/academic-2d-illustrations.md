# Academic 2D illustration components

Use this reference when a scientific figure benefits from small, friendly 2D illustrations rather
than generic boxes or stock SVG icons. The goal is publication clarity with a coherent visual family,
not decorative cartooning.

## Assign each illustration a semantic role

Choose one class before generating an asset:

- **scene-derived exposition**: a simplified physical setup, transition, or outcome that helps the
  reader recognize the real task;
- **abstract semantic component**: evidence binding, grammar, intent, verification, compilation, or
  another nonphysical transformation;
- **control or terminal component**: policy, execute, clarify, reject, merge, or stop.

Use scene-derived images mainly at inputs, outputs, or a scoped execution witness. Do not depict
grammar, intent, verification, or policy as arbitrary beakers merely because the paper contains a
liquid task. Their pictures should encode their computational roles.

## Generate one family, not isolated icons

Write one family brief covering line color, fill palette, viewpoint, stroke character, detail level,
and exclusions. Generate related components together as a 2x2 or 2x3 atlas when possible so their
style is conditioned jointly.

For small paper components, request:

- flat or lightly hand-drawn 2D academic illustration;
- one dark ink color and two or three restrained fills;
- no words, pseudo-text, logos, people, photorealism, glossy 3D, drop shadows, or decorative clutter;
- generous gutters and true transparent background;
- legibility when the visible foreground is only 48--96 px high.

Keep the prompt/design brief and generator metadata in internal provenance. Reviewer-facing captions
should describe what the illustration means, not how it was generated.

## Extract and normalize components

Inspect the atlas at native resolution before cropping. Reject or repair baked checkerboards,
cross-cell strokes, inconsistent outlines, missing alpha, or semantic ambiguity. Crop by reviewed
cell bounds, then trim only empty transparent margins. Never crop through a foreground stroke.

Transparent canvas dimensions are not an alignment metric. Run:

```bash
python scripts/analyze_icon_optics.py icon-a.png icon-b.png icon-c.png --pretty
```

Use each asset's alpha bounding box and alpha-weighted centroid to normalize visible height and
optical baseline. Equalize the apparent area of peer icons, while allowing a primary physical witness
to remain larger. Recheck horizontal gaps using foreground bounds rather than image rectangles.

## Compose deterministically

Keep labels as native text; never rely on generated lettering. Place raster components into PPTX or
SVG with explicit coordinates from configuration, and keep connectors as native vector paths. Use
the same font role, size, and weight for peer labels such as POLICY and COMPILER, and a second shared
role for terminal labels such as EXECUTE, CLARIFY, and REJECT.

The bundled case study under `assets/examples/illustration-led-method/` demonstrates this separation:
physical vessel scenes anchor selection/execution, computational cartoons explain the middle, and a
coherent authority family distinguishes policy, compiler, clarification, and rejection. Read its
`provenance.json` before adaptation. It is a visual baseline, not a reusable scientific claim.

## Review at paper scale

Inspect the standalone figure, dense crops, grayscale output, PPTX round trip, and the exact paper
page. Check that the illustrations are visible without dominating labels or connectors, peers share
an optical center, and no component crosses a title rule or card boundary. The claim boundary must
distinguish explanatory illustration from simulation renders and measured evidence.
